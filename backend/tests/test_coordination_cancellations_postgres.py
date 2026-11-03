"""HU24 con módulos reales y una DB PostgreSQL local descartable por caso."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import os
import pytest
from sqlalchemy import event,text
from sqlalchemy.exc import IntegrityError,DBAPIError
from sqlalchemy.orm import sessionmaker
from app.db.coordination_cancellations import SqlAlchemyCoordinationCancellations
from app.db.cancellation_notices import validate_cancellation_notice
from app.schemas.coordination_cancellations import CoordinationCancellationRequest
from app.services.quote_portal import QuotePortalError
from tests.test_quote_selections_postgres import selection_case,quoted,selection
from tests.test_quote_portal_postgres import portal_case,active_provider,request,budget,scalar
from tests.test_provider_choices_postgres import choice_base,body as choose_body
from tests.test_responsible_actor_postgres import claim_case,local_engine,MIGRATIONS
from tests.test_quote_requests_postgres import eligible

pytestmark=pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'),reason='Sólo PostgreSQL local descartable.')


@pytest.fixture
def cancellation_case(selection_case,monkeypatch):
    case=selection_case
    monkeypatch.setenv('AARI_CANCELLATIONS_ENABLED','true')
    with case.db.connect() as c:
        cur=c.connection.cursor()
        cur.execute((MIGRATIONS/'20261103120000_hu24_cancelacion_coordinacion.sql').read_text(encoding='utf-8'))
        c.connection.commit()
        cur.close()
    case.cancel=SqlAlchemyCoordinationCancellations(sessionmaker(bind=case.db))
    return case


def payload(case,**changes):
    view=case.cancel.get(case.claim,case.actor)
    return CoordinationCancellationRequest(request_id=uuid4(),eleccion_id=view['eleccion_id'],
        expected_updated_at=view['updated_at'],confirmar=True).model_copy(update=changes)


def current_choice(case):
    with case.db.connect() as c:
        return dict(c.execute(text('SELECT * FROM reclamo_elecciones_proveedor ORDER BY intento DESC LIMIT 1')).mappings().one())


@pytest.mark.parametrize('expense',['ordinario','extraordinario'])
@pytest.mark.parametrize('stage',['esperando','revisando','seleccionado'])
def test_cancels_each_stage_and_reselects_without_rewriting_history(cancellation_case,expense,stage):
    case=cancellation_case
    eligible(case,expense)
    provider=active_provider(case)
    case.portal.publish(case.claim)
    old_request=request(case,provider)
    old_round=scalar(case,'SELECT ronda_id FROM aari_solicitudes_presupuesto LIMIT 1')
    if stage!='esperando': case.portal.submit(old_request['id'],provider,budget())
    if stage=='seleccionado': case.selection.choose(case.claim,case.actor,selection(case))
    original=current_choice(case)
    with case.db.connect() as c:
        rr=dict(c.execute(text('SELECT * FROM reclamo_responsables')).mappings().one())
        auth=[dict(x) for x in c.execute(text('SELECT * FROM reclamo_autorizaciones')).mappings()]
    saved=case.cancel.cancel(case.claim,case.actor,payload(case))
    assert saved['eleccion_id']==original['id']
    assert scalar(case,'SELECT count(*) FROM cancelaciones')==1
    assert current_choice(case)['intento']==1
    assert current_choice(case)['estado']=='pendiente'
    assert case.repo.get(case.claim,case.actor).puede_elegir
    assert scalar(case,"SELECT estado FROM aari_rondas_presupuesto")== 'cancelada'
    assert scalar(case,'SELECT presupuesto_seleccionado_id FROM reclamos') is None
    with case.db.connect() as c:
        assert dict(c.execute(text('SELECT * FROM reclamo_elecciones_proveedor WHERE id=:id'),{'id':original['id']}).mappings().one())==original
        assert dict(c.execute(text('SELECT * FROM reclamo_responsables')).mappings().one())==rr
        assert [dict(x) for x in c.execute(text('SELECT * FROM reclamo_autorizaciones')).mappings()]==auth
    assert not case.portal.get_own(old_request['id'],provider)['puede_responder']
    with pytest.raises(QuotePortalError):
        case.portal.submit(old_request['id'],provider,budget())
    case.repo.choose(case.claim,case.actor,choose_body(case))
    case.portal.publish(case.claim)
    assert scalar(case,'SELECT count(*) FROM aari_rondas_presupuesto')==2
    with case.db.connect() as c:
        new=c.execute(text('SELECT id FROM aari_solicitudes_presupuesto WHERE ronda_id<>:old'),{'old':old_round}).scalar_one()
    case.portal.submit(new,provider,budget())
    case.selection.choose(case.claim,case.actor,selection(case))
    assert scalar(case,'SELECT estado FROM reclamos')=='Proveedor seleccionado'
    assert scalar(case,'SELECT count(*) FROM presupuestos')==(1 if stage=='esperando' else 2)


def test_replay_and_concurrent_double_click_make_one_new_attempt(cancellation_case):
    case=cancellation_case
    quoted(case)
    p=payload(case)
    barrier=Barrier(2)
    def cancel():
        barrier.wait(timeout=5)
        return case.cancel.cancel(case.claim,case.actor,p)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:cancel(),range(2)))
    assert results[0]['id']==results[1]['id']
    assert sum(x['repetida'] for x in results)==1
    assert scalar(case,'SELECT count(*) FROM cancelaciones')==1
    assert scalar(case,'SELECT count(*) FROM reclamo_elecciones_proveedor')==2
    assert case.cancel.cancel(case.claim,case.actor,p)['repetida']


@pytest.mark.parametrize('change',['version','choice','confirmation','inactive','actor','authorization'])
def test_rejects_stale_or_unauthorized_cancellation(cancellation_case,change):
    case=cancellation_case
    quoted(case,'extraordinario' if change=='authorization' else 'ordinario')
    p=payload(case)
    if change=='choice': p=p.model_copy(update={'eleccion_id':uuid4()})
    if change=='confirmation': p=p.model_copy(update={'confirmar':False})
    with case.db.begin() as c:
        if change=='version': c.execute(text('UPDATE reclamos SET updated_at=clock_timestamp()'))
        if change=='inactive': c.execute(text('UPDATE usuarios SET activo=false WHERE id=:id'),{'id':case.actor.id})
        if change=='actor': c.execute(text('UPDATE inquilinos SET usuario_id=NULL'))
        if change=='authorization': c.execute(text('UPDATE reclamo_autorizaciones SET usuario_id=:id'),{'id':case.actors['inquilino'].id})
    with pytest.raises(QuotePortalError): case.cancel.cancel(case.claim,case.actor,p)
    assert scalar(case,'SELECT count(*) FROM cancelaciones')==0


def test_blocks_programmed_visit_even_with_stale_claim_state(cancellation_case):
    case=cancellation_case
    quoted(case)
    p=payload(case)
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamos SET estado='Visita programada',fecha_visita=clock_timestamp()"))
    with pytest.raises(QuotePortalError): case.cancel.cancel(case.claim,case.actor,p)
    assert not case.cancel.get(case.claim,case.actor)['puede_cancelar']
    assert scalar(case,'SELECT count(*) FROM cancelaciones')==0


def test_rollback_does_not_close_round_or_open_choice(cancellation_case):
    case=cancellation_case
    quoted(case)
    p=payload(case)
    def fail(conn,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO reclamo_cancelaciones_coordinacion'): raise RuntimeError('fallo sintético')
    event.listen(case.db,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError): case.cancel.cancel(case.claim,case.actor,p)
    finally: event.remove(case.db,'before_cursor_execute',fail)
    assert scalar(case,'SELECT count(*) FROM cancelaciones')==0
    assert scalar(case,'SELECT count(*) FROM reclamo_elecciones_proveedor')==1
    assert scalar(case,'SELECT cerrada_en FROM aari_rondas_presupuesto') is None


def test_third_cancellation_alerts_real_operator_once_and_preserves_history(cancellation_case):
    case=cancellation_case
    with case.db.begin() as c:
        c.execute(text("UPDATE usuarios SET primer_ingreso=false WHERE email='operator@example.com'"))
    eligible(case)
    for _ in range(3):
        saved=case.cancel.cancel(case.claim,case.actor,payload(case))
        p=current_choice(case)
        case.repo.choose(case.claim,case.actor,choose_body(case))
    assert p['intento']==3
    assert scalar(case,'SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :key',key='hu24:%:alerta')==1
    assert scalar(case,'SELECT destinatario_contacto FROM notificaciones WHERE clave_idempotencia LIKE :key',key='hu24:%:alerta')=='operator@example.com'
    with case.db.begin() as c:
        with pytest.raises(IntegrityError):
            with c.begin_nested(): c.execute(text('INSERT INTO reclamo_elecciones_proveedor(reclamo_id,solicitud_responsable_en,actor_tipo,solicitado_en,recordatorio_programado_en,respuesta_vence_en,intento) SELECT reclamo_id,solicitud_responsable_en,actor_tipo,solicitado_en,recordatorio_programado_en,respuesta_vence_en,intento FROM reclamo_elecciones_proveedor LIMIT 1'))
    assert len(case.cancel.get(case.claim,case.actor)['historial'])==3
    assert saved['estado_resultante']=='Pendiente de respuesta del responsable'


def test_provider_notice_is_revalidated_and_old_selection_cannot_reactivate(cancellation_case):
    case=cancellation_case
    users=quoted(case)
    old=selection(case)
    case.selection.choose(case.claim,case.actor,old)
    case.cancel.cancel(case.claim,case.actor,payload(case))
    with pytest.raises(QuotePortalError): case.selection.choose(case.claim,case.actor,old)
    with sessionmaker(bind=case.db).begin() as c:
        nid=c.execute(text("SELECT id FROM notificaciones WHERE clave_idempotencia LIKE 'hu24:%:proveedor:%'")).scalar_one()
        assert validate_cancellation_notice(c,nid)
        c.execute(text('UPDATE usuarios SET activo=false WHERE id=:id'),{'id':users[0].id})
        assert not validate_cancellation_notice(c,nid)
    assert scalar(case,'SELECT count(*) FROM reclamo_selecciones_presupuesto')==1
    assert scalar(case,'SELECT estado FROM reclamos')=='Pendiente de respuesta del responsable'


@pytest.mark.parametrize('opposite',['seleccion','cancelacion'])
def test_cancellation_competes_with_other_decision_without_two_winners(cancellation_case,opposite):
    case=cancellation_case
    quoted(case)
    cp,sp=payload(case),selection(case)
    other=payload(case)
    barrier=Barrier(2)
    def decide(index):
        barrier.wait(timeout=5)
        try:
            if index and opposite=='seleccion': return case.selection.choose(case.claim,case.actor,sp)
            return case.cancel.cancel(case.claim,case.actor,other if index else cp)
        except QuotePortalError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(decide,range(2)))
    assert sum(x is not None for x in results)==1
    assert scalar(case,'SELECT count(*) FROM cancelaciones')+scalar(case,'SELECT count(*) FROM reclamo_selecciones_presupuesto')==1


def test_real_http_returns_to_hu17_and_replays_without_duplicate(cancellation_case):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.auth import get_current_user
    from app.api import coordination_cancellations as api,provider_choices as choices
    case=cancellation_case
    quoted(case)
    app=FastAPI()
    app.include_router(api.router)
    app.include_router(choices.router)
    app.dependency_overrides[get_current_user]=lambda:case.actor
    app.dependency_overrides[api.get_cancellations]=lambda:case.cancel
    app.dependency_overrides[choices.get_provider_choices_repository]=lambda:case.repo
    path=f'/reclamos/{case.claim}/cancelacion-coordinacion'
    with TestClient(app) as http:
        view=http.get(path)
        assert view.status_code==200 and view.headers['cache-control']=='no-store'
        p=payload(case).model_dump(mode='json')
        response=http.post(path,json=p)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert http.post(path,json=p).json()['repetida']
        assert not http.get(path).json()['puede_cancelar']
        choice=http.get(f'/reclamos/{case.claim}/tipo-proveedor').json()
        assert choice['puede_elegir'] and choice['solicitud_id']==response.json()['eleccion_nueva_id']
    assert scalar(case,'SELECT count(*) FROM cancelaciones')==1


def test_cancelled_conversations_remain_readable_and_cannot_receive_messages(cancellation_case,monkeypatch):
    from app.db.conversations import SqlAlchemyConversations
    from app.schemas.conversations import ConversationMessageRequest
    from app.services.conversations import ConversationError
    case=cancellation_case
    with case.db.connect() as c:
        cur=c.connection.cursor()
        cur.execute((MIGRATIONS/'20261028210000_hu33_conversaciones.sql').read_text(encoding='utf-8'))
        c.connection.commit()
        cur.close()
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED','true')
    eligible(case)
    user=active_provider(case)
    case.portal.publish(case.claim)
    rid=request(case,user)['id']
    conversations=SqlAlchemyConversations(sessionmaker(bind=case.db))
    before=conversations.messages(rid,user)
    case.cancel.cancel(case.claim,case.actor,payload(case))
    after=conversations.messages(rid,user)
    assert after['ultimo_numero']>before['ultimo_numero']
    assert not after['puede_enviar']
    assert all(x['id'] in {y['id'] for y in after['items']} for x in before['items'])
    with pytest.raises(ConversationError):
        conversations.send(rid,user,ConversationMessageRequest(request_id=uuid4(),texto='Mensaje tardío ficticio'))


def test_audit_is_immutable_and_public_roles_have_no_access(cancellation_case):
    case=cancellation_case
    quoted(case)
    case.cancel.cancel(case.claim,case.actor,payload(case))
    with case.db.begin() as c:
        for statement in ("UPDATE reclamo_cancelaciones_coordinacion SET actor_nombre='alterado'",
                          'DELETE FROM reclamo_cancelaciones_coordinacion'):
            with pytest.raises(DBAPIError):
                with c.begin_nested(): c.execute(text(statement))
        for table in ('cancelaciones','reclamo_cancelaciones_coordinacion'):
            with pytest.raises(DBAPIError):
                with c.begin_nested():
                    c.execute(text('SET LOCAL ROLE authenticated'))
                    c.execute(text(f'SELECT * FROM {table}'))
    assert scalar(case,'SELECT count(*) FROM cancelaciones')==1


def test_reelection_can_choose_own_provider_without_fabricating_contact(cancellation_case):
    case=cancellation_case
    quoted(case)
    case.cancel.cancel(case.claim,case.actor,payload(case))
    saved=case.repo.choose(case.claim,case.actor,choose_body(case,'propio'))
    assert saved.estado=='Pendiente de datos de proveedor propio'
    assert scalar(case,'SELECT count(*) FROM proveedores_externos')==0
    assert scalar(case,'SELECT count(*) FROM presupuestos')==1
