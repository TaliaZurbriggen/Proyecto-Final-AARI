"""HU33 local: avisos privados, consultas explícitas, bandeja y carreras sin red externa."""
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.conversations import SqlAlchemyConversations, _append
from app.schemas.auth import AuthenticatedUser
from app.schemas.conversations import ConversationActionRequest, ConversationMessageRequest
from app.services.conversations import ConversationError
from app.services.quote_portal import QuotePortalError
from tests.test_provider_choices_postgres import choice_base
from tests.test_responsible_actor_postgres import MIGRATIONS, claim_case, local_engine
from tests.test_quote_portal_postgres import active_provider, budget, eligible, past_deadline, portal_case, scalar

pytestmark = pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'), reason='Sólo PostgreSQL local descartable.')


@pytest.fixture
def conversation_case(portal_case, monkeypatch, request):
    case = eligible(portal_case, getattr(request, 'param', 'ordinario'))
    with case.db.connect() as connection:
        cursor = connection.connection.cursor()
        cursor.execute((MIGRATIONS / '20261028210000_hu33_conversaciones.sql').read_text(encoding='utf-8'))
        connection.commit()
        cursor.close()
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED', 'true')
    case.providers = [active_provider(case, n) for n in range(2)]
    case.portal.publish(case.claim)
    case.requests = [case.portal.list_own(user)['items'][0]['id'] for user in case.providers]
    case.chat = SqlAlchemyConversations(sessionmaker(bind=case.db))
    return case


def message(value='¿La pérdida está debajo de la pileta?', key=None):
    return ConversationMessageRequest(request_id=key or uuid4(), texto=value)


def action(key=None):
    return ConversationActionRequest(request_id=key or uuid4())


def inquiry(case):
    return case.chat.open_questions(case.requests[0], case.providers[0], action())['id']


def agency(case):
    with case.db.begin() as connection:
        uid = connection.execute(text("INSERT INTO usuarios(email,password_hash,rol,primer_ingreso) VALUES ('admin-chat@example.com','unused','administrador',false) RETURNING id")).scalar_one()
    return AuthenticatedUser(id=uid, email='admin-chat@example.com', rol='administrador', primer_ingreso=False)


@pytest.mark.parametrize('conversation_case', ['ordinario', 'extraordinario'], indirect=True)
def test_individual_agent_notices_and_technical_questions_are_not_a_group_chat(conversation_case):
    case, rid, provider = conversation_case, conversation_case.requests[0], conversation_case.providers[0]
    tenant, admin = case.actors['inquilino'], agency(case)
    provider_notices = case.chat.messages(rid, provider)
    responsible_notices = case.chat.messages(rid, case.actor)
    assert provider_notices['id'] != responsible_notices['id']
    for account in (provider, case.actor, admin):
        assert not case.chat.messages(rid, account)['puede_enviar']
        with pytest.raises(ConversationError):
            case.chat.send(rid, account, message('No es un chat libre.'))
    with pytest.raises(ConversationError):
        case.chat.thread_messages(responsible_notices['id'], provider)
    with pytest.raises(ConversationError):
        case.chat.thread_messages(provider_notices['id'], case.actor)
    qid = inquiry(case)
    case.chat.thread_send(qid, provider, message())
    case.chat.thread_send(qid, tenant, message('Está bajo la pileta.'))
    assert case.chat.thread_messages(qid, tenant)['items'][-1]['propio']
    for other in (case.providers[1], case.actors['propietario']):
        with pytest.raises(ConversationError): case.chat.thread_messages(qid, other)
    assert case.chat.thread_messages(qid, admin)['items']
    assert not case.chat.thread_messages(qid, admin)['puede_enviar']
    with pytest.raises(ConversationError): case.chat.thread_send(qid, admin, message())
    assert all(item['origen'] == 'agente' for item in case.chat.messages(rid, provider)['items'])


def test_operator_can_only_audit_assigned_claim_and_never_send(conversation_case):
    case, rid = conversation_case, conversation_case.requests[0]
    with case.db.begin() as connection:
        uid = connection.execute(text("UPDATE usuarios SET primer_ingreso=false WHERE rol='operador' RETURNING id")).scalar_one()
    operator = AuthenticatedUser(id=uid,email='operator@example.com',rol='operador',primer_ingreso=False)
    assert case.chat.inbox(operator)['items'] == []
    with pytest.raises(ConversationError): case.chat.messages(rid, operator)
    with case.db.begin() as connection:
        connection.execute(text('UPDATE reclamos SET operador_asignado_id=:id'), {'id': uid})
    assert case.chat.messages(rid, operator)['items']
    qid = inquiry(case)
    with pytest.raises(ConversationError): case.chat.thread_send(qid, operator, message())
    assert case.chat.inbox(operator)['no_leidos'] == 0


