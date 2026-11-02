"""HU20: contratos HTTP aislados, sin SMTP, LLM ni base compartida."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.api.auth import get_current_user
from app.api.quote_selections import get_quote_selections
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.quote_selections import QuoteSelectionRequest
from app.services.quote_portal import QuotePortalError


def body(**changes):
    return {'request_id': str(uuid4()), 'ronda_id': str(uuid4()),
            'expected_updated_at': datetime.now(timezone.utc).isoformat(),
            'modalidad': 'fidelizado', 'presupuesto_id': str(uuid4()), **changes}


@pytest.mark.parametrize('changes', [
    {'modalidad': 'propio'}, {'presupuesto_id': None}, {'modalidad': 'automatico'},
    {'monto': '10'}, {'usuario_id': str(uuid4())}, {'proveedor_id': str(uuid4())},
    {'expected_updated_at': '2026-10-01T12:00:00'}, {'ronda_id': 'otra'},
])
def test_rejects_forged_or_ambiguous_selection(changes):
    with pytest.raises(ValidationError):
        QuoteSelectionRequest(**body(**changes))


def test_own_provider_remains_unavailable_until_hu18_integration():
    with pytest.raises(ValidationError):
        QuoteSelectionRequest(**body(modalidad='propio', presupuesto_id=None))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AARI_QUOTE_PORTAL_ENABLED', 'true')
    user = AuthenticatedUser(id=uuid4(), email='tenant@example.com', rol='inquilino', primer_ingreso=False, perfil_id=uuid4())
    app.dependency_overrides[get_current_user] = lambda: user
    calls = []
    repo = SimpleNamespace(get=lambda *args: calls.append(args) or {'items': []},
                           choose=lambda *args: calls.append(args) or {'estado_resultante': 'Proveedor seleccionado'})
    app.dependency_overrides[get_quote_selections] = lambda: repo
    with TestClient(app) as http:
        yield http, user, repo, calls
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_quote_selections, None)


def test_api_forwards_only_authenticated_identity_and_no_store(client):
    http, user, _, calls = client
    claim = uuid4()
    assert http.get(f'/reclamos/{claim}/seleccion-presupuesto').headers['cache-control'] == 'no-store'
    result = http.post(f'/reclamos/{claim}/seleccion-presupuesto', json=body())
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert calls[-1][0] == claim and calls[-1][1] is user


@pytest.mark.parametrize('role', ['proveedor', 'administrador', 'operador'])
def test_non_responsible_roles_cannot_confirm(client, role):
    http, user, _, calls = client
    app.dependency_overrides[get_current_user] = lambda: user.model_copy(update={'rol': role})
    assert http.post(f'/reclamos/{uuid4()}/seleccion-presupuesto', json=body()).status_code == 403
    assert not calls


def test_disabled_portal_and_conflict_are_controlled(client, monkeypatch):
    http, _, repo, _ = client
    def fail(*args):
        raise QuotePortalError('La selección cambió.', code='selection_conflict')
    repo.choose = fail
    assert http.post(f'/reclamos/{uuid4()}/seleccion-presupuesto', json=body()).status_code == 409
    monkeypatch.setenv('AARI_QUOTE_PORTAL_ENABLED', 'false')
    assert http.get(f'/reclamos/{uuid4()}/seleccion-presupuesto').status_code == 503
