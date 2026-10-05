"""HU11: API y SQL reales con SQLite aislado, sin llamadas externas."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import get_current_user
from app.api.property_claims import get_property_claims_service
from app.db.property_claims import SqlAlchemyPropertyClaimsRepository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.property_claims import PropertyClaimsFilters
from app.services.property_claims_service import PropertyClaimsService


@pytest.fixture
def history_case():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata = MetaData()
    properties = Table("propiedades", metadata,
        Column("id", String, primary_key=True), Column("direccion", String),
        Column("provincia", String), Column("localidad", String), Column("barrio", String),
        Column("tipo", String), Column("piso", Integer), Column("numero", String))
    tenants = Table("inquilinos", metadata,
        Column("id", String, primary_key=True), Column("usuario_id", String), Column("propiedad_id", String))
    claims = Table("reclamos", metadata,
        Column("id", String, primary_key=True), Column("numero", Integer),
        Column("descripcion", String), Column("estado", String), Column("tipo_gasto", String),
        Column("urgencia", String), Column("creado_en", DateTime), Column("updated_at", DateTime),
        Column("propiedad_id", String), Column("inquilino_id", String))
    history = Table("reclamo_historial_estados", metadata,
        Column("id", String, primary_key=True), Column("reclamo_id", String),
        Column("estado_anterior", String), Column("estado_nuevo", String),
        Column("origen", String), Column("timestamp", DateTime))
    metadata.create_all(engine)
    property_id, other_property_id, tenant_id, other_tenant, user_id = [uuid4() for _ in range(5)]
    admin = AuthenticatedUser(id=uuid4(), email="admin@example.com", rol="administrador", primer_ingreso=False)
    tenant = AuthenticatedUser(id=user_id, email="tenant@example.com", rol="inquilino", primer_ingreso=False, perfil_id=tenant_id)
    ids = [uuid4() for _ in range(25)]
    start = datetime(2026, 10, 1, 3, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(properties.insert(), [
            {"id": str(pid), "direccion": "Unidad de prueba", "provincia": "Córdoba",
             "localidad": "Localidad de prueba", "tipo": "casa"}
            for pid in (property_id, other_property_id)
        ])
        connection.execute(tenants.insert(), [
            {"id": str(tenant_id), "usuario_id": str(user_id), "propiedad_id": str(property_id)},
            {"id": str(other_tenant), "usuario_id": str(uuid4()), "propiedad_id": str(property_id)},
        ])
        connection.execute(claims.insert(), [
            {"id": str(cid), "numero": n, "descripcion": f"Reclamo sintético {n}.",
             "estado": "Resuelto" if n % 2 == 0 else "Recibido",
             "tipo_gasto": "ordinario" if n % 2 == 0 else None,
             "urgencia": "media", "creado_en": start + timedelta(hours=n),
             "updated_at": start + timedelta(hours=n), "propiedad_id": str(property_id),
             "inquilino_id": str(tenant_id if n <= 22 else other_tenant)}
            for n, cid in enumerate(ids, 1)
        ])
        # Mismo timestamp: el UUID se usa como desempate del historial.
        connection.execute(history.insert(), [
            {"id": str(uuid4()), "reclamo_id": str(ids[0]), "estado_anterior": None,
             "estado_nuevo": "Recibido", "origen": "inquilino", "timestamp": start},
            {"id": str(uuid4()), "reclamo_id": str(ids[0]), "estado_anterior": "Recibido",
             "estado_nuevo": "Clasificado", "origen": "agente", "timestamp": start + timedelta(minutes=1)},
        ])
    repository = SqlAlchemyPropertyClaimsRepository(sessionmaker(bind=engine))
    yield {"engine": engine, "repository": repository, "service": PropertyClaimsService(repository),
           "admin": admin, "tenant": tenant, "property": property_id, "other_property": other_property_id,
           "ids": ids, "start": start}
    engine.dispose()


@pytest.fixture
def client(history_case):
    app.dependency_overrides[get_property_claims_service] = lambda: history_case["service"]
    app.dependency_overrides[get_current_user] = lambda: history_case["admin"]
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_property_claims_service, None)
    app.dependency_overrides.pop(get_current_user, None)


def path(case, suffix=""):
    return f'/propiedades/{case["property"]}/reclamos{suffix}'


def test_admin_pagination_counts_and_stable_order(client, history_case):
    first = client.get(path(history_case)).json()
    response = client.get(path(history_case, "?page=2"))
    second = response.json()
    assert first["total"] == second["total"] == 25
    assert first["page_size"] == 20 and first["total_pages"] == 2
    assert [c["numero"] for c in first["items"]] == list(range(25, 5, -1))
    assert [c["numero"] for c in second["items"]] == [5, 4, 3, 2, 1]
    assert response.headers["X-Total-Count"] == "25"
    assert not client.get(path(history_case, "?page=3")).json()["items"]


def test_filters_are_combined_and_total_matches(client, history_case):
    data = client.get(path(history_case), params={
        "estado": "Resuelto", "tipo_gasto": "ordinario",
        "fecha_desde": "2026-10-01", "fecha_hasta": "2026-10-01",
    }).json()
    assert data["total"] == 11
    assert [item["numero"] for item in data["items"]] == list(range(22, 1, -2))
    assert client.get(path(history_case, "?tipo_gasto=expensa")).json()["total"] == 0
    assert client.get(path(history_case, "?tipo_gasto=sin_clasificar")).json()["total"] == 13


def test_date_range_includes_complete_argentine_day(client, history_case):
    # Medianoche argentina = 03:00 UTC; incluye el inicio y excluye el día siguiente.
    with history_case["engine"].begin() as connection:
        for number, instant in [(1, history_case["start"]),
                                (2, history_case["start"] - timedelta(microseconds=1)),
                                (3, history_case["start"] + timedelta(days=1) - timedelta(microseconds=1)),
                                (4, history_case["start"] + timedelta(days=1))]:
            connection.execute(text("UPDATE reclamos SET creado_en=:instant WHERE numero=:number"),
                               {"instant": instant, "number": number})
    data = client.get(path(history_case, "?fecha_desde=2026-10-01&fecha_hasta=2026-10-01")).json()
    numbers = [item["numero"] for item in data["items"]]
    # Todos entran en una página aplicando también estado/número por prueba específica.
    assert data["total"] == 21
    assert 3 in numbers and 2 not in numbers and 4 not in numbers
    last = client.get(path(history_case, "?fecha_desde=2026-10-01&fecha_hasta=2026-10-01&page=2")).json()
    assert [item["numero"] for item in last["items"]] == [1]


def test_tenant_scope_applies_to_items_counts_and_detail(client, history_case):
    app.dependency_overrides[get_current_user] = lambda: history_case["tenant"]
    response = client.get(path(history_case))
    assert response.json()["total"] == 22
    assert response.headers["X-Total-Count"] == "22"
    assert all(item["numero"] <= 22 for item in response.json()["items"])
    assert client.get(path(history_case, f'/{history_case["ids"][24]}')).status_code == 404
    own = client.get(path(history_case, f'/{history_case["ids"][0]}'))
    assert own.status_code == 200
    assert [item["estado_nuevo"] for item in own.json()["historial"]] == ["Recibido", "Clasificado"]


def test_previous_tenant_keeps_only_their_own_history(client, history_case):
    app.dependency_overrides[get_current_user] = lambda: history_case["tenant"]
    with history_case["engine"].begin() as connection:
        connection.execute(text("UPDATE inquilinos SET propiedad_id = :new WHERE id = :id"),
                           {"new": str(history_case["other_property"]), "id": str(history_case["tenant"].perfil_id)})
    assert client.get(path(history_case)).json()["total"] == 22
    assert client.get(f'/propiedades/{history_case["other_property"]}/reclamos').json()["total"] == 0


def test_tenant_cannot_access_unrelated_property_or_fake_profile(client, history_case):
    app.dependency_overrides[get_current_user] = lambda: history_case["tenant"]
    unrelated = f'/propiedades/{history_case["other_property"]}/reclamos'
    assert client.get(unrelated).status_code == 403
    assert client.get(f'{unrelated}/{history_case["ids"][0]}').status_code == 403
    forged = history_case["tenant"].model_copy(update={"id": uuid4()})
    app.dependency_overrides[get_current_user] = lambda: forged
    assert client.get(path(history_case)).status_code == 403


@pytest.mark.parametrize("role", ["operador", "propietario"])
def test_other_roles_are_forbidden(client, history_case, role):
    app.dependency_overrides[get_current_user] = lambda: history_case["admin"].model_copy(update={"rol": role})
    assert client.get(path(history_case)).status_code == 403
    assert client.get(path(history_case, f'/{history_case["ids"][0]}')).status_code == 403


def test_first_login_and_missing_session_cannot_read_history(client, history_case):
    app.dependency_overrides[get_current_user] = lambda: history_case["admin"].model_copy(update={"primer_ingreso": True})
    assert client.get(path(history_case)).status_code == 403
    app.dependency_overrides.pop(get_current_user)
    assert client.get(path(history_case)).status_code == 401


def test_missing_property_and_claim_do_not_return_data(client, history_case):
    assert client.get(f"/propiedades/{uuid4()}/reclamos").status_code == 404
    assert client.get(path(history_case, f"/{uuid4()}")).status_code == 404
    wrong = f'/propiedades/{history_case["other_property"]}/reclamos/{history_case["ids"][0]}'
    assert client.get(wrong).status_code == 404
    assert client.get(f'/propiedades/{history_case["other_property"]}/reclamos').json()["total"] == 0


@pytest.mark.parametrize("query", [
    "page=0", "page=-1", "page=abc", "estado=inventado", "tipo_gasto=otro",
    "fecha_desde=no-es-fecha", "fecha_desde=2026-10-02&fecha_hasta=2026-10-01",
    "fecha_hasta=9999-12-31",
])
def test_invalid_filters_are_rejected(client, history_case, query):
    assert client.get(path(history_case, f"?{query}")).status_code == 422


def test_total_header_is_exposed_to_frontend(client, history_case):
    response = client.get(path(history_case), headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert "x-total-count" in response.headers["access-control-expose-headers"].lower()


def test_equal_dates_use_claim_number_to_break_ties(history_case):
    with history_case["engine"].begin() as connection:
        connection.execute(text("UPDATE reclamos SET creado_en = :date"), {"date": history_case["start"]})
    page = history_case["service"].list(property_id=history_case["property"],
                                     user=history_case["admin"], filters=PropertyClaimsFilters())
    assert [item.numero for item in page.items] == list(range(25, 5, -1))