def test_events_are_durable_idempotent_and_keep_source_date(conversation_case):
    case, rid, provider = conversation_case, conversation_case.requests[0], conversation_case.providers[0]
    before = scalar(case, 'SELECT count(*) FROM aari_conversacion_mensajes')
    first = case.chat.messages(rid, provider)
    restarted = SqlAlchemyConversations(sessionmaker(bind=case.db)).messages(rid, provider)
    assert first == restarted and scalar(case, 'SELECT count(*) FROM aari_conversacion_mensajes') == before
    original = scalar(case, "SELECT creado_en FROM aari_presupuesto_eventos WHERE solicitud_id=:id AND tipo='publicada'", id=rid)
    assert first['items'][0]['creado_en'] == original
    case.portal.submit(rid, provider, budget())
    events = case.chat.messages(rid, provider)['items']
    assert sum('presentó su presupuesto' in item['texto'] for item in events) == 1


def test_lazy_inbox_recovers_old_events_in_batch_without_fake_coordination(portal_case, monkeypatch):
    case = eligible(portal_case)
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED', 'false')
    provider = active_provider(case)
    case.portal.publish(case.claim)
    with case.db.connect() as connection:
        cursor = connection.connection.cursor()
        cursor.execute((MIGRATIONS / '20261028210000_hu33_conversaciones.sql').read_text(encoding='utf-8'))
        connection.commit()
        cursor.close()
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED', 'true')
    chat = SqlAlchemyConversations(sessionmaker(bind=case.db))
    first = chat.inbox(provider)
    assert first['total'] == first['no_leidos'] == 1
    assert first == chat.inbox(provider)
    assert scalar(case, "SELECT count(*) FROM aari_conversaciones WHERE finalidad!='presupuesto'") == 0
    assert scalar(case, 'SELECT count(*) FROM aari_conversacion_lecturas') == 0


@pytest.mark.parametrize('conversation_case', ['extraordinario'], indirect=True)
def test_replacing_owner_revokes_old_access_without_inheriting_financial_history(conversation_case):
    case, rid = conversation_case, conversation_case.requests[0]
    with case.db.begin() as connection:
        uid = connection.execute(text("INSERT INTO usuarios(email,password_hash,rol,primer_ingreso) VALUES ('new-owner@example.com','unused','propietario',false) RETURNING id")).scalar_one()
        connection.execute(text('UPDATE propietarios SET usuario_id=:id'), {'id': uid})
    new_owner = case.actor.model_copy(update={'id':uid,'email':'new-owner@example.com'})
    for account in (case.actor, new_owner):
        with pytest.raises(ConversationError): case.chat.messages(rid, account)
        assert not case.chat.inbox(account)['items']


def test_inbox_has_stable_pagination_constant_sql_and_never_marks_closed_threads_read(conversation_case):
    case = conversation_case
    qid = inquiry(case)
    tenant = case.actors['inquilino']
    statements = []
    def record(_conn, _cursor, sql, *_args): statements.append(sql)
    event.listen(case.db, 'before_cursor_execute', record)
    try:
        first = case.chat.inbox(tenant, page_size=1)
        count = len(statements)
        statements.clear()
        all_rows = case.chat.inbox(tenant, page_size=50)
        # Incluye dos SET LOCAL de la transacción; no crece con las tarjetas.
        assert len(statements) == count and count <= 8
    finally: event.remove(case.db, 'before_cursor_execute', record)
    pages = [case.chat.inbox(tenant, page=n, page_size=1)['items'][0]['id'] for n in range(1, first['total'] + 1)]
    assert len(pages) == len(set(pages)) == all_rows['total']
    assert qid in pages and first['no_leidos'] == all_rows['no_leidos']
    assert scalar(case, 'SELECT count(*) FROM aari_conversacion_lecturas') == 0
    assert case.chat.inbox(tenant, page=2147483647)['page'] == 1  # 20 por página.
    assert case.chat.inbox(agency(case))['no_leidos'] == 0


