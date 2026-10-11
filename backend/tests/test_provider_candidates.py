"""HU15: permisos, validación y algoritmo, sin redes ni datos reales."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine, text

from app.api.auth import get_current_user
from app.api.provider_candidates import get_candidates_repository
from app.db.proveedores import SqlAlchemyProveedoresRepository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.provider_candidates import CandidateSearchExecution, CandidateSearchRequest
from app.services.provider_candidates_service import (
    CandidateClaimNotFoundError, CandidateSearchConflictError, CandidateSearchPermissionError,
    CandidateSpecialtyNotFoundError, ProviderCandidatesService, ensure_search_stage, search_inputs,
)

VERSION = datetime(2026, 10, 9, 12, tzinfo=UTC)
CLAIM = uuid4()
SPECIALTY = uuid4()


def payload():
    return {"request_id": str(uuid4()), "especialidad_id": str(SPECIALTY),
            "expected_updated_at": VERSION.isoformat()}


class Repository:
    def __init__(self):
        self.calls = []
        self.error = None

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return {"items": [], "total": 0, "total_pages": 1, **{k: v for k, v in kwargs.items() if k != "search"}}

    def specialties(self):
        self.calls.append(("specialties",))
        return [{"id": str(SPECIALTY), "nombre": "Plomería"}]

    def get(self, claim_id, **kwargs):
        self.calls.append(("get", claim_id))
        raise CandidateClaimNotFoundError

    def search(self, claim_id, request, **kwargs):
        if self.error:
            raise self.error
        self.calls.append(("search", claim_id, request, kwargs))
        return CandidateSearchExecution(busqueda_id=uuid4(), resultado="candidatos_encontrados",
                                        candidato_ids=[uuid4()], aviso_operador="no_aplica")


@pytest.fixture
def api():
    repo = Repository()
    app.dependency_overrides[get_candidates_repository] = lambda: repo
    def login(role="administrador", first=False):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=UUID(int=1), email="staff@example.com", rol=role, primer_ingreso=first,
        )
    login()
    yield TestClient(app), repo, login
    for dep in (get_current_user, get_candidates_repository):
        app.dependency_overrides.pop(dep, None)


@pytest.mark.parametrize("role", ["administrador", "operador"])
def test_staff_reads_catalog_and_records_explicit_search(api, role):
    client, repo, login = api
    login(role)
    assert client.get("/reclamos/pendientes-asignacion?page=2&page_size=3&search=canilla").status_code == 200
    assert repo.calls[0] == ("list", {"page": 2, "page_size": 3, "search": "canilla"})
    assert client.get("/reclamos/especialidades-proveedores").json()[0]["nombre"] == "Plomería"
    body = payload()
    response = client.post(f"/reclamos/{CLAIM}/buscar-proveedores", json=body)
    assert response.status_code == 200 and not response.json()["repetida"]
    assert repo.calls[-1][-1] == {"origin": role, "user_id": UUID(int=1)}


PATHS = ["/reclamos/pendientes-asignacion", "/reclamos/especialidades-proveedores",
         f"/reclamos/{CLAIM}/proveedores-candidatos", f"/reclamos/{CLAIM}/buscar-proveedores"]


@pytest.mark.parametrize("role,first", [("inquilino", False), ("propietario", False), ("operador", True)])
@pytest.mark.parametrize("path", PATHS)
def test_no_public_provider_contacts_or_spoofed_staff(api, role, first, path):
    client, repo, login = api
    login(role, first)
    result = client.post(path, json=payload()) if path.endswith("buscar-proveedores") else client.get(path)
    assert result.status_code == 403 and not repo.calls


@pytest.mark.parametrize("path", PATHS)
def test_session_is_required(api, path):
    client, repo, _ = api
    app.dependency_overrides.pop(get_current_user)
    result = client.post(path, json=payload()) if path.endswith("buscar-proveedores") else client.get(path)
    assert result.status_code == 401 and not repo.calls


@pytest.mark.parametrize("changes", [
    {"expected_updated_at": "2026-10-09T12:00:00"}, {"request_id": "123"},
    {"especialidad_id": "electricidad"}, {"origen": "agente"},
    {"autorizado": True}, {"tipo_gasto": "ordinario"}, {"usuario_id": str(uuid4())},
])
def test_invalid_command_cannot_bypass_decisions(api, changes):
    client, repo, _ = api
    assert client.post(f"/reclamos/{CLAIM}/buscar-proveedores", json={**payload(), **changes}).status_code == 422
    assert not repo.calls


@pytest.mark.parametrize("error,status", [
    (CandidateSearchConflictError("Actualizá."), 409), (CandidateSearchPermissionError(), 403),
    (CandidateSpecialtyNotFoundError(), 422), (CandidateClaimNotFoundError(), 404),
])
def test_safe_error_contract(api, error, status):
    client, repo, _ = api
    repo.error = error
    response = client.post(f"/reclamos/{CLAIM}/buscar-proveedores", json=payload())
    assert response.status_code == status and not repo.calls
    if status == 422:
        assert response.json()["detail"]["field"] == "especialidad_id"


def test_get_is_not_a_search_command(api):
    client, repo, _ = api
    assert client.get(f"/reclamos/{CLAIM}/proveedores-candidatos").status_code == 404
    assert repo.calls == [("get", CLAIM)]
    assert client.get("/reclamos/pendientes-asignacion?page=0").status_code == 422


@pytest.mark.parametrize("state", ["Resuelto", "Rechazado por propietario", "Derivado a proveedor externo", "Sesión expirada"])
def test_closed_claims_cannot_record_search(state):
    row = {"estado": "Pendiente de asignación", "tipo_gasto": "ordinario",
           "has_responsible": True, "proveedor_seleccionado_id": None}
    with pytest.raises(CandidateSearchConflictError):
        ensure_search_stage({**row, "estado": state})
    ensure_search_stage(row)


@pytest.mark.parametrize("state", ["Recibido", "Escalado", "Autorizado", "Pendiente de respuesta del responsable"])
def test_preliminary_search_needs_no_authorization_or_responsible(state):
    ensure_search_stage({"estado": state, "tipo_gasto": None,
                         "has_responsible": False, "proveedor_seleccionado_id": None})


def test_missing_specialty_or_location_is_explicit():
    row = {"provincia": " Córdoba ", "localidad": " San   Francisco ", "barrio": None}
    normalized, reason = search_inputs(row, None)
    assert reason == "especialidad_pendiente" and normalized["localidad"] == "San Francisco"
    assert search_inputs({**row, "localidad": " "}, SPECIALTY)[1] == "ubicacion_incompleta"
    assert search_inputs(row, SPECIALTY)[1] is None


def test_internal_agent_port_is_not_an_http_authorization():
    repo = Repository()
    service = ProviderCandidatesService(repo)
    service.search_from_coordination(CLAIM, CandidateSearchRequest(**payload()))
    assert repo.calls[0][-1] == {"origin": "agente", "user_id": None}
    with pytest.raises(CandidateSearchPermissionError):
        service.search(CLAIM, CandidateSearchRequest(**payload()), AuthenticatedUser(
            id=uuid4(), email="tenant@example.com", rol="inquilino", primer_ingreso=False,
        ))


@pytest.fixture
def candidate_sql():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE proveedores (id TEXT PRIMARY KEY, nombre_razon_social TEXT, activo BOOLEAN)"))
        c.execute(text("CREATE TABLE proveedor_especialidades (proveedor_id TEXT, especialidad_id TEXT)"))
        c.execute(text("CREATE TABLE proveedor_coberturas (id TEXT, proveedor_id TEXT, provincia TEXT, localidad TEXT, cubre_toda_localidad BOOLEAN)"))
        c.execute(text("CREATE TABLE proveedor_cobertura_barrios (cobertura_id TEXT, barrio TEXT)"))
        cases = [
            ("1", True, "Córdoba", "San Francisco", True, None, True),
            ("2", True, "Córdoba", "San Francisco", False, "Centro", True),
            ("3", True, "Santa Fe", "San Francisco", True, None, True),
            ("4", True, "Córdoba", "Otra localidad", True, None, True),
            ("5", False, "Córdoba", "San Francisco", True, None, True),
            ("6", True, "Córdoba", "San Francisco", True, None, False),
            ("7", True, "Córdoba", "San Francisco del Monte", True, None, True),
            ("8", True, "Córdoba", "San Francisco", False, "Centro Norte", True),
        ]
        for id, active, province, city, all_city, area, specialty in cases:
            c.execute(text("INSERT INTO proveedores VALUES (:id, :name, :active)"), {"id": id, "name": id, "active": active})
            if specialty:
                c.execute(text("INSERT INTO proveedor_especialidades VALUES (:id, :s)"), {"id": id, "s": str(SPECIALTY)})
            c.execute(text("INSERT INTO proveedor_coberturas VALUES (:id, :id, :p, :c, :all)"),
                      {"id": id, "p": province, "c": city, "all": all_city})
            if area:
                c.execute(text("INSERT INTO proveedor_cobertura_barrios VALUES (:id, :area)"), {"id": id, "area": area})
        # Otra cobertura del mismo proveedor no duplica ni mezcla geografías.
        c.execute(text("INSERT INTO proveedor_coberturas VALUES ('extra', '2', 'Santa Fe', 'Otra localidad', true)"))
        yield c
    engine.dispose()


@pytest.mark.parametrize("city,area,expected", [
    ("San Francisco", "Centro", ["1", "2"]), ("san francisco", "centro", ["1", "2"]),
    ("San Francisco", None, ["1"]), ("San Francisco", "Barrio inexistente", ["1"]),
    ("San Francisco", "Centro Norte", ["1", "8"]), ("San", "Centro", []),
    ("Otra localidad", "Centro", ["4"]), ("San Francisco del Monte", "Centro", ["7"]),
    ("' OR 1=1 --", "Centro", []), ("San Francisco", "%", ["1"]),
])
def test_exact_geography_specialty_active_and_unique(candidate_sql, city, area, expected):
    result = SqlAlchemyProveedoresRepository.candidate_ids(
        candidate_sql, specialty_id=SPECIALTY, provincia="Córdoba", localidad=city, barrio=area,
    )
    assert result == expected
