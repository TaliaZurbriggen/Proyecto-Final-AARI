"""HU17: reglas, grafo y contratos HTTP sin canales externos."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.agents.provider_choice import provider_choice_graph
from app.api.auth import get_current_user
from app.api.provider_choices import get_provider_choices_repository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.provider_choices import ProviderChoiceRequest
from app.services.provider_choices_service import (
    ProviderChoiceConflict, ProviderChoiceNotFound, can_choose, ensure_choice_allowed,
)

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("choice,state,next_step", [
    ("fidelizado", "Pendiente de asignación", "solicitar_presupuestos"),
    ("propio", "Pendiente de datos de proveedor propio", "registrar_proveedor_propio"),
])
def test_deterministic_graph_has_explicit_next_stage(choice, state, next_step):
    result = provider_choice_graph.invoke({"tipo_proveedor": choice})
    assert result["estado_resultante"] == state and result["siguiente_paso"] == next_step
    assert result["estado_resultante"] != "Derivado a proveedor externo"


def test_graph_rejects_unknown_choice():
    with pytest.raises(ValueError):
        provider_choice_graph.invoke({"tipo_proveedor": "inventado"})


@pytest.mark.parametrize("expense,actor,state,seconds,allowed", [
    ("ordinario", "inquilino", "Pendiente de respuesta del responsable", 1, True),
    ("extraordinario", "propietario", "Autorizado", 1, True),
    ("extraordinario", "propietario", "Pendiente de respuesta del responsable", 1, False),
    ("expensa", "inquilino", "Pendiente de respuesta del responsable", 1, False),
    ("ordinario", "propietario", "Autorizado", 1, False),
    ("ordinario", "inquilino", "Pendiente de respuesta del responsable", 0, False),
    ("ordinario", "inquilino", "Pendiente de respuesta del responsable", -1, False),
    ("ordinario", "inquilino", "Resuelto", 1, False),
])
def test_stage_and_exact_deadline(expense, actor, state, seconds, allowed):
    assert can_choose(dict(tipo_gasto=expense, actor_tipo=actor, estado=state,
        solicitud_estado="pendiente", respuesta_vence_en=NOW+timedelta(seconds=seconds)), NOW) is allowed


def test_request_rejects_identity_and_naive_version():
    base = dict(request_id=uuid4(), solicitud_id=uuid4(), tipo_proveedor="propio", expected_updated_at=NOW)
    for extra in ({"usuario_id": uuid4()}, {"rol": "propietario"}, {"tipo_proveedor": "inventado"},
                  {"expected_updated_at": NOW.replace(tzinfo=None)}):
        with pytest.raises(ValidationError):
            ProviderChoiceRequest(**{**base, **extra})


def test_wrong_generation_and_version_are_rejected():
    body = ProviderChoiceRequest(request_id=uuid4(), solicitud_id=uuid4(), tipo_proveedor="propio", expected_updated_at=NOW)
    row = dict(tipo_gasto="ordinario", actor_tipo="inquilino", estado="Pendiente de respuesta del responsable",
        solicitud_estado="pendiente", respuesta_vence_en=NOW+timedelta(hours=72), updated_at=NOW, solicitud_id=uuid4())
    with pytest.raises(ProviderChoiceConflict):
        ensure_choice_allowed(row, body, NOW)


class FakeRepository:
    def choose(self, claim, user, body):
        routed = provider_choice_graph.invoke({"tipo_proveedor": body.tipo_proveedor})
        return dict(reclamo_id=claim, solicitud_id=body.solicitud_id, tipo_proveedor=body.tipo_proveedor,
                    estado=routed["estado_resultante"], siguiente_paso=routed["siguiente_paso"],
                    actor_nombre="Actor Sintético", decidido_en=NOW)

    def get(self, *args):
        raise ProviderChoiceNotFound


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="actor@example.com", rol="inquilino", primer_ingreso=False, perfil_id=uuid4())
    app.dependency_overrides[get_provider_choices_repository] = FakeRepository
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_provider_choices_repository, None)


@pytest.mark.parametrize("role", ["inquilino", "propietario"])
@pytest.mark.parametrize("choice", ["fidelizado", "propio"])
def test_http_accepts_explicit_choice_from_supported_roles(client, role, choice):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="actor@example.com", rol=role, primer_ingreso=False, perfil_id=uuid4())
    response = client.post(f"/reclamos/{uuid4()}/tipo-proveedor", json=dict(request_id=str(uuid4()),
        solicitud_id=str(uuid4()), tipo_proveedor=choice, expected_updated_at=NOW.isoformat()))
    assert response.status_code == 200 and response.json()["tipo_proveedor"] == choice


@pytest.mark.parametrize("role,first_login", [("administrador", False), ("operador", False), ("inquilino", True)])
def test_http_forbids_other_roles_and_first_login(client, role, first_login):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="actor@example.com", rol=role, primer_ingreso=first_login, perfil_id=uuid4())
    assert client.get(f"/reclamos/{uuid4()}/tipo-proveedor").status_code == 403


def test_http_404_422_and_anonymous(client):
    path = f"/reclamos/{uuid4()}/tipo-proveedor"
    assert client.get(path).status_code == 404
    assert client.post(path, json={"tipo_proveedor": "propio"}).status_code == 422
    app.dependency_overrides.pop(get_current_user)
    assert client.get(path).status_code == 401
