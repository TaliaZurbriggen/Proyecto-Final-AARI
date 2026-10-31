"""HU18: contratos y permisos HTTP reales con repositorio simulado, sin red."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import get_current_user
from app.api.external_providers import get_external_providers_repository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.external_providers import ExternalProviderRequest, normalize_external_name, normalize_external_phone
from app.services.external_providers_service import ExternalProviderError, registration_reason

NOW = datetime(2026, 10, 29, 18, tzinfo=timezone.utc)


def payload(**changes):
    return {"request_id": str(uuid4()), "eleccion_id": str(uuid4()), "expected_updated_at": NOW.isoformat(),
            "nombre": "Persona Sintética", "telefono": "+54 (11) 5555-0100", **changes}


@pytest.mark.parametrize("raw,expected", [("12345678", "12345678"), (" +54 (11) 5555-0100 ", "541155550100"),
    ("123456789012345", "123456789012345"), ("00000001", "00000001")])
def test_phone_formats(raw, expected):
    assert normalize_external_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "1234567", "1234567890123456", "abcdefghi", "1234hola5678", "54+1155550100", "++12345678", "１２３４５６７８", "12345678x99", "12345678\n99"])
def test_invalid_phone(raw):
    with pytest.raises(ValueError): normalize_external_phone(raw)


@pytest.mark.parametrize("raw", ["", "43428013", "Juan123", "Ana <script>", "A" * 121, "---"])
def test_invalid_names(raw):
    with pytest.raises(ValueError): normalize_external_name(raw)


def test_name_normalization_unicode_and_apostrophes():
    assert normalize_external_name("  Jose\u0301   D’Angelo  ") == "José D’Angelo"
    assert normalize_external_name("Ana-María Pérez") == "Ana-María Pérez"


@pytest.mark.parametrize("changes", [{"usuario_id": str(uuid4())}, {"rol": "administrador"},
    {"expected_updated_at": "2026-10-29T18:00:00"}, {"nombre": 12345678}, {"telefono": 12345678}])
def test_request_rejects_forged_identity_naive_time_and_wrong_types(changes):
    with pytest.raises(ValidationError): ExternalProviderRequest(**payload(**changes))


def row(**changes):
    return {"eleccion_estado": "decidida", "tipo_proveedor": "propio", "estado": "Pendiente de datos de proveedor propio",
            "presupuesto_seleccionado_id": None, "proveedor_seleccionado_id": None, **changes}


def test_own_choice_and_quote_alternative_have_explicit_stages():
    assert registration_reason(row()) is None
    assert registration_reason(row(tipo_proveedor="fidelizado", estado="Pendiente de asignación", ronda_estado="esperando", presupuestos_disponibles=1)) is None
    assert registration_reason(row(tipo_proveedor="fidelizado", estado="Sin presupuestos recibidos", ronda_estado="sin_presupuestos")) is None


@pytest.mark.parametrize("changes", [{"eleccion_estado": "pendiente"}, {"estado": "Resuelto"}, {"estado": "Autorizado"},
    {"proveedor_seleccionado_id": uuid4()}, {"presupuesto_seleccionado_id": uuid4()},
    {"tipo_proveedor": "fidelizado", "estado": "Pendiente de asignación", "ronda_estado": "esperando"},
    {"tipo_proveedor": "fidelizado", "estado": "Pendiente de asignación", "ronda_estado": "cancelada", "presupuestos_disponibles": 1}])
def test_invalid_stages(changes):
    assert registration_reason(row(**changes)) is not None
    assert registration_reason(row(), registered=True) is not None


class FakeRepository:
    def get(self, claim, user):
        raise ExternalProviderError("No encontramos ese reclamo.", status=404, code="not_found")

    def register(self, claim, user, body):
        return {"reclamo_id": claim, "estado": "Derivado a proveedor externo", "registro": {
            "id": uuid4(), "eleccion_id": body.eleccion_id, "nombre": body.nombre, "telefono": body.telefono,
            "created_at": NOW, "actor_nombre": "Actor Sintético"}}


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: actor()
    app.dependency_overrides[get_external_providers_repository] = FakeRepository
    with TestClient(app) as client: yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_external_providers_repository, None)


def actor(role="inquilino", first=False):
    return AuthenticatedUser(id=uuid4(), email="actor@example.com", rol=role, primer_ingreso=first, perfil_id=uuid4())


@pytest.mark.parametrize("role", ["inquilino", "propietario"])
def test_http_registers_normalized_contact_for_supported_roles(client, role):
    app.dependency_overrides[get_current_user] = lambda: actor(role)
    response = client.post(f"/reclamos/{uuid4()}/proveedor-externo", json=payload())
    assert response.status_code == 200
    assert response.json()["registro"]["telefono"] == "541155550100"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("role,first", [("administrador", False), ("operador", False), ("proveedor", False), ("inquilino", True)])
def test_http_forbids_other_writers(client, role, first):
    app.dependency_overrides[get_current_user] = lambda: actor(role, first)
    assert client.post(f"/reclamos/{uuid4()}/proveedor-externo", json=payload()).status_code == 403


def test_http_404_validation_anonymous_and_storage_errors(client):
    path = f"/reclamos/{uuid4()}/proveedor-externo"
    assert client.get(path).status_code == 404
    assert client.post(path, json=payload(nombre="43428013")).status_code == 422
    class Broken(FakeRepository):
        def get(self, *args): raise SQLAlchemyError("Private connection must not be shown")
    app.dependency_overrides[get_external_providers_repository] = Broken
    response = client.get(path)
    assert response.status_code == 503 and "Private connection" not in response.text
    app.dependency_overrides.pop(get_current_user)
    assert client.get(path).status_code == 401
