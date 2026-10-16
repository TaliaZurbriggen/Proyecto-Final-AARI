"""Reglas y API HU16: datos ficticios, sin SMTP, modelos ni base compartida."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.api.auth import get_current_user
from app.api.expense_authorizations import get_expense_authorizations_repository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.expense_authorizations import ExpenseDecisionRequest
from app.services.expense_authorizations_service import (
    ExpenseAuthorizationConflict, ExpenseAuthorizationNotFound, can_decide,
    ensure_decision_allowed,
)

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def test_request_requires_aware_version_and_rejects_actor_injection():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=NOW, usuario_id=uuid4())


@pytest.mark.parametrize("state,expense,actor,seconds,expected", [
    ("Pendiente de respuesta del responsable", "extraordinario", "propietario", 1, True),
    ("Pendiente de respuesta del responsable", "extraordinario", "propietario", 0, False),
    ("Pendiente de respuesta del responsable", "extraordinario", "propietario", -1, False),
    ("Autorizado", "extraordinario", "propietario", 1, False),
    ("Pendiente de respuesta del responsable", "ordinario", "inquilino", 1, False),
    ("Pendiente de autorización - vencido", "extraordinario", "propietario", 1, False),
])
def test_decision_stage_and_deadline(state, expense, actor, seconds, expected):
    assert can_decide(state=state, expense=expense, actor=actor,
                      deadline=NOW + timedelta(seconds=seconds), now=NOW) is expected


def test_stale_version_is_rejected():
    row = dict(estado="Pendiente de respuesta del responsable", tipo_gasto="extraordinario",
               actor_tipo="propietario", respuesta_vence_en=NOW + timedelta(hours=1), updated_at=NOW)
    with pytest.raises(ExpenseAuthorizationConflict):
        ensure_decision_allowed(row, NOW - timedelta(seconds=1), NOW)


class FakeRepository:
    def decide(self, claim, user, body, *, decision):
        return dict(reclamo_id=claim, decision=decision,
                    estado="Autorizado" if decision == "autorizar" else "Rechazado por propietario",
                    decidido_en=NOW, propietario_nombre="Titular Sintetico",
                    siguiente_paso="eleccion_proveedor_pendiente" if decision == "autorizar" else "cerrado")

    def get(self, *args):
        raise ExpenseAuthorizationNotFound


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="owner@example.com", rol="propietario", primer_ingreso=False, perfil_id=uuid4())
    app.dependency_overrides[get_expense_authorizations_repository] = FakeRepository
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_expense_authorizations_repository, None)


@pytest.mark.parametrize("decision", ["autorizar", "rechazar"])
def test_both_endpoints_accept_explicit_owner_decision(client, decision):
    result = client.post(f"/reclamos/{uuid4()}/{decision}", json={
        "request_id": str(uuid4()), "expected_updated_at": NOW.isoformat()})
    assert result.status_code == 200
    assert result.json()["decision"] == decision
    assert result.json()["notificacion_estado"] == "pendiente"


@pytest.mark.parametrize("role", ["inquilino", "operador", "administrador"])
def test_other_roles_cannot_decide(client, role):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="actor@example.com", rol=role, primer_ingreso=False)
    assert client.post(f"/reclamos/{uuid4()}/autorizar", json={
        "request_id": str(uuid4()), "expected_updated_at": NOW.isoformat()}).status_code == 403


def test_first_login_and_unknown_claim(client):
    assert client.get(f"/reclamos/{uuid4()}/autorizacion").status_code == 404
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="owner@example.com", rol="propietario", primer_ingreso=True)
    assert client.get("/propietario/reclamos").status_code == 403


def test_bad_version_and_extra_identity_return_422(client):
    base = {"request_id": str(uuid4()), "expected_updated_at": NOW.isoformat()}
    assert client.post(f"/reclamos/{uuid4()}/autorizar", json={**base, "rol": "propietario"}).status_code == 422
    assert client.post(f"/reclamos/{uuid4()}/autorizar", json={**base, "expected_updated_at": "invalid"}).status_code == 422
    assert client.get("/propietario/reclamos?page=0").status_code == 422


def test_anonymous_access_is_not_allowed(client):
    app.dependency_overrides.pop(get_current_user)
    assert client.get("/propietario/reclamos").status_code == 401
