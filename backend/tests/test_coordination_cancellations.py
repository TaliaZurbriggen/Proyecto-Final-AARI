"""Contrato HU24 aislado: no DB compartida, SMTP, Gemini ni Meta."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from app.api.auth import get_current_user
from app.api.coordination_cancellations import get_cancellations
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.coordination_cancellations import CoordinationCancellationRequest
from app.services.coordination_cancellations import cancellation_reason
from app.services.quote_portal import QuotePortalError


def body(**changes):
    return {'request_id':str(uuid4()),'eleccion_id':str(uuid4()),
            'expected_updated_at':datetime.now(timezone.utc).isoformat(),'confirmar':True,**changes}


@pytest.mark.parametrize('changes',[
    {'confirmar':'true'},{'confirmar':1},{'expected_updated_at':'2026-11-03T12:00:00'},
    {'usuario_id':str(uuid4())},{'proveedor_id':str(uuid4())},{'etapa':'visita_programada'},
    {'estado':'Autorizado'},{'eleccion_id':'no-es-uuid'},
])
def test_rejects_forged_identity_stage_and_ambiguous_confirmation(changes):
    with pytest.raises(ValidationError):
        CoordinationCancellationRequest(**body(**changes))


@pytest.mark.parametrize('state',['Visita programada','Resuelto','Autorizado','Pendiente de datos de proveedor propio','Sin presupuestos recibidos'])
def test_closed_or_unapproved_stages_are_not_cancelled(state):
    assert cancellation_reason({'estado':state,'solicitud_estado':'decidida','tipo_proveedor':'fidelizado'},
                               authorized=True,visit_scheduled=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AARI_CANCELLATIONS_ENABLED','true')
    user=AuthenticatedUser(id=uuid4(),email='tenant@example.com',rol='inquilino',primer_ingreso=False,perfil_id=uuid4())
    calls=[]
    repo=SimpleNamespace(get=lambda *a:calls.append(a) or {'puede_cancelar':True},
                         cancel=lambda *a:calls.append(a) or {'estado_resultante':'Pendiente de respuesta del responsable'})
    app.dependency_overrides[get_current_user]=lambda:user
    app.dependency_overrides[get_cancellations]=lambda:repo
    with TestClient(app) as http:
        yield http,user,repo,calls
    app.dependency_overrides.pop(get_current_user,None)
    app.dependency_overrides.pop(get_cancellations,None)


def test_authenticated_contract_and_no_store(client):
    http,user,_,calls=client
    claim=uuid4()
    for response in (http.get(f'/reclamos/{claim}/cancelacion-coordinacion'),
                     http.post(f'/reclamos/{claim}/cancelacion-coordinacion',json=body())):
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert calls[-1][0]==claim and calls[-1][1] is user


@pytest.mark.parametrize('role',['proveedor','operador','administrador'])
def test_other_roles_cannot_cancel(client,role):
    http,user,_,calls=client
    app.dependency_overrides[get_current_user]=lambda:user.model_copy(update={'rol':role})
    assert http.post(f'/reclamos/{uuid4()}/cancelacion-coordinacion',json=body()).status_code==403
    assert not calls


def test_conflict_and_opt_in_are_controlled(client,monkeypatch):
    http,_,repo,_=client
    def fail(*a): raise QuotePortalError('La visita ya está programada.',code='cancellation_conflict')
    repo.cancel=fail
    assert http.post(f'/reclamos/{uuid4()}/cancelacion-coordinacion',json=body()).status_code==409
    monkeypatch.setenv('AARI_CANCELLATIONS_ENABLED','false')
    assert http.get(f'/reclamos/{uuid4()}/cancelacion-coordinacion').status_code==503
