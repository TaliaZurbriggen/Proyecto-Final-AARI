"""Contrato real HU24↔HU23. Se ejecuta al integrar HU23; nunca usa Supabase."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy.orm import sessionmaker

pytest.importorskip('app.db.visits',reason='HU23 aún no está integrada en main.')

from app.db.coordination_cancellations import SqlAlchemyCoordinationCancellations
from app.db.conversations import SqlAlchemyConversations
from app.db.visits import SqlAlchemyVisits
from app.schemas.coordination_cancellations import CoordinationCancellationRequest
from app.schemas.visits import VisitAction,VisitConfirmationRequest
from app.schemas.conversations import ConversationMessageRequest
from app.services.conversations import ConversationError
from app.services.quote_portal import QuotePortalError
from app.services.visits import VisitError
from tests.test_visits_postgres import visit_case,publish,action
from tests.test_quote_portal_postgres import portal_case,budget,scalar
from tests.test_provider_choices_postgres import choice_base,body as choose_body
from tests.test_responsible_actor_postgres import local_engine,claim_case,MIGRATIONS
from tests.test_quote_selections_postgres import selection

pytestmark=pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'),reason='Sólo PostgreSQL local descartable.')


@pytest.fixture
def integrated(visit_case,monkeypatch):
    c=visit_case
    monkeypatch.setenv('AARI_CANCELLATIONS_ENABLED','true')
    with c.db.connect() as conn:
        cur=conn.connection.cursor()
        cur.execute((MIGRATIONS/'20261103120000_hu24_cancelacion_coordinacion.sql').read_text(encoding='utf-8'))
        conn.commit()
        cur.close()
    c.cancel=SqlAlchemyCoordinationCancellations(sessionmaker(bind=c.db))
    return c


def cancellation(c):
    v=c.cancel.get(c.claim,c.actor)
    return CoordinationCancellationRequest(request_id=uuid4(),eleccion_id=v['eleccion_id'],
        expected_updated_at=v['updated_at'],confirmar=True)


@pytest.mark.parametrize('visit_case',['ordinario','extraordinario'],indirect=True)
@pytest.mark.parametrize('stage',['disponibilidad','confirmacion','negociacion'])
def test_invalidates_real_hu23_and_can_start_a_new_visit_attempt(integrated,stage):
    c=integrated
    date=None
    if stage!='disponibilidad':
        data=publish(c)
        date=data.opciones[0].desde
    if stage=='negociacion':
        c.visits.act(c.claim,c.provider,'sin-coincidencia',VisitAction(**action(c,c.provider)))
    detail=c.visits.get(c.claim,c.tenant)
    old_id=detail['id']
    late=VisitConfirmationRequest(**action(c,c.provider),fecha=date) if date else None
    c.cancel.cancel(c.claim,c.actor,cancellation(c))
    assert scalar(c,'SELECT etapa FROM aari_visita_coordinaciones WHERE id=:id',id=old_id)=='invalidada'
    assert scalar(c,'SELECT count(*) FROM visitas')==0
    if late:
        with pytest.raises(VisitError): c.visits.act(c.claim,c.provider,'confirmar',late)
    conversations=SqlAlchemyConversations(sessionmaker(bind=c.db))
    history=conversations.thread_messages(detail['hilo_id'],c.tenant)
    assert not history['puede_enviar'] and any('canceló' in m['texto'] for m in history['items'])
    assert sum(x['id']==detail['hilo_id'] for x in conversations.inbox(c.tenant)['items'])==1
    assert conversations.thread_read(detail['hilo_id'],c.tenant,history['ultimo_numero'])['no_leidos']==0
    with pytest.raises(ConversationError):
        conversations.thread_send(detail['hilo_id'],c.provider,ConversationMessageRequest(request_id=uuid4(),texto='No reactivar.'))
    # Reiniciar repositorio/worker no vuelve a activar la selección anterior.
    SqlAlchemyVisits(sessionmaker(bind=c.db)).tick()
    assert scalar(c,'SELECT count(*) FROM aari_visita_coordinaciones')==1
    c.repo.choose(c.claim,c.actor,choose_body(c))
    c.portal.publish(c.claim)
    rid=c.portal.list_own(c.provider)['items'][0]['id']
    c.portal.submit(rid,c.provider,budget())
    c.selection.choose(c.claim,c.actor,selection(c))
    # El sondeo HU23 pagina por UUID y puede necesitar volver al inicio del
    # cursor antes de descubrir otro intento del mismo reclamo.
    c.visits.tick()
    c.visits.tick()
    assert scalar(c,'SELECT count(*) FROM aari_visita_coordinaciones')==2
    assert c.visits.get(c.claim,c.tenant)['id']!=old_id
    # Tras otro intento, el hilo cancelado sigue en la bandeja y se lee como
    # historia, sin invocar las acciones de la nueva coordinación HU23.
    assert any(x['id']==detail['hilo_id'] for x in conversations.inbox(c.tenant)['items'])
    assert not conversations.thread_messages(detail['hilo_id'],c.provider)['puede_enviar']


@pytest.mark.parametrize('visit_case',['ordinario','extraordinario'],indirect=True)
def test_actual_confirmation_and_cancellation_have_exactly_one_winner(integrated):
    c=integrated
    data=publish(c)
    cp=cancellation(c)
    vp=VisitConfirmationRequest(**action(c,c.provider),fecha=data.opciones[1].desde)
    barrier=Barrier(2)
    def decide(index):
        barrier.wait(timeout=5)
        try:
            return c.cancel.cancel(c.claim,c.actor,cp) if index==0 else c.visits.act(c.claim,c.provider,'confirmar',vp)
        except (QuotePortalError,VisitError): return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(decide,range(2)))
    assert sum(x is not None for x in results)==1
    assert scalar(c,'SELECT count(*) FROM visitas')+scalar(c,'SELECT count(*) FROM cancelaciones')==1


@pytest.mark.parametrize('visit_case',['ordinario','extraordinario'],indirect=True)
def test_confirmed_visit_cannot_be_cancelled_and_history_is_unchanged(integrated):
    c=integrated
    data=publish(c)
    c.visits.act(c.claim,c.provider,'confirmar',VisitConfirmationRequest(**action(c,c.provider),fecha=data.opciones[0].desde))
    assert not c.cancel.get(c.claim,c.actor)['puede_cancelar']
    with pytest.raises(QuotePortalError): c.cancel.cancel(c.claim,c.actor,cancellation(c))
    assert scalar(c,'SELECT count(*) FROM cancelaciones')==0
    assert scalar(c,'SELECT count(*) FROM visitas')==1
    assert scalar(c,'SELECT etapa FROM aari_visita_coordinaciones')=='confirmada'


@pytest.mark.parametrize('visit_case',['extraordinario'],indirect=True)
def test_cancelled_threads_keep_audiences_and_current_identity_separate(integrated):
    from sqlalchemy import text
    c=integrated
    tenant_thread=c.visits.get(c.claim,c.tenant)['hilo_id']
    owner_thread=c.visits.get(c.claim,c.actor)['hilo_id']
    c.cancel.cancel(c.claim,c.actor,cancellation(c))
    repo=SqlAlchemyConversations(sessionmaker(bind=c.db))
    assert not repo.thread_messages(owner_thread,c.actor)['puede_enviar']
    for thread,user in ((tenant_thread,c.actor),(owner_thread,c.tenant),
                        (tenant_thread,c.tenant.model_copy(update={'perfil_id':uuid4()})),
                        (tenant_thread,c.provider.model_copy(update={'perfil_id':uuid4()}))):
        with pytest.raises(ConversationError): repo.thread_messages(thread,user)
    with c.db.begin() as session:
        session.execute(text('UPDATE usuarios SET activo=false WHERE id=:id'),{'id':c.provider.id})
    with pytest.raises(ConversationError): repo.thread_messages(tenant_thread,c.provider)


def test_historical_http_pagination_and_read_receipt_do_not_allow_writes(integrated):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.auth import get_current_user
    from app.api import conversations as api
    c=integrated
    publish(c)
    c.visits.act(c.claim,c.provider,'sin-coincidencia',VisitAction(**action(c,c.provider)))
    thread=c.visits.get(c.claim,c.tenant)['hilo_id']
    for i in range(5):
        c.visits.thread_send(thread,c.tenant,ConversationMessageRequest(request_id=uuid4(),texto=f'Mensaje ficticio {i}'))
    c.cancel.cancel(c.claim,c.actor,cancellation(c))
    app=FastAPI()
    app.include_router(api.router)
    repo=SqlAlchemyConversations(sessionmaker(bind=c.db))
    app.dependency_overrides[get_current_user]=lambda:c.tenant
    app.dependency_overrides[api.get_conversations]=lambda:repo
    path=f'/conversaciones/hilos/{thread}'
    with TestClient(app) as http:
        response=http.get(path+'?limite=2')
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        first=response.json()
        assert len(first['items'])==2 and first['hay_anteriores'] and not first['puede_enviar']
        before=first['items'][0]['numero']
        previous=http.get(path+f'?limite=2&antes={before}').json()
        assert not ({m['id'] for m in first['items']}&{m['id'] for m in previous['items']})
        assert http.post(path+'/lectura',json={'hasta_numero':first['ultimo_numero']}).status_code==200
        assert http.post(path+'/lectura',json={'hasta_numero':first['ultimo_numero']+1}).status_code==422
        assert http.post(path+'/mensajes',json={'request_id':str(uuid4()),'texto':'No permitido.'}).status_code==403