def test_questions_cannot_be_opened_without_active_tenant_access(conversation_case):
    case = conversation_case
    with case.db.begin() as connection:
        connection.execute(text('UPDATE usuarios SET activo=false WHERE id=:id'), {'id':case.actors['inquilino'].id})
    with pytest.raises(ConversationError) as error: inquiry(case)
    assert error.value.code == 'tenant_unavailable'
    assert scalar(case, "SELECT count(*) FROM aari_conversaciones WHERE finalidad='consulta_tecnica'") == 0
    assert scalar(case, "SELECT count(*) FROM usuarios WHERE rol='inquilino'") == 1


def test_close_is_explicit_and_quote_is_blocked_until_provider_finishes(conversation_case):
    case, rid, provider = conversation_case, conversation_case.requests[0], conversation_case.providers[0]
    deadline = scalar(case, 'SELECT vence_en FROM aari_solicitudes_presupuesto WHERE id=:id', id=rid)
    qid = inquiry(case)
    with pytest.raises(QuotePortalError) as error: case.portal.submit(rid, provider, budget())
    assert error.value.code == 'questions_open'
    for account in (case.actors['inquilino'], case.actor, agency(case)):
        with pytest.raises(ConversationError): case.chat.finish_questions(qid, account, action())
    key = action()
    assert not case.chat.finish_questions(qid, provider, key)['repetido']
    assert case.chat.finish_questions(qid, provider, key)['repetido']
    detail = case.chat.thread_messages(qid, provider)
    assert not detail['puede_enviar'] and not detail['puede_finalizar']
    with pytest.raises(ConversationError): case.chat.thread_send(qid, case.actors['inquilino'], message())
    with pytest.raises(ConversationError): inquiry(case)
    assert scalar(case, 'SELECT vence_en FROM aari_solicitudes_presupuesto WHERE id=:id', id=rid) == deadline
    result = case.portal.submit(rid, provider, budget())
    assert result['presupuesto']['monto'] == '10000.50'


def test_message_retry_recovers_one_result_without_decisions(conversation_case):
    case, provider = conversation_case, conversation_case.providers[0]
    qid = inquiry(case)
    body = message('Acepto $10000; martes a las 10.')
    first = case.chat.thread_send(qid, provider, body)
    assert case.chat.thread_send(qid, provider, body)['repetido']
    assert first['mensaje'] == case.chat.thread_send(qid, provider, body)['mensaje']
    with pytest.raises(ConversationError): case.chat.thread_send(qid, provider, message('Otro texto', body.request_id))
    assert scalar(case, 'SELECT count(*) FROM presupuestos') == 0
    assert scalar(case, 'SELECT proveedor_seleccionado_id FROM reclamos') is None
    assert scalar(case, 'SELECT count(*) FROM visitas') == 0
    case.chat.finish_questions(qid, provider, action())
    assert case.chat.thread_send(qid, provider, body)['repetido']


def test_read_positions_are_monotonic_and_inbox_uses_only_authorized_threads(conversation_case):
    case, provider, tenant = conversation_case, conversation_case.providers[0], conversation_case.actors['inquilino']
    qid = inquiry(case)
    number = case.chat.thread_send(qid, provider, message())['mensaje']['numero']
    assert case.chat.thread_messages(qid, tenant)['no_leidos'] == number
    assert case.chat.thread_read(qid, tenant, number)['no_leidos'] == 0
    assert case.chat.thread_read(qid, tenant, 1)['leido_hasta'] == number
    with pytest.raises(ConversationError): case.chat.thread_read(qid, tenant, number + 1)
    case.chat.thread_send(qid, tenant, message('Respuesta del inquilino.'))
    assert case.chat.thread_messages(qid, tenant)['no_leidos'] == 0
    own = case.portal.list_own(provider)['items'][0]
    assert own['conversacion_no_leidos'] == case.chat.inbox(provider)['no_leidos']


