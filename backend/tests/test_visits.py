"""Contratos HTTP, reloj y subgrafo HU23 sin APIs externas."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.visits import router, participant, get_visits
from app.agents.coordination.visits import TRANSITIONS, visit_graph
from app.schemas.auth import AuthenticatedUser
from app.schemas.visits import VisitOption, AvailabilityRequest, VisitConfirmationRequest
from app.services.visits import VisitError, reminder_due, validate_options


@pytest.mark.parametrize('source,action',list(TRANSITIONS))
def test_graph_allowed_transitions(source,action):
    assert visit_graph.invoke({'etapa':source,'accion':action})['etapa']==TRANSITIONS[source,action]


@pytest.mark.parametrize('source,action',[('confirmada','confirmar'),('esperando_disponibilidad','confirmar'),('negociando','disponibilidad')])
def test_graph_never_skips_steps(source,action):
    with pytest.raises(ValueError): visit_graph.invoke({'etapa':source,'accion':action})


@pytest.mark.parametrize('offset,expected',[(25,False),(24,True),(23,True),(1,False),(-1,False)])
def test_reminders_are_not_retroactive_or_after_visit(offset,expected):
    visit=datetime(2026,11,20,18,tzinfo=timezone.utc)
    now=visit-timedelta(hours=offset)
    assert reminder_due(visit-timedelta(days=3),visit,now,24)==(offset<=24 and offset>0)
    assert reminder_due(visit-timedelta(hours=12),visit,now,24) is False


def test_day_validation_uses_argentina_not_server_utc_date():
    now=datetime(2026,11,1,tzinfo=timezone.utc)
    # UTC dates differ, but these two options both belong to 10/11 in Argentina.
    values=[('2026-11-10T20:00:00Z','2026-11-10T21:00:00Z'),('2026-11-11T01:00:00Z','2026-11-11T02:00:00Z'),('2026-11-12T20:00:00Z','2026-11-12T21:00:00Z')]
    with pytest.raises(VisitError): validate_options([VisitOption(desde=a,hasta=b) for a,b in values],now)


@pytest.mark.parametrize('change',[{'fecha':'2026-11-01T15:00:00'},{'version_esperada':True},{'autor_id':str(uuid4())}])
def test_payload_rejects_naive_dates_boolean_versions_and_chosen_authors(change):
    data=dict(request_id=uuid4(),coordinacion_id=uuid4(),version_esperada=0,fecha='2026-11-20T15:00:00-03:00')|change
    with pytest.raises(ValidationError): VisitConfirmationRequest(**data)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AARI_VISITS_ENABLED','true')
    app=FastAPI()
    app.include_router(router)
    user=AuthenticatedUser(id=uuid4(),email='tenant@example.com',rol='inquilino',primer_ingreso=False,perfil_id=uuid4())
    app.dependency_overrides[participant]=lambda:user
    class Repo:
        def get(self,claim,user): return {'id':str(claim),'etapa':'esperando_disponibilidad'}
        def list_own(self,user,**kw): return {'items':[],**kw,'total':0}
    repo=Repo()
    app.dependency_overrides[get_visits]=lambda:repo
    return TestClient(app),repo


def test_http_no_store_and_read_does_not_start_coordination(client):
    http,_=client
    assert http.get('/reclamos/visitas/propias').status_code==200
    response=http.get(f'/reclamos/{uuid4()}/visita')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('failure',[VisitError('No disponible',status=404),SQLAlchemyError('private-connection-data')])
def test_errors_no_store_and_storage_diagnostics_are_not_exposed(client,failure):
    http,repo=client
    def fail(*a): raise failure
    repo.get=fail
    response=http.get(f'/reclamos/{uuid4()}/visita')
    assert response.status_code in {404,503} and response.headers['cache-control']=='no-store'
    assert 'private-connection-data' not in response.text


def test_disabled_feature_does_not_call_repository(client,monkeypatch):
    monkeypatch.setenv('AARI_VISITS_ENABLED','false')
    assert client[0].get(f'/reclamos/{uuid4()}/visita').json()['detail']['code']=='visits_disabled'
