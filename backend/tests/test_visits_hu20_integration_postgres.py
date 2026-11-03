"""Rutas HTTP y checkpoints reales con identidades ficticias locales, sin SMTP/LLM.

Se sustituye sólo la resolución de la sesión autenticada, no las decisiones,
repositorios, permisos de dominio, migraciones ni el grafo de HU21.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
from psycopg.rows import dict_row
import pytest
from sqlalchemy.orm import sessionmaker

from app.api.auth import get_current_user
from app.api import conversations, quote_selections, visits
from app.db.conversations import SqlAlchemyConversations
from app.db.coordination import PostgresCoordinationRepository
from app.agents.coordination.state import ResumeRequest
from app.schemas.visits import AvailabilityRequest, VisitConfirmationRequest
from app.services.coordination_service import CoordinationError
from scripts.check_coordination_postgres import apply, verify
from tests.test_visits_postgres import prepare_visits, options, action
from tests.test_quote_portal_postgres import portal_case, scalar
from tests.test_provider_choices_postgres import choice_base
from tests.test_responsible_actor_postgres import local_engine, claim_case

pytestmark=pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'),reason='Sólo PostgreSQL local descartable.')


def wire(value):
    return json.loads(json.dumps(value,default=str))


@pytest.mark.parametrize('expense',['ordinario','extraordinario'])
@pytest.mark.parametrize('kind',['exacto','minimo'])
@pytest.mark.parametrize('negotiate',[False,True])
def test_http_selection_to_confirmed_visit_with_real_domain(portal_case,monkeypatch,expense,kind,negotiate):
    c=prepare_visits(portal_case,monkeypatch,expense,kind=kind)
    app=FastAPI()
    for router in (quote_selections.router,visits.router,conversations.router): app.include_router(router)
    current=[c.actor]
    app.dependency_overrides[get_current_user]=lambda:current[0]
    app.dependency_overrides[quote_selections.get_quote_selections]=lambda:c.selection
    app.dependency_overrides[visits.get_visits]=lambda:c.visits
    app.dependency_overrides[conversations.get_conversations]=lambda:SqlAlchemyConversations(sessionmaker(bind=c.db))
    path=f'/reclamos/{c.claim}/visita'
    selection_path=f'/reclamos/{c.claim}/seleccion-presupuesto'
    with TestClient(app) as http:
        saved=http.post(selection_path,json=c.selection_payload.model_dump(mode='json'))
        assert saved.status_code==200 and saved.json()['tipo_importe']==kind
        assert http.get(selection_path).json()['coordinacion_url']==f'/visitas/{c.claim}'
        assert scalar(c,'SELECT count(*) FROM visitas')==0
        # Descubrimiento posterior al commit de la selección; se puede reintentar.
        c.visits.tick()
        c.visits.tick()
        current[0]=c.tenant
        detail=http.get(path)
        assert detail.status_code==200 and detail.headers['cache-control']=='no-store'
        assert detail.json()['acciones']==['disponibilidad']
        availability=AvailabilityRequest(**action(c),opciones=options())
        posted=http.post(path+'/disponibilidad',json=availability.model_dump(mode='json'))
        assert posted.status_code==200 and posted.json()['etapa']=='esperando_confirmacion'
        deadline=posted.json()['vence_en']
        current[0]=c.provider
        if negotiate:
            thread=posted.json()['hilo_id']
            message={'request_id':str(uuid4()),'texto':'Propongo otro día, sin confirmar por texto.'}
            assert http.post(f'/conversaciones/hilos/{thread}/mensajes',json=message).status_code==403
            assert http.post(path+'/sin-coincidencia',json=wire(action(c,c.provider))).status_code==200
            assert http.post(f'/conversaciones/hilos/{thread}/mensajes',json=message).status_code==200
            current[0]=c.tenant
            proposed=http.post(path+'/proponer',json=wire({**action(c),'fecha':(options()[0].desde+timedelta(days=10)).isoformat()}))
            assert proposed.status_code==200
            version=proposed.json()['propuesta']['version']
            assert http.post(path+'/confirmar',json=wire({**action(c),'propuesta_version':version})).status_code==409
            current[0]=c.provider
            payload={**action(c,c.provider),'propuesta_version':version}
        else:
            payload={**action(c,c.provider),'fecha':availability.opciones[1].desde.isoformat()}
        # UUID y fecha se serializan igual que en una petición de red.
        payload=wire(payload)
        confirmed=http.post(path+'/confirmar',json=payload)
        assert confirmed.status_code==200 and confirmed.json()['etapa']=='confirmada'
        assert confirmed.json()['vence_en']==deadline
        assert http.post(path+'/confirmar',json=payload).json()['repetida']
        current[0]=c.actor
        comparison=http.get(selection_path).json()
        assert comparison['estado']=='Visita programada'
        assert comparison['decision']['estado_resultante']=='Proveedor seleccionado'
        assert comparison['coordinacion_url']==f'/visitas/{c.claim}'
        assert http.post(selection_path,json=c.selection_payload.model_dump(mode='json')).json()['repetida']
    c.visits.tick()
    assert scalar(c,'SELECT count(*) FROM visitas')==1
    assert scalar(c,'SELECT count(*) FROM aari_visita_coordinaciones')==1
    assert scalar(c,'SELECT count(*) FROM reclamo_selecciones_presupuesto')==1


def test_hu21_keeps_selection_and_does_not_expire_hu23_specific_wait(portal_case,monkeypatch):
    c=prepare_visits(portal_case,monkeypatch,'extraordinario')
    url=c.db.url
    def connect():
        return psycopg.connect(host=url.host,port=url.port,dbname=url.database,
            user=url.username,password=url.password,row_factory=dict_row,prepare_threshold=None)
    with connect() as conn:
        apply(conn)
        verify(conn)
    now=datetime.now(timezone.utc)
    repo=PostgresCoordinationRepository(connect,clock=lambda:now)
    first=repo.resume(c.claim,ResumeRequest(evento_id=uuid4(),version_esperada=0),c.actor)
    chosen=c.selection.choose(c.claim,c.actor,c.selection_payload)
    assert repo.get(c.claim,c.actor).requiere_sincronizacion
    selected=repo.resume(c.claim,ResumeRequest(evento_id=uuid4(),version_esperada=first.contexto.version,
        intento_id=first.contexto.intento_id),c.actor)
    assert selected.contexto.etapa=='esperando_disponibilidad'
    assert selected.contexto.dominio.presupuesto_id==chosen['presupuesto_id']
    assert selected.contexto.dominio.proveedor_id==chosen['proveedor_id']
    c.visits.tick()
    slots=AvailabilityRequest(**action(c),opciones=options())
    c.visits.act(c.claim,c.tenant,'disponibilidad',slots)
    deadline=scalar(c,'SELECT vence_en FROM aari_visita_coordinaciones')
    future=PostgresCoordinationRepository(connect,clock=lambda:now+timedelta(hours=100))
    assert future.expire_due()==0
    assert scalar(c,'SELECT estado FROM reclamos')=='Proveedor seleccionado'
    assert scalar(c,'SELECT vence_en FROM aari_visita_coordinaciones')==deadline
    c.visits.act(c.claim,c.provider,'confirmar',VisitConfirmationRequest(**action(c,c.provider),fecha=slots.opciones[0].desde))
    fresh=PostgresCoordinationRepository(connect,clock=lambda:now)
    latest=fresh.get(c.claim,c.actor)
    assert latest.requiere_sincronizacion and latest.estado_reclamo_actual=='Visita programada'
    # HU21 informa la diferencia, pero resume no admite estados terminales.
    # El adaptador automático de checkpoint terminal sigue siendo AARI-345;
    # no se falsea una sincronización escribiendo sesiones/checkpoints a mano.
    with pytest.raises(CoordinationError):
        fresh.resume(c.claim,ResumeRequest(evento_id=uuid4(),version_esperada=selected.contexto.version,
            intento_id=selected.contexto.intento_id),c.actor)
    assert scalar(c,'SELECT estado FROM reclamos')=='Visita programada'