def test_pagination_does_not_skip_unfetched_messages(conversation_case):
    case, tenant = conversation_case, conversation_case.actors['inquilino']
    qid = inquiry(case)
    with case.db.begin() as session:
        thread = session.execute(text('SELECT * FROM aari_conversaciones WHERE id=:id'), {'id':qid}).mappings().one()
        for n in range(65): _append(session,thread,origin='humano',actor=case.providers[0].id,name='Proveedor',body=f'Consulta {n}',request=uuid4())
    last = case.chat.thread_messages(qid, tenant, limit=30)
    assert [m['numero'] for m in last['items']] == list(range(37,67)) and last['hay_anteriores']
    assert [m['numero'] for m in case.chat.thread_messages(qid,tenant,before=37)['items']] == list(range(7,37))
    assert not case.chat.thread_messages(qid,tenant,before=7)['hay_anteriores']
    newer = case.chat.thread_messages(qid,tenant,after=1)
    assert newer['hay_nuevos'] and newer['items'][-1]['numero'] == 31
    assert case.chat.thread_read(qid,tenant,31)['no_leidos'] == 35
    with pytest.raises(ConversationError): case.chat.thread_messages(qid,tenant,before=2,after=1)


@pytest.mark.parametrize('change', ['cancelled','claim_closed','cycle','description','expired'])
def test_stale_context_rejects_new_messages_but_preserves_history_and_confirmed_retry(conversation_case, change):
    case, provider = conversation_case, conversation_case.providers[0]
    qid, body = inquiry(case), message()
    first = case.chat.thread_send(qid,provider,body)
    with case.db.begin() as c:
        if change == 'cancelled': c.execute(text("UPDATE aari_rondas_presupuesto SET estado='cancelada'"))
        elif change == 'claim_closed': c.execute(text("UPDATE reclamos SET estado='Resuelto'"))
        elif change == 'cycle': c.execute(text("UPDATE reclamo_responsables SET solicitado_en=solicitado_en+interval '1 second'"))
        elif change == 'description': c.execute(text("UPDATE reclamos SET descripcion='Otro contexto diferente'"))
    if change == 'expired': past_deadline(case)
    detail = case.chat.thread_messages(qid,provider)
    assert not detail['puede_enviar'] and any(m['id']==first['mensaje']['id'] for m in detail['items'])
    with pytest.raises(ConversationError): case.chat.thread_send(qid,provider,message('Nuevo texto'))
    assert case.chat.thread_send(qid,provider,body)['repetido']


@pytest.mark.parametrize('change', ['provider_disabled','account_disabled','first_login','provider_unlinked','tenant_left'])
def test_revoked_participant_cannot_keep_reading(conversation_case, change):
    case, provider = conversation_case, conversation_case.providers[0]
    qid, target = inquiry(case), provider
    with case.db.begin() as c:
        if change == 'provider_disabled': c.execute(text('UPDATE proveedores SET activo=false'))
        elif change == 'account_disabled': c.execute(text('UPDATE usuarios SET activo=false WHERE id=:id'), {'id':provider.id})
        elif change == 'first_login': c.execute(text('UPDATE usuarios SET primer_ingreso=true WHERE id=:id'), {'id':provider.id})
        elif change == 'provider_unlinked': c.execute(text('UPDATE proveedores SET usuario_id=NULL'))
        else:
            target=case.actors['inquilino']
            c.execute(text("UPDATE inquilinos SET propiedad_id=NULL,estado='sin_propiedad_asignada'"))
    with pytest.raises(ConversationError): case.chat.thread_messages(qid,target)
    assert not any(row['id']==qid for row in case.chat.inbox(target)['items']) if change not in ('account_disabled','first_login') else True


def test_two_senders_and_retries_keep_one_sequence(conversation_case):
    case, provider, tenant = conversation_case, conversation_case.providers[0], conversation_case.actors['inquilino']
    qid, body, barrier = inquiry(case), message(), Barrier(2)
    def same(_):
        barrier.wait(timeout=5)
        return case.chat.thread_send(qid,provider,body)
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(same,range(2)))
    assert sorted(r['repetido'] for r in results)==[False,True]
    barrier=Barrier(2)
    def different(user):
        barrier.wait(timeout=5)
        return case.chat.thread_send(qid,user,message('Texto de cada participante'))
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(different,[provider,tenant]))
    assert [m['numero'] for m in case.chat.thread_messages(qid,provider)['items']]==[1,2,3,4]


