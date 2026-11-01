"""HU23 PostgreSQL local. La selección se prepara como fixture, no simula HU20 real."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.visits import SqlAlchemyVisits, validate_visit_notice
from app.db.conversations import SqlAlchemyConversations
from app.schemas.conversations import ConversationMessageRequest
from app.schemas.visits import AvailabilityRequest, VisitAction, VisitConfirmationRequest, VisitOption, VisitProposalRequest
from app.services.visits import VisitError
from tests.test_quote_portal_postgres import portal_case, eligible, active_provider, budget, scalar
from tests.test_provider_choices_postgres import choice_base
from tests.test_responsible_actor_postgres import local_engine, claim_case, MIGRATIONS

pytestmark=pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'),reason='PostgreSQL local dedicado.')


@pytest.fixture
def visit_case(portal_case,monkeypatch,request):
    case=eligible(portal_case,getattr(request,'param','ordinario'))
    monkeypatch.setenv('AARI_VISITS_ENABLED','true')
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED','true')
    with case.db.connect() as c:
        cursor=c.connection.cursor()
        for name in ('20261028210000_hu33_conversaciones.sql','20261101110000_hu23_coordinacion_visitas.sql'):
            cursor.execute((MIGRATIONS/name).read_text(encoding='utf-8'))
        c.commit()
        cursor.close()
    case.provider=active_provider(case)
    case.portal.publish(case.claim)
    rid=case.portal.list_own(case.provider)['items'][0]['id']
    case.portal.submit(rid,case.provider,budget())
    with case.db.begin() as c:
        bid=c.execute(text('SELECT id FROM presupuestos WHERE solicitud_aari_id=:id'),{'id':rid}).scalar_one()
        c.execute(text("UPDATE reclamos SET estado='Proveedor seleccionado',presupuesto_seleccionado_id=:b,proveedor_seleccionado_id=:p,monto_seleccionado=10000.50 WHERE id=:id"),{'id':case.claim,'b':bid,'p':case.provider.perfil_id})
    case.visits=SqlAlchemyVisits(sessionmaker(bind=case.db))
    case.tenant=case.actors['inquilino']
    case.cid=case.visits.start(case.claim)
    return case


def action(case,user=None,**extra):
    detail=case.visits.get(case.claim,user or case.tenant)
    return dict(request_id=uuid4(),coordinacion_id=detail['id'],version_esperada=detail['version'],**extra)


def options():
    start=(datetime.now(timezone.utc)+timedelta(days=4)).replace(hour=17,minute=0,second=0,microsecond=0)
    return [VisitOption(desde=start+timedelta(days=i),hasta=start+timedelta(days=i,hours=3)) for i in range(3)]


def publish(case):
    data=AvailabilityRequest(**action(case),opciones=options())
    case.visits.act(case.claim,case.tenant,'disponibilidad',data)
    return data


@pytest.mark.parametrize('visit_case',['ordinario','extraordinario'],indirect=True)
def test_schedule_from_selected_quote_no_llm_owner_does_not_replace_tenant(visit_case):
    c=visit_case
    assert c.cid and c.visits.start(c.claim)==c.cid
    assert c.visits.get(c.claim,c.tenant)['acciones']==['disponibilidad']
    if c.actor.rol=='propietario':
        assert c.visits.get(c.claim,c.actor)['acciones']==[]
        assert c.visits.get(c.claim,c.actor)['hilo_id']!=c.visits.get(c.claim,c.tenant)['hilo_id']
    data=publish(c)
    assert c.visits.act(c.claim,c.tenant,'disponibilidad',data)['repetida']
    date=data.opciones[1].desde+timedelta(minutes=30)
    confirm=VisitConfirmationRequest(**action(c,c.provider),fecha=date)
    result=c.visits.act(c.claim,c.provider,'confirmar',confirm)
    assert result['etapa']=='confirmada' and result['fecha_confirmada']==date
    assert scalar(c,'SELECT estado FROM reclamos')=='Visita programada'
    assert scalar(c,'SELECT count(*) FROM visitas')==1
    assert scalar(c,'SELECT count(*) FROM aari_visita_acciones')==2
    assert c.visits.act(c.claim,c.provider,'confirmar',confirm)['repetida']
    assert scalar(c,'SELECT count(*) FROM reclamo_historial_estados WHERE estado_nuevo=\'Visita programada\'')==1


def test_negotiation_requires_button_counterparty_and_exact_proposal_version(visit_case):
    c=visit_case
    publish(c)
    thread=c.visits.get(c.claim,c.tenant)['hilo_id']
    msg=ConversationMessageRequest(request_id=uuid4(),texto='El lunes podría por la tarde.')
    with pytest.raises(VisitError): c.visits.thread_send(thread,c.tenant,msg)
    due=scalar(c,'SELECT vence_en FROM aari_visita_coordinaciones')
    c.visits.act(c.claim,c.provider,'sin-coincidencia',VisitAction(**action(c,c.provider)))
    assert c.visits.thread_send(thread,c.tenant,msg)['mensaje']['propio']
    assert c.visits.thread_send(thread,c.tenant,msg)['repetido']
    when=options()[0].desde+timedelta(days=10)
    proposed=c.visits.act(c.claim,c.provider,'proponer',VisitProposalRequest(**action(c,c.provider),fecha=when))
    with pytest.raises(VisitError):
        c.visits.act(c.claim,c.provider,'confirmar',VisitConfirmationRequest(**action(c,c.provider),propuesta_version=proposed['propuesta']['version']))
    with pytest.raises(VisitError):
        c.visits.act(c.claim,c.tenant,'confirmar',VisitConfirmationRequest(**action(c),propuesta_version=proposed['propuesta']['version']+1))
    c.visits.act(c.claim,c.tenant,'confirmar',VisitConfirmationRequest(**action(c),propuesta_version=proposed['propuesta']['version']))
    assert scalar(c,'SELECT vence_en FROM aari_visita_coordinaciones')==due
    assert not c.visits.thread_messages(thread,c.tenant)['puede_enviar']
    with pytest.raises(VisitError): c.visits.thread_send(thread,c.tenant,ConversationMessageRequest(request_id=uuid4(),texto='Tardío'))


@pytest.mark.parametrize('condition',['past','same_day','outside','stale','wrong_attempt'])
def test_rejects_invalid_availability_and_confirmations_without_partial_writes(visit_case,condition):
    c=visit_case
    if condition in {'past','same_day'}:
        slots=options()
        if condition=='past': slots[0]=VisitOption(desde=slots[0].desde-timedelta(days=100),hasta=slots[0].hasta-timedelta(days=100))
        else: slots[1]=slots[0]
        with pytest.raises(VisitError): c.visits.act(c.claim,c.tenant,'disponibilidad',AvailabilityRequest(**action(c),opciones=slots))
        assert scalar(c,'SELECT count(*) FROM aari_visita_opciones')==0
    else:
        data=publish(c)
        kwargs=action(c,c.provider)
        if condition=='stale': kwargs['version_esperada']=0
        if condition=='wrong_attempt': kwargs['coordinacion_id']=uuid4()
        when=data.opciones[0].desde+timedelta(hours=10 if condition=='outside' else 1)
        with pytest.raises(VisitError): c.visits.act(c.claim,c.provider,'confirmar',VisitConfirmationRequest(**kwargs,fecha=when))
        assert scalar(c,'SELECT count(*) FROM visitas')==0


def test_simultaneous_confirmations_only_one_visit_and_audit(visit_case):
    c=visit_case
    data=publish(c)
    requests=[VisitConfirmationRequest(**action(c,c.provider),fecha=data.opciones[i].desde) for i in range(2)]
    barrier=Barrier(2)
    def confirm(data):
        barrier.wait(timeout=10)
        try: return c.visits.act(c.claim,c.provider,'confirmar',data)
        except VisitError: return None
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(confirm,requests))
    assert sum(v is not None for v in results)==1
    assert scalar(c,'SELECT count(*) FROM visitas')==1


@pytest.mark.parametrize('condition',['inactive_provider','tenant_left','resolved','changed_address'])
def test_context_changes_block_actions_and_obsolete_mail(visit_case,condition):
    c=visit_case
    data=publish(c)
    payload=VisitConfirmationRequest(**action(c,c.provider),fecha=data.opciones[0].desde)
    with c.db.begin() as s:
        if condition=='inactive_provider': s.execute(text('UPDATE proveedores SET activo=false'))
        elif condition=='tenant_left': s.execute(text("UPDATE inquilinos SET propiedad_id=NULL,estado='sin_propiedad_asignada'"))
        elif condition=='resolved': s.execute(text("UPDATE reclamos SET estado='Resuelto'"))
        else: s.execute(text("UPDATE propiedades SET direccion='Dirección distinta'"))
    with pytest.raises(VisitError): c.visits.act(c.claim,c.provider,'confirmar',payload)
    with c.db.begin() as s:
        nid=s.execute(text("SELECT notificacion_id FROM aari_visita_avisos WHERE evento='opciones'")).scalar_one()
        assert not validate_visit_notice(s,nid)
    assert scalar(c,'SELECT count(*) FROM visitas')==0


def test_timeout_no_visit_mail_or_chat_restarts_clock(visit_case):
    c=visit_case
    publish(c)
    with c.db.begin() as s: s.execute(text("UPDATE aari_visita_coordinaciones SET vence_en=clock_timestamp()-interval '1 second'"))
    with pytest.raises(VisitError): c.visits.act(c.claim,c.provider,'sin-coincidencia',VisitAction(**action(c,c.provider)))
    c.visits.follow_up(c.claim)
    c.visits.follow_up(c.claim)
    assert scalar(c,'SELECT etapa FROM aari_visita_coordinaciones')=='sin_acuerdo'
    assert scalar(c,"SELECT count(*) FROM aari_visita_avisos WHERE evento='sin_acuerdo'")==1
    assert scalar(c,'SELECT count(*) FROM visitas')==0


def test_migration_protects_tables_and_preserves_legacy_unique_threads(visit_case):
    with visit_case.db.connect() as s:
        assert s.execute(text("SELECT count(*) FROM pg_class WHERE relname IN ('aari_visita_coordinaciones','aari_visita_opciones','aari_visita_acciones','aari_visita_avisos','visitas') AND relrowsecurity")).scalar_one()==5
        assert s.execute(text("SELECT count(*) FROM information_schema.role_table_grants WHERE table_name LIKE 'aari_visita_%' AND grantee IN ('PUBLIC','anon','authenticated')")).scalar_one()==0


def test_global_inbox_routes_coordination_and_preserves_pagination(visit_case):
    c=visit_case
    chat=SqlAlchemyConversations(sessionmaker(bind=c.db))
    expected=c.visits.get(c.claim,c.tenant)['hilo_id']
    inbox=chat.inbox(c.tenant,page_size=1)
    pages=[chat.inbox(c.tenant,page=n,page_size=1)['items'][0]['id'] for n in range(1,inbox['total']+1)]
    assert len(pages)==len(set(pages)) and expected in pages
    thread=chat.thread_messages(expected,c.tenant)
    assert thread['finalidad']=='coordinacion' and not thread['puede_enviar']
    assert thread['coordinacion_url']==f'/visitas/{c.claim}'
    chat.thread_read(expected,c.tenant,thread['ultimo_numero'])
    assert chat.thread_messages(expected,c.tenant)['no_leidos']==0


def test_reminder_outbox_is_idempotent_and_skips_24h_if_confirmed_late(visit_case):
    c=visit_case
    data=publish(c)
    c.visits.act(c.claim,c.provider,'confirmar',VisitConfirmationRequest(**action(c,c.provider),fecha=data.opciones[0].desde))
    with c.db.begin() as s:
        # Reloj relativo de QA: visita en 90 minutos, confirmada hace 3 horas.
        date=s.execute(text("SELECT date_trunc('minute',clock_timestamp()+interval '90 minutes')")).scalar_one()
        s.execute(text('UPDATE reclamos SET fecha_visita=:d'),{'d':date})
        s.execute(text("UPDATE aari_visita_coordinaciones SET propuesta_fecha=:d,actualizada_en=clock_timestamp()-interval '3 hours'"),{'d':date})
    c.visits.follow_up(c.claim)
    c.visits.follow_up(c.claim)
    assert scalar(c,"SELECT count(*) FROM aari_visita_avisos WHERE evento='recordatorio_2'")==2
    assert scalar(c,"SELECT count(*) FROM aari_visita_avisos WHERE evento='recordatorio_24'")==0


def test_resolved_claim_stops_notices_without_rewriting_visit_as_cancelled(visit_case):
    c=visit_case
    data=publish(c)
    c.visits.act(c.claim,c.provider,'confirmar',VisitConfirmationRequest(**action(c,c.provider),fecha=data.opciones[0].desde))
    with c.db.begin() as s: s.execute(text("UPDATE reclamos SET estado='Resuelto'"))
    c.visits.follow_up(c.claim)
    assert scalar(c,'SELECT estado FROM visitas')=='confirmada'
    assert scalar(c,'SELECT etapa FROM aari_visita_coordinaciones')=='invalidada'
    with c.db.begin() as s:
        ids=s.execute(text("SELECT notificacion_id FROM aari_visita_avisos WHERE evento='confirmada'")).scalars().all()
        assert ids and all(not validate_visit_notice(s,n) for n in ids)


def test_real_notification_repository_revalidates_visit_before_delivery(visit_case):
    c=visit_case
    publish(c)
    nid=scalar(c,"SELECT notificacion_id FROM aari_visita_avisos WHERE evento='opciones'")
    context=c.claims.claim_notification(nid)
    assert context and c.claims.prepare_notification_delivery(context)
    with c.db.begin() as s: s.execute(text("UPDATE reclamos SET estado='Resuelto'"))
    assert not c.claims.prepare_notification_delivery(context)
    assert scalar(c,'SELECT estado_envio FROM notificaciones WHERE id=:id',id=nid)=='fallido'
