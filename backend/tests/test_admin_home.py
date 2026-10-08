"""HU31: consulta real aislada, autorización y contrato HTTP sin APIs externas."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin_home import get_admin_home_repository
from app.api.auth import get_auth_service, get_current_user, require_admin
from app.core.security import COOKIE_NAME, create_access_token
from app.db.admin_home import SqlAlchemyAdminHomeRepository
from app.main import app
from app.schemas.admin_home import ActiveEntityCount, AdminHomeSummary, ClaimsSummary
from app.schemas.auth import AuthenticatedUser
from app.services.auth_service import InactiveAccountError


@pytest.fixture
def summary_db():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        for statement in (
            "CREATE TABLE propietarios (id INTEGER PRIMARY KEY)",
            "CREATE TABLE propiedades (id INTEGER PRIMARY KEY)",
            "CREATE TABLE inquilinos (id INTEGER PRIMARY KEY)",
            "CREATE TABLE proveedores (id INTEGER PRIMARY KEY, activo BOOLEAN NOT NULL)",
            "CREATE TABLE usuarios (id INTEGER PRIMARY KEY, rol TEXT NOT NULL, activo BOOLEAN NOT NULL)",
            """CREATE TABLE reclamos (
                id INTEGER PRIMARY KEY, estado TEXT NOT NULL,
                tipo_gasto TEXT, origen_clasificacion TEXT
            )""",
            "CREATE TABLE reclamo_responsables (reclamo_id INTEGER)",
        ):
            connection.execute(text(statement))
    yield engine, SqlAlchemyAdminHomeRepository(sessionmaker(bind=engine))
    engine.dispose()


def add_claim(engine, *, state, expense=None, origin=None, responsible=False):
    with engine.begin() as connection:
        result = connection.execute(text("""
            INSERT INTO reclamos (estado, tipo_gasto, origen_clasificacion)
            VALUES (:state, :expense, :origin)
        """), {"state": state, "expense": expense, "origin": origin})
        if responsible:
            connection.execute(text("INSERT INTO reclamo_responsables VALUES (:id)"),
                               {"id": result.lastrowid})


def test_empty_database_returns_zero_counts_and_aware_timestamp(summary_db):
    _, repo = summary_db
    data = repo.get_summary().model_dump()
    assert data.pop("consultado_en").tzinfo is not None
    assert data == {
        "propietarios": {"total": 0}, "propiedades": {"total": 0},
        "inquilinos": {"total": 0}, "proveedores": {"total": 0, "activos": 0},
        "operadores": {"total": 0, "activos": 0},
        "reclamos": {"activos": 0, "pendientes_clasificacion": 0},
    }


def test_registered_counts_active_subsets_and_one_statement(summary_db):
    engine, repo = summary_db
    with engine.begin() as connection:
        for table, total in (("propietarios", 2), ("propiedades", 3), ("inquilinos", 4)):
            for index in range(total):
                connection.execute(text(f"INSERT INTO {table} VALUES (:id)"), {"id": index})
        connection.execute(text("INSERT INTO proveedores VALUES (1, true), (2, true), (3, false)"))
        connection.execute(text("""
            INSERT INTO usuarios VALUES
            (1, 'operador', true), (2, 'operador', false),
            (3, 'administrador', true), (4, 'inquilino', true), (5, 'propietario', true)
        """))
    statements = []
    event.listen(engine, "before_cursor_execute",
                 lambda conn, cursor, statement, params, context, many: statements.append(statement))
    summary = repo.get_summary()
    assert len(statements) == 1
    assert (summary.propietarios.total, summary.propiedades.total, summary.inquilinos.total) == (2, 3, 4)
    assert summary.proveedores.model_dump() == {"total": 3, "activos": 2}
    assert summary.operadores.model_dump() == {"total": 2, "activos": 1}


@pytest.mark.parametrize(("state", "active", "pending"), [
    ("Recibido", 1, 0), ("Clasificado", 1, 0),
    ("Escalado", 1, 1), ("Clasificación pendiente", 1, 1),
    ("Pendiente de respuesta del responsable", 1, 0),
    ("Pendiente de respuesta - vencido", 1, 0), ("Autorizado", 1, 0),
    ("Rechazado por propietario", 1, 0), ("Pendiente de asignación", 1, 0),
    ("En proceso", 1, 0), ("Visita programada", 1, 0),
    ("Resuelto", 0, 0), ("Resuelto (sin confirmación)", 0, 0),
    ("Reabierto por disconformidad", 1, 0),
    ("Derivado a inmobiliaria (expensa)", 1, 0),
    ("Derivado a proveedor externo", 1, 0), ("Sesión expirada", 1, 0),
])
def test_existing_claim_states_define_active_and_pending(summary_db, state, active, pending):
    engine, repo = summary_db
    add_claim(engine, state=state)
    summary = repo.get_summary().reclamos
    assert summary.activos == active
    assert summary.pendientes_clasificacion == pending


@pytest.mark.parametrize("state", ["Escalado", "Clasificación pendiente"])
@pytest.mark.parametrize(("expense", "origin", "responsible", "pending"), [
    (None, None, False, 1), (None, "agente", False, 1),
    ("ordinario", "agente", False, 0), ("extraordinario", "agente", False, 0),
    ("expensa", "agente", False, 0), (None, "agente", True, 0),
    (None, "operador", False, 0), (None, "administrador", False, 0),
])
def test_pending_matches_hu13_queue_not_later_escalations(
    summary_db, state, expense, origin, responsible, pending,
):
    engine, repo = summary_db
    add_claim(engine, state=state, expense=expense, origin=origin, responsible=responsible)
    summary = repo.get_summary().reclamos
    assert summary.activos == 1
    assert summary.pendientes_clasificacion == pending


@pytest.mark.parametrize(("total", "active"), [(-1, 0), (2, -1), (1, 2)])
def test_invalid_active_counts_are_rejected(total, active):
    with pytest.raises(ValidationError):
        ActiveEntityCount(total=total, activos=active)


@pytest.mark.parametrize(("active", "pending"), [(-1, 0), (2, -1), (1, 2)])
def test_invalid_claim_counts_are_rejected(active, pending):
    with pytest.raises(ValidationError):
        ClaimsSummary(activos=active, pendientes_clasificacion=pending)


ADMIN = AuthenticatedUser(
    id=UUID("00000000-0000-0000-0000-000000000001"), email="admin@example.com",
    rol="administrador", primer_ingreso=False,
)


@pytest.fixture
def client(summary_db, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "local-test-secret-not-a-production-credential")
    _, repo = summary_db
    # No usar la autorización administrativa simulada de los CRUD: probarla.
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    app.dependency_overrides[get_admin_home_repository] = lambda: repo
    yield TestClient(app)
    for dependency in (get_current_user, get_admin_home_repository, get_auth_service):
        app.dependency_overrides.pop(dependency, None)


def test_summary_endpoint_is_read_only_private_and_has_no_personal_data(client):
    response = client.get("/admin/resumen")
    assert response.status_code == 200
    result = response.json()
    assert result["propietarios"] == {"total": 0}
    assert datetime.fromisoformat(result["consultado_en"].replace("Z", "+00:00")).tzinfo is not None
    assert set(result) == {"consultado_en", "propietarios", "propiedades", "inquilinos",
                           "proveedores", "operadores", "reclamos"}
    for method in ("post", "patch", "delete"):
        assert getattr(client, method)("/admin/resumen").status_code == 405


def test_no_session_cannot_obtain_counts(client):
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get("/admin/resumen").status_code == 401


@pytest.mark.parametrize("role", ["operador", "inquilino", "propietario"])
def test_other_roles_cannot_obtain_counts(client, role):
    app.dependency_overrides[get_current_user] = lambda: ADMIN.model_copy(update={"rol": role})
    assert client.get("/admin/resumen").status_code == 403


def test_first_login_must_change_password(client):
    app.dependency_overrides[get_current_user] = lambda: ADMIN.model_copy(update={"primer_ingreso": True})
    response = client.get("/admin/resumen")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "first_login_required"


def test_inactive_session_cannot_obtain_counts(client):
    class InactiveAuthService:
        def get_active_user(self, user_id):
            raise InactiveAccountError()
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_auth_service] = InactiveAuthService
    client.cookies.set(COOKIE_NAME, create_access_token(
        user_id=str(ADMIN.id), role=ADMIN.rol, first_login=False,
    ))
    assert client.get("/admin/resumen").status_code == 401


def test_database_failure_does_not_return_zeros_or_expose_sql(client):
    class BrokenRepository:
        def get_summary(self):
            raise SQLAlchemyError("connection params and internal SQL must stay private")
    app.dependency_overrides[get_admin_home_repository] = BrokenRepository
    response = client.get("/admin/resumen")
    assert response.status_code == 503
    assert response.json() == {"detail": {
        "code": "summary_unavailable",
        "message": "No pudimos obtener el resumen. Podés volver a intentar.",
    }}


def test_response_requires_explicit_timezone(summary_db):
    _, repo = summary_db
    data = repo.get_summary().model_dump()
    data["consultado_en"] = datetime(2026, 10, 5)
    with pytest.raises(ValidationError):
        AdminHomeSummary.model_validate(data)