def test_concurrent_open_and_close_are_idempotent(conversation_case):
    case, provider, rid = conversation_case, conversation_case.providers[0], conversation_case.requests[0]
    barrier=Barrier(2)
    def opening(_):
        barrier.wait(timeout=5)
        return case.chat.open_questions(rid,provider,action())
    with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(opening,range(2)))
    assert rows[0]['id']==rows[1]['id']
    qid, barrier=rows[0]['id'],Barrier(2)
    def closing(_):
        barrier.wait(timeout=5)
        return case.chat.finish_questions(qid,provider,action())
    with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(closing,range(2)))
    assert sorted(r['repetido'] for r in rows)==[False,True]
    assert scalar(case, "SELECT count(*) FROM aari_conversacion_mensajes WHERE clave_evento='consulta:cierre'")==1


def test_close_committed_while_sender_waits_blocks_late_message(conversation_case):
    case, provider = conversation_case, conversation_case.providers[0]
    qid, started = inquiry(case), Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with case.db.begin() as c:
            c.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'), {'id':case.claim})
            c.execute(text('''UPDATE aari_conversaciones SET consultas_cerradas_en=clock_timestamp(),
                cierre_request_id=:key WHERE id=:id'''), {'id':qid,'key':uuid4()})
            def late():
                started.set()
                return case.chat.thread_send(qid,provider,message())
            future=pool.submit(late)
            assert started.wait(timeout=3)
        with pytest.raises(ConversationError): future.result(timeout=8)
    assert scalar(case, "SELECT count(*) FROM aari_conversacion_mensajes WHERE origen='humano'")==0


def test_source_projection_failure_rolls_back_quote_and_mail(conversation_case, monkeypatch):
    case, provider = conversation_case, conversation_case.providers[0]
    before=scalar(case,'SELECT count(*) FROM notificaciones')
    def fail(*_args,**_kwargs): raise RuntimeError('Falla sintética')
    monkeypatch.setattr('app.db.conversations._append',fail)
    with pytest.raises(RuntimeError): case.portal.submit(case.requests[0],provider,budget())
    assert scalar(case,'SELECT count(*) FROM presupuestos')==0
    assert scalar(case,'SELECT count(*) FROM notificaciones')==before


def test_database_rls_and_append_only_history(conversation_case):
    case=conversation_case
    for table in ('aari_conversaciones','aari_conversacion_mensajes','aari_conversacion_lecturas'):
        assert scalar(case,'SELECT relrowsecurity FROM pg_class WHERE oid=cast(:table AS regclass)',table=table)
        for role in ('anon','authenticated'):
            assert not scalar(case,"SELECT has_table_privilege(:role,:table,'SELECT,INSERT,UPDATE,DELETE')",role=role,table=table)
    for sql in ("UPDATE aari_conversacion_mensajes SET texto='Alterado'",'DELETE FROM aari_conversacion_mensajes'):
        with pytest.raises(DBAPIError):
            with case.db.begin() as c: c.execute(text(sql))


def test_open_retry_after_close_and_quote_recovers_without_reopening(conversation_case):
    case, provider, rid = conversation_case, conversation_case.providers[0], conversation_case.requests[0]
    key = action()
    qid = case.chat.open_questions(rid, provider, key)['id']
    case.chat.finish_questions(qid, provider, action())
    case.portal.submit(rid, provider, budget())
    assert case.chat.open_questions(rid, provider, key) == {'id': qid, 'repetido': True}
    assert not case.chat.thread_messages(qid, provider)['puede_enviar']
    with pytest.raises(ConversationError): case.chat.open_questions(rid, provider, action())


def test_inbox_projection_and_quote_submission_share_safe_lock_order(conversation_case):
    case, provider, rid = conversation_case, conversation_case.providers[0], conversation_case.requests[0]
    # Evento durable legado pendiente de proyección; HU19 normal lo haría atómico.
    with case.db.begin() as c:
        c.execute(text("INSERT INTO aari_presupuesto_eventos(ronda_id,tipo) SELECT ronda_id,'revision' FROM aari_solicitudes_presupuesto WHERE id=:id"), {'id': rid})
    barrier = Barrier(2)
    def read():
        barrier.wait(timeout=5)
        return case.chat.inbox(case.actor)
    def submit():
        barrier.wait(timeout=5)
        return case.portal.submit(rid, provider, budget())
    with ThreadPoolExecutor(max_workers=2) as pool:
        reads, submits = pool.submit(read), pool.submit(submit)
        assert reads.result(timeout=12)['items']
        assert submits.result(timeout=12)['presupuesto']
    items = case.chat.messages(rid, case.actor)['items']
    assert len([item for item in items if 'presentó su presupuesto' in item['texto']]) == 1
