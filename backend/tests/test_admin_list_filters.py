"""Filtros sobre SQL real en memoria y rutas protegidas, sin servicios externos."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import require_admin
from app.api.propiedades import get_propiedades_service
from app.api.propietarios import get_propietarios_service
from app.api.inquilinos import get_inquilinos_service
from app.db.propiedades import SqlAlchemyPropiedadesRepository
from app.db.propietarios import SqlAlchemyPropietariosRepository
from app.db.inquilinos import SqlAlchemyInquilinosRepository
from app.main import app
from app.schemas.list_filters import PropertiesListFilters, OwnersListFilters, TenantsListFilters
from app.services.propiedades_service import PropiedadesService
from app.services.propietarios_service import PropietariosService
from app.services.inquilinos_service import InquilinosService


def uid(n):
    return str(UUID(int=n))


@pytest.fixture
def repos():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as c:
        c.execute(text("""CREATE TABLE propietarios (
            id TEXT PRIMARY KEY, nombre_completo TEXT, dni TEXT, email TEXT, telefono TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"""))
        c.execute(text("""CREATE TABLE propiedades (
            id TEXT PRIMARY KEY, direccion TEXT, provincia TEXT, localidad TEXT, barrio TEXT,
            tipo TEXT, piso INT, numero TEXT, propietario_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"""))
        c.execute(text("""CREATE TABLE inquilinos (
            id TEXT PRIMARY KEY, nombre_completo TEXT, dni TEXT, email TEXT, telefono TEXT,
            estado TEXT, propiedad_id TEXT, usuario_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"""))
        c.execute(text("CREATE TABLE reclamos (id TEXT, propiedad_id TEXT, inquilino_id TEXT)"))
        c.execute(text("CREATE TABLE usuarios (id TEXT, primer_ingreso BOOLEAN)"))
        c.execute(text("""CREATE TABLE entregas_credenciales (usuario_id TEXT, estado TEXT,
            intentos INT, ultimo_error TEXT, enviado_en TEXT)"""))
        for n, name in enumerate(("Ana Sintetica", "Bruno Sintetico", "Carla Sintetica"), 1):
            c.execute(text("""INSERT INTO propietarios (id, nombre_completo, dni, email, telefono)
                VALUES (:id, :name, :dni, :email, '00000000')"""),
                {"id": uid(n), "name": name, "dni": str(10000000+n), "email": f"owner{n}@example.com"})
        for n, (province, city, area, kind, owner) in enumerate([
            ("Córdoba", "San Francisco", "Centro", "departamento", 1),
            ("Córdoba", "San Francisco", "Centro", "departamento", 1),
            ("Córdoba", "San Francisco", "Norte", "casa", 1),
            ("Santa Fe", "San Francisco", "Centro", "departamento", 2),
            ("Córdoba", "Otra Localidad", None, "departamento", 2),
        ], 1):
            c.execute(text("""INSERT INTO propiedades
                (id, direccion, provincia, localidad, barrio, tipo, propietario_id)
                VALUES (:id, :address, :province, :city, :area, :kind, :owner)"""),
                {"id": uid(10+n), "address": f"Calle Ficticia {n}", "province": province,
                 "city": city, "area": area, "kind": kind, "owner": uid(owner)})
        for n, (name, property_number) in enumerate([
            ("Lucia Sintetica", 1), ("Mario Sintetico", 4),
            ("Lucia Desasociada", None), ("Pedro Sintetico", 5),
        ], 1):
            c.execute(text("""INSERT INTO inquilinos
                (id, nombre_completo, dni, email, telefono, estado, propiedad_id)
                VALUES (:id, :name, :dni, :email, '00000000', :state, :property)"""),
                {"id": uid(20+n), "name": name, "dni": str(20000000+n),
                 "email": f"tenant{n}@example.com", "property": uid(10+property_number) if property_number else None,
                 "state": "activo" if property_number else "sin_propiedad_asignada"})
    factory = sessionmaker(bind=engine)
    yield (SqlAlchemyPropiedadesRepository(factory), SqlAlchemyPropietariosRepository(factory),
           SqlAlchemyInquilinosRepository(factory))
    engine.dispose()


@pytest.mark.parametrize(("values", "expected"), [
    ({"tipo": "casa"}, 1), ({"provincia": "Córdoba"}, 4),
    ({"localidad": "  SAN   FRANCISCO "}, 4), ({"barrio": "CENTRO"}, 3),
    ({"propietario": "10000001"}, 3), ({"propietario": "OWNER2@EXAMPLE.COM"}, 2),
    ({"tiene_inquilino_activo": True}, 3), ({"tiene_inquilino_activo": False}, 2),
    ({"localidad": "San"}, 0), ({"propietario": "%"}, 0),
    ({"propietario": "' OR 1=1 --"}, 0), ({"barrio": "' OR 1=1 --"}, 0),
])
def test_property_filters(repos, values, expected):
    items, total = repos[0].list(page=1, page_size=100, search=None,
                               filters=PropertiesListFilters(**values))
    assert len(items) == total == expected


def test_property_combination_pagination_and_parenthesized_search(repos):
    f = PropertiesListFilters(tipo="departamento", provincia="Córdoba", localidad="San Francisco",
                             barrio="Centro", propietario="Ana", tiene_inquilino_activo=False)
    items, total = repos[0].list(page=1, page_size=1, search="San", filters=f)
    assert total == 1 and items[0]["id"] == uid(12)
    items, total = repos[0].list(page=2, page_size=1, search="San", filters=f)
    assert total == 1 and items == []
    items, total = repos[0].list(page=1, page_size=1, search="Bruno",
                               filters=PropertiesListFilters(provincia="Córdoba"))
    assert total == 1 and items[0]["id"] == uid(15)


@pytest.mark.parametrize(("with_properties", "search", "expected"), [
    (True, None, 2), (False, None, 1), (True, "Bruno", 1), (False, "Bruno", 0),
])
def test_owner_filters_do_not_duplicate_owners(repos, with_properties, search, expected):
    items, total = repos[1].list(page=1, page_size=1, search=search,
                               filters=OwnersListFilters(con_inmuebles=with_properties))
    assert total == expected and len(items) == min(1, expected)


@pytest.mark.parametrize(("values", "search", "expected"), [
    ({"estado": "activo"}, None, 3), ({"estado": "sin_propiedad_asignada"}, None, 1),
    ({"provincia": "Córdoba"}, None, 2), ({"localidad": "SAN FRANCISCO"}, None, 2),
    ({"estado": "sin_propiedad_asignada", "provincia": "Córdoba"}, None, 0),
    ({"estado": "activo", "provincia": "Córdoba", "localidad": "San Francisco"}, "Lucia", 1),
    ({"estado": "sin_propiedad_asignada"}, "Lucia", 1),
    ({"localidad": "San"}, None, 0),
])
def test_tenant_filters_use_current_property(repos, values, search, expected):
    items, total = repos[2].list(page=1, page_size=100, search=search,
                               filters=TenantsListFilters(**values))
    assert len(items) == total == expected


@pytest.fixture
def client(repos):
    dependencies = {get_propiedades_service: lambda: PropiedadesService(repos[0]),
                    get_propietarios_service: lambda: PropietariosService(repos[1]),
                    get_inquilinos_service: lambda: InquilinosService(repos[2])}
    app.dependency_overrides.update(dependencies)
    with TestClient(app) as client:
        yield client
    for dependency in dependencies:
        app.dependency_overrides.pop(dependency, None)


@pytest.mark.parametrize(("url", "expected"), [
    ("/propiedades?tipo=departamento&provincia=Córdoba&localidad=San%20Francisco&tiene_inquilino_activo=false", 1),
    ("/propietarios?con_inmuebles=false", 1),
    ("/inquilinos?estado=sin_propiedad_asignada", 1),
])
def test_filtered_endpoints_use_services_and_global_totals(client, url, expected):
    response = client.get(url + "&page_size=1")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == expected
    assert len(response.json()["items"]) == min(1, expected)


@pytest.mark.parametrize("url", [
    "/propiedades?tipo=castillo", "/propiedades?provincia=Atlantida",
    "/propiedades?tiene_inquilino_activo=quizas", "/propietarios?con_inmuebles=quizas",
    "/inquilinos?estado=desconocido", "/propiedades?barrio=" + "x"*101,
])
def test_invalid_filter_returns_422(client, url):
    assert client.get(url).status_code == 422


@pytest.mark.parametrize("path", ["propiedades", "propietarios", "inquilinos"])
def test_filters_do_not_bypass_session(client, path):
    app.dependency_overrides.pop(require_admin, None)
    assert client.get("/"+path).status_code == 401
