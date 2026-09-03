"""HU7: API, SQL y servicios aislados, sin Supabase ni correo real."""

import json
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import get_auth_service, get_current_user, require_admin
from app.api.operadores import get_operadores_service
from app.db.access import SqlAlchemyAccessRepository
from app.db.operadores import SqlAlchemyOperadoresRepository
from app.db.usuarios import SqlAlchemyUsuariosRepository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.services.auth_service import AuthService
from app.services.operadores_service import OperadoresService, generate_temporary_password


@pytest.fixture
def operator_setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as connection:
        # Dobles locales del hash: no usan ni validan pgcrypto de producción.
        connection.connection.driver_connection.create_function("crypt", 2, lambda raw, _: raw)
        for sql in [
            """CREATE TABLE usuarios (
                id TEXT PRIMARY KEY, nombre_completo TEXT, email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, rol TEXT NOT NULL,
                primer_ingreso BOOLEAN NOT NULL DEFAULT 1, activo BOOLEAN NOT NULL DEFAULT 1,
                intentos_fallidos INTEGER NOT NULL DEFAULT 0, bloqueado_hasta TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
            "CREATE UNIQUE INDEX uq_usuarios_email_normalizado ON usuarios(lower(email))",
            """CREATE TABLE entregas_credenciales (
                id TEXT PRIMARY KEY, usuario_id TEXT NOT NULL UNIQUE REFERENCES usuarios(id),
                destinatario_email TEXT NOT NULL, estado TEXT NOT NULL, intentos INTEGER DEFAULT 0,
                ultimo_error TEXT, enviado_en TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE reclamos (id TEXT PRIMARY KEY, estado TEXT NOT NULL,
                operador_asignado_id TEXT REFERENCES usuarios(id), updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            "CREATE TABLE propietarios (id TEXT PRIMARY KEY, usuario_id TEXT)",
            "CREATE TABLE inquilinos (id TEXT PRIMARY KEY, usuario_id TEXT)",
        ]:
            connection.execute(text(sql))
    factory = sessionmaker(bind=engine)
    repository = SqlAlchemyOperadoresRepository(factory)
    sender = Mock()
    service = OperadoresService(repository, sender)
    app.dependency_overrides[get_operadores_service] = lambda: service
    app.dependency_overrides[get_auth_service] = lambda: AuthService(
        SqlAlchemyUsuariosRepository(factory), SqlAlchemyAccessRepository(factory),
    )
    with TestClient(app) as client:
        yield client, repository, sender
    for dependency in (get_operadores_service, get_auth_service, get_current_user):
        app.dependency_overrides.pop(dependency, None)
    engine.dispose()


def create(client, **changes):
    return client.post("/usuarios/operadores", json={
        "nombre_completo": "Ana Prueba", "email": "operador@example.com", **changes,
    })


def update_user(repository, user_id, clause):
    with repository.session_factory.begin() as session:
        session.execute(text(f"UPDATE usuarios SET {clause} WHERE id = :id"), {"id": user_id})


def test_create_is_normalized_and_mail_is_after_commit(operator_setup):
    client, repository, sender = operator_setup
    def check_committed(**kwargs):
        with repository.session_factory() as session:
            assert session.execute(text("SELECT COUNT(*) FROM usuarios")).scalar_one() == 1
        assert kwargs["recipient"] == "operador@example.com"
    sender.send.side_effect = check_committed
    response = create(client, nombre_completo="  Ana   Prueba ", email="OPERADOR@EXAMPLE.COM")
    assert response.status_code == 201
    result = response.json()
    assert result["nombre_completo"] == "Ana Prueba"
    assert result["activo"] and result["acceso"]["primer_ingreso"]
    assert result["acceso"]["estado"] == "enviado"
    assert result["acceso"]["intentos"] == 1
    assert set(result) == {"id", "nombre_completo", "email", "activo", "acceso", "created_at"}
    assert "password" not in json.dumps(result)
    assert "delivery_id" not in json.dumps(result)


@pytest.mark.parametrize("role", ["administrador", "propietario", "inquilino", "operador"])
@pytest.mark.parametrize("active", [True, False])
def test_global_duplicate_email_for_every_role_including_inactive(operator_setup, role, active):
    client, repository, sender = operator_setup
    with repository.session_factory.begin() as session:
        session.execute(text("""INSERT INTO usuarios(id,email,password_hash,rol,activo)
            VALUES(:id,'OPERADOR@EXAMPLE.COM','hash',:role,:active)"""),
            {"id": str(uuid4()), "role": role, "active": active})
    response = create(client)
    assert response.status_code == 409
    assert response.json()["detail"]["field"] == "email"
    sender.send.assert_not_called()
    with repository.session_factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM usuarios")).scalar_one() == 1
        assert session.execute(text("SELECT COUNT(*) FROM entregas_credenciales")).scalar_one() == 0


@pytest.mark.parametrize("changes", [
    {"nombre_completo": ""}, {"nombre_completo": "12345678"},
    {"nombre_completo": "x" * 121}, {"email": "no-es-email"},
    {"rol": "administrador"}, {"password": "no-se-acepta"}, {"activo": False},
])
def test_validation_and_no_mass_assignment(operator_setup, changes):
    client, _, sender = operator_setup
    assert create(client, **changes).status_code == 422
    sender.send.assert_not_called()


def test_failed_mail_preserves_account_and_retry_rotates_secret(operator_setup, caplog):
    client, repository, sender = operator_setup
    sender.send.side_effect = RuntimeError("do-not-persist-smtp-secrets")
    created = create(client).json()
    assert created["acceso"]["estado"] == "fallido"
    first_password = sender.send.call_args.kwargs["temporary_password"]
    sender.send.side_effect = None
    retry = client.post(f"/usuarios/operadores/{created['id']}/acceso/reintentar")
    assert retry.status_code == 200
    new_password = sender.send.call_args.kwargs["temporary_password"]
    assert first_password != new_password
    assert retry.json()["acceso"]["estado"] == "enviado"
    assert retry.json()["acceso"]["intentos"] == 2
    with repository.session_factory() as session:
        assert session.execute(text("SELECT password_hash FROM usuarios")).scalar_one() == new_password
        assert session.execute(text("SELECT ultimo_error FROM entregas_credenciales")).scalar_one() is None
    assert "do-not-persist-smtp-secrets" not in caplog.text


@pytest.mark.parametrize("clause", ["primer_ingreso = false", "activo = false"])
def test_retry_rejects_activated_or_inactive_account(operator_setup, clause):
    client, repository, sender = operator_setup
    created = create(client).json()
    update_user(repository, created["id"], clause)
    sender.reset_mock()
    assert client.post(f"/usuarios/operadores/{created['id']}/acceso/reintentar").status_code == 409
    sender.send.assert_not_called()


def test_pending_delivery_cannot_be_retried_immediately_and_stale_result_is_ignored(operator_setup):
    client, repository, sender = operator_setup
    created = create(client).json()
    user_id = UUID(created["id"])
    context = repository.prepare_retry(user_id, "test-new")
    response = client.post(f"/usuarios/operadores/{user_id}/acceso/reintentar")
    assert response.status_code == 409
    with repository.session_factory.begin() as session:
        session.execute(text("UPDATE entregas_credenciales SET updated_at = '2000-01-01 00:00:00'"))
    current = repository.prepare_retry(user_id, "test-latest")
    repository.record_delivery(context, sent=True)
    assert repository.get(user_id)["acceso"]["estado"] == "pendiente"
    repository.record_delivery(current, sent=False)
    assert repository.get(user_id)["acceso"]["estado"] == "fallido"


def test_account_survives_delivery_tracking_failure(operator_setup, monkeypatch):
    client, repository, _ = operator_setup
    monkeypatch.setattr(repository, "record_delivery", Mock(side_effect=SQLAlchemyError()))
    response = create(client)
    assert response.status_code == 201
    assert response.json()["acceso"]["estado"] == "pendiente"


def test_failed_delivery_insert_rolls_back_account_without_leaking_error(operator_setup):
    client, repository, sender = operator_setup
    with repository.session_factory.begin() as session:
        session.execute(text("""CREATE TRIGGER fail_delivery BEFORE INSERT ON entregas_credenciales
            BEGIN SELECT RAISE(ABORT, 'private-database-detail'); END"""))
    response = create(client)
    assert response.status_code == 503
    assert "private-database-detail" not in response.text
    sender.send.assert_not_called()
    with repository.session_factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM usuarios")).scalar_one() == 0


def test_admin_cannot_be_deactivated_through_operator_endpoint(operator_setup):
    client, repository, sender = operator_setup
    admin_id = str(uuid4())
    with repository.session_factory.begin() as session:
        session.execute(text("""INSERT INTO usuarios(id,email,password_hash,rol)
            VALUES(:id,'admin@example.com','hash','administrador')"""), {"id": admin_id})
    assert client.patch(f"/usuarios/operadores/{admin_id}/desactivar").status_code == 404
    with repository.session_factory() as session:
        assert session.execute(text("SELECT activo FROM usuarios WHERE id = :id"), {"id": admin_id}).scalar_one()
    sender.send.assert_not_called()


def test_list_filters_sorts_and_paginates_only_operators(operator_setup):
    client, repository, _ = operator_setup
    create(client, nombre_completo="Zoe Prueba", email="zoe@example.com")
    create(client, nombre_completo="Ana Prueba", email="ana@example.com")
    with repository.session_factory.begin() as session:
        session.execute(text("INSERT INTO usuarios(id,email,password_hash,rol) VALUES('admin','admin@example.com','hash','administrador')"))
    result = client.get("/usuarios/operadores?page_size=1").json()
    assert result["total"] == result["total_pages"] == 2
    assert result["items"][0]["nombre_completo"] == "Ana Prueba"
    result = client.get("/usuarios/operadores?search=ZOE%40").json()
    assert result["total"] == 1 and result["items"][0]["email"] == "zoe@example.com"
    assert client.get("/usuarios/operadores?search=nadie").json()["items"] == []
    assert client.get("/usuarios/operadores?page=0").status_code == 422


def test_deactivation_releases_only_pending_escalations_and_is_idempotent(operator_setup):
    client, repository, _ = operator_setup
    user_id = create(client).json()["id"]
    other = create(client, email="otro@example.com").json()["id"]
    with repository.session_factory.begin() as session:
        for case, state, assigned in [("pending", "Escalado", user_id), ("resolved", "Resuelto", user_id),
                                      ("other", "Escalado", other), ("unassigned", "Escalado", None)]:
            session.execute(text("INSERT INTO reclamos(id,estado,operador_asignado_id) VALUES(:id,:state,:user)"),
                            {"id": case, "state": state, "user": assigned})
    response = client.patch(f"/usuarios/operadores/{user_id}/desactivar")
    assert response.status_code == 200
    assert response.json()["reclamos_liberados"] == 1
    assert response.json()["operador"]["activo"] is False
    with repository.session_factory() as session:
        rows = {r.id: (r.estado, r.operador_asignado_id) for r in session.execute(text("SELECT * FROM reclamos"))}
    assert rows == {"pending": ("Escalado", None), "resolved": ("Resuelto", user_id),
                    "other": ("Escalado", other), "unassigned": ("Escalado", None)}
    assert client.patch(f"/usuarios/operadores/{user_id}/desactivar").json()["reclamos_liberados"] == 0


def test_release_failure_rolls_back_user_deactivation(operator_setup):
    client, repository, _ = operator_setup
    user_id = UUID(create(client).json()["id"])
    with repository.session_factory.begin() as session:
        session.execute(text("INSERT INTO reclamos VALUES('case','Escalado',:id,CURRENT_TIMESTAMP)"), {"id": str(user_id)})
        session.execute(text("CREATE TRIGGER fail_release BEFORE UPDATE ON reclamos BEGIN SELECT RAISE(ABORT,'forced'); END"))
    with pytest.raises(SQLAlchemyError):
        repository.deactivate(user_id)
    assert repository.get(user_id)["activo"]


@pytest.mark.parametrize("role", ["propietario", "inquilino", "operador"])
def test_all_operator_routes_reject_other_roles(operator_setup, role):
    client, _, sender = operator_setup
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="person@example.com", rol=role, primer_ingreso=False)
    for method, path, payload in [("GET", "", None), ("POST", "", {"nombre_completo": "Ana Prueba", "email": "ana@example.com"}),
                                  ("PATCH", f"/{uuid4()}/desactivar", None), ("POST", f"/{uuid4()}/acceso/reintentar", None)]:
        assert client.request(method, "/usuarios/operadores" + path, json=payload).status_code == 403
    sender.send.assert_not_called()


def test_missing_session_and_unknown_ids(operator_setup):
    client, _, _ = operator_setup
    assert client.patch(f"/usuarios/operadores/{uuid4()}/desactivar").status_code == 404
    assert client.post(f"/usuarios/operadores/{uuid4()}/acceso/reintentar").status_code == 404
    app.dependency_overrides.pop(require_admin, None)
    assert client.get("/usuarios/operadores").status_code == 401


def test_full_login_change_password_and_deactivation_invalidates_session(operator_setup, monkeypatch):
    client, repository, sender = operator_setup
    monkeypatch.setenv("JWT_SECRET", "test-only-operator-auth-secret-with-at-least-32-characters")
    user_id = create(client).json()["id"]
    password = sender.send.call_args.kwargs["temporary_password"]
    login = client.post("/auth/login", json={"email": "operador@example.com", "password": password})
    assert login.status_code == 200 and login.json()["user"]["primer_ingreso"]
    changed = client.post("/auth/cambiar-contrasena", json={"password_actual": password,
                        "password_nueva": "NuevaPrueba9", "confirmacion_password": "NuevaPrueba9"})
    assert changed.status_code == 200 and not changed.json()["user"]["primer_ingreso"]
    assert client.get("/auth/me").status_code == 200
    repository.deactivate(UUID(user_id))
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": "operador@example.com", "password": "NuevaPrueba9"}).status_code == 403


def test_random_password_format():
    passwords = {generate_temporary_password() for _ in range(200)}
    assert len(passwords) == 200
    assert all(len(p) == 8 and p.isalnum() and any(c.isdigit() for c in p)
               and any(c.isalpha() for c in p) for p in passwords)


def test_migration_has_additive_fields_and_private_api_boundary():
    sql = (Path(__file__).parents[1] / "migrations/17_usuarios_operadores.sql").read_text(encoding="utf-8").lower()
    assert "add column if not exists nombre_completo" in sql
    assert "add column if not exists operador_asignado_id" in sql
    assert "idx_reclamos_operador_asignado" in sql
    assert "security invoker" in sql and "for share" in sql
    assert "usuarios enable row level security" in sql
    assert "reclamos enable row level security" in sql
    assert "revoke all on table public.usuarios, public.reclamos from anon, authenticated" in sql
    assert "delete from" not in sql and "security definer" not in sql
