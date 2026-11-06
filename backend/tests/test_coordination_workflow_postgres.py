"""AARI-345: recorridos con dominio/checkpoints/Mensajes reales, sólo DB local."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from threading import Barrier
from uuid import uuid4

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.agents.coordination.state import ResumeRequest
from app.agents.coordination.graph import build_coordination_graph
from app.db.coordination import PostgresCoordinationRepository
from app.db.coordination_cancellations import SqlAlchemyCoordinationCancellations
from app.db.conversations import SqlAlchemyConversations
from app.db.external_providers import SqlAlchemyExternalProvidersRepository
from app.db.quote_selections import SqlAlchemyQuoteSelections
from app.db.visits import SqlAlchemyVisits
from app.schemas.conversations import ConversationMessageRequest
from app.schemas.coordination_cancellations import CoordinationCancellationRequest
from app.schemas.expense_authorizations import ExpenseDecisionRequest
from app.schemas.external_providers import ExternalProviderRequest
from app.schemas.visits import VisitAction, VisitConfirmationRequest, VisitProposalRequest
from app.services.coordination_service import CoordinationError
from scripts.check_coordination_postgres import apply, verify
from tests.test_quote_portal_postgres import portal_case, active_provider, budget, scalar
from tests.test_provider_choices_postgres import choice_base, body as choice_body
from tests.test_responsible_actor_postgres import claim_case, local_engine, MIGRATIONS, classification
from tests.test_quote_selections_postgres import selection
from tests.test_visits_postgres import publish, action

pytestmark = pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'), reason='PostgreSQL local descartable.')


@pytest.fixture
def workflow_case(portal_case, monkeypatch):
    c = portal_case
    for name in ('20261028210000_hu33_conversaciones.sql',
                 '20261029120000_hu20_seleccion_presupuesto.sql',
                 '20261029235000_hu18_proveedor_externo.sql',
                 '20261101110000_hu23_coordinacion_visitas.sql',
                 '20261102103000_hu23_seleccion_auditada.sql',
                 '20261103120000_hu24_cancelacion_coordinacion.sql'):
        with c.db.connect() as conn:
            cursor = conn.connection.cursor()
            cursor.execute((MIGRATIONS / name).read_text(encoding='utf-8'))
            conn.commit()
            cursor.close()
    for flag in ('AARI_CONVERSATIONS_ENABLED', 'AARI_VISITS_ENABLED', 'AARI_CANCELLATIONS_ENABLED'):
        monkeypatch.setenv(flag, 'true')
    url = c.db.url
    def connect():
        return psycopg.connect(host=url.host, port=url.port, dbname=url.database,
            user=url.username, password=url.password, row_factory=dict_row, prepare_threshold=None)
    c.connect = connect
    with connect() as conn:
        apply(conn)
        verify(conn)
        conn.execute("UPDATE public.usuarios SET primer_ingreso=false WHERE rol='operador'")
    c.now = datetime.now(timezone.utc)
    c.selection = SqlAlchemyQuoteSelections(sessionmaker(bind=c.db))
    c.visits = SqlAlchemyVisits(sessionmaker(bind=c.db))
    c.cancel = SqlAlchemyCoordinationCancellations(sessionmaker(bind=c.db))
    c.external = SqlAlchemyExternalProvidersRepository(sessionmaker(bind=c.db))
    c.messages = SqlAlchemyConversations(sessionmaker(bind=c.db))
    c.tenant = c.actors['inquilino']
    c.provider = active_provider(c)
    return c


def repository(c):
    # Un repositorio nuevo por turno: no depende de memoria del proceso anterior.
    return PostgresCoordinationRepository(c.connect, clock=lambda: c.now)


def begin(c, expense='ordinario'):
    c.claims.persist_classification(c.claim, classification(expense))
    c.actor = c.actors['inquilino' if expense == 'ordinario' else 'propietario']
    c.initial_request = ResumeRequest(evento_id=uuid4(), version_esperada=0)
    first = repository(c).resume(c.claim, c.initial_request, c.actor)
    c.initial = first
    return first


def sync(c, stage):
    repo = repository(c)
    repo.synchronize_due(limit=100)
    value = repo.get(c.claim, c.actor)
    assert not value.requiere_sincronizacion
    assert value.contexto.etapa == stage
    assert value.ultima_actividad == c.initial.ultima_actividad
    return value


def authorize(c):
    detail = c.auth.get(c.claim, c.actor)
    c.auth.decide(c.claim, c.actor, ExpenseDecisionRequest(
        request_id=uuid4(), expected_updated_at=detail.updated_at), decision='autorizar')
    return sync(c, 'esperando_eleccion_proveedor')


def choose(c, kind='fidelizado'):
    c.repo.choose(c.claim, c.actor, choice_body(c, kind))
    return sync(c, 'esperando_presupuestos' if kind == 'fidelizado' else 'esperando_datos_proveedor')


def quotes(c, *, close=True):
    c.portal.publish(c.claim)
    waiting = sync(c, 'esperando_presupuestos')
    c.rid = c.portal.list_own(c.provider)['items'][0]['id']
    c.portal.submit(c.rid, c.provider, budget())
    # Recibir un presupuesto no cierra por sí solo la ronda de 24 horas.
    assert repository(c).get(c.claim, c.actor).contexto.etapa == 'esperando_presupuestos'
    if close:
        with c.db.begin() as conn:
            conn.execute(text("""UPDATE aari_rondas_presupuesto
                SET publicada_en=clock_timestamp()-interval '25 hours',
                    vence_en=clock_timestamp()-interval '1 hour' WHERE id=:id"""),
                {'id': waiting.contexto.dominio.ronda_id})
        assert c.portal.finalize_one_portal(waiting.contexto.dominio.ronda_id, c.claim)
        return sync(c, 'esperando_seleccion_presupuesto')
    return waiting


def select_and_start(c):
    c.selection.choose(c.claim, c.actor, selection(c))
    sync(c, 'esperando_disponibilidad')
    c.visits.tick()
    c.visits.tick()  # El cursor HU23 puede necesitar volver al inicio.
    return sync(c, 'esperando_disponibilidad')


def finish(c, *, negotiate=False):
    availability = publish(c)
    waiting = sync(c, 'esperando_confirmacion_visita')
    assert waiting.contexto.dominio.vencimiento_especifico is not None
    if negotiate:
        c.visits.act(c.claim, c.provider, 'sin-coincidencia', VisitAction(**action(c, c.provider)))
        before = sync(c, 'negociando_visita')
        thread = c.visits.get(c.claim, c.tenant)['hilo_id']
        c.messages.thread_send(thread, c.provider, ConversationMessageRequest(
            request_id=uuid4(), texto='Podemos acordar otra fecha en la propuesta estructurada.'))
        assert repository(c).synchronize_due() == 0
        assert repository(c).get(c.claim, c.actor).contexto == before.contexto
        proposal = c.visits.act(c.claim, c.provider, 'proponer', VisitProposalRequest(
            **action(c, c.provider), fecha=availability.opciones[0].desde))
        sync(c, 'negociando_visita')
        c.visits.act(c.claim, c.tenant, 'confirmar', VisitConfirmationRequest(
            **action(c), propuesta_version=proposal['propuesta']['version']))
    else:
        c.visits.act(c.claim, c.provider, 'confirmar', VisitConfirmationRequest(
            **action(c, c.provider), fecha=availability.opciones[0].desde))
    terminal = sync(c, 'visita_programada')
    assert scalar(c, 'SELECT estado_sesion FROM sesiones_agente') == 'finalizada'
    assert terminal.contexto.dominio.fecha_visita is not None
    assert scalar(c, 'SELECT count(*) FROM visitas') == 1
    state = durable(c)
    assert repository(c).synchronize_due() == 0
    assert repository(c).expire_due() == 0
    with pytest.raises(CoordinationError):
        repository(c).resume(c.claim, ResumeRequest(evento_id=uuid4(),
            version_esperada=terminal.contexto.version, intento_id=terminal.contexto.intento_id), c.actor)
    assert durable(c) == state
    return terminal


def durable(c):
    with c.connect() as conn:
        return [conn.execute(sql).fetchall() for sql in (
            'SELECT * FROM public.sesiones_agente ORDER BY reclamo_id',
            'SELECT * FROM aari_coordinacion.eventos ORDER BY reclamo_id,evento_id',
            'SELECT * FROM aari_coordinacion.checkpoints ORDER BY thread_id,checkpoint_id',
            'SELECT * FROM public.reclamos ORDER BY id',
            'SELECT * FROM public.notificaciones ORDER BY id')]


@pytest.mark.parametrize('expense,negotiate', [('ordinario', False), ('extraordinario', True)])
def test_real_multi_turn_authorization_quote_selection_and_visit(workflow_case, expense, negotiate):
    c = workflow_case
    begin(c, expense)
    if expense == 'extraordinario': authorize(c)
    choose(c)
    quotes(c)
    selected = select_and_start(c)
    assert selected.contexto.dominio.seleccion_id is not None
    finish(c, negotiate=negotiate)


@pytest.mark.parametrize('expense', ['ordinario', 'extraordinario'])
def test_real_own_provider_derivation_is_a_durable_terminal(workflow_case, expense):
    c = workflow_case
    begin(c, expense)
    if expense == 'extraordinario': authorize(c)
    choose(c, 'propio')
    info = c.external.get(c.claim, c.actor)
    c.external.register(c.claim, c.actor, ExternalProviderRequest(request_id=uuid4(),
        eleccion_id=info.eleccion_id, expected_updated_at=info.updated_at,
        nombre='Persona Sintética', telefono='+54 (11) 5555-0100'))
    sync(c, 'derivado_externo')
    assert scalar(c, 'SELECT estado_sesion FROM sesiones_agente') == 'finalizada'
    assert scalar(c, 'SELECT count(*) FROM proveedores_externos') == 1


@pytest.mark.parametrize('stage', ['presupuestos', 'comparacion', 'visita'])
def test_real_cancellation_reselection_and_new_visit_keep_history(workflow_case, stage):
    c = workflow_case
    begin(c, 'extraordinario')
    authorize(c)
    authorization = scalar(c, 'SELECT request_id FROM reclamo_autorizaciones')
    choose(c)
    quotes(c, close=stage != 'presupuestos')
    old = repository(c).get(c.claim, c.actor)
    thread = None
    if stage == 'visita':
        select_and_start(c)
        publish(c)
        old = sync(c, 'esperando_confirmacion_visita')
        thread = c.visits.get(c.claim, c.tenant)['hilo_id']
    detail = c.cancel.get(c.claim, c.actor)
    payload = CoordinationCancellationRequest(request_id=uuid4(), eleccion_id=detail['eleccion_id'],
        expected_updated_at=detail['updated_at'], confirmar=True)
    c.cancel.cancel(c.claim, c.actor, payload)
    renewed = sync(c, 'esperando_eleccion_proveedor')
    assert renewed.contexto.intento_id != old.contexto.intento_id
    assert renewed.contexto.dominio.eleccion_id != old.contexto.dominio.eleccion_id
    assert renewed.contexto.dominio.ronda_id is None
    assert renewed.contexto.dominio.proveedor_id is None
    assert scalar(c, 'SELECT request_id FROM reclamo_autorizaciones') == authorization
    before = durable(c)
    c.cancel.cancel(c.claim, c.actor, payload)
    assert repository(c).synchronize_due() == 0 and durable(c) == before
    with pytest.raises(CoordinationError):
        repository(c).resume(c.claim, ResumeRequest(evento_id=uuid4(),
            version_esperada=old.contexto.version, intento_id=old.contexto.intento_id), c.actor)
    choose(c)
    quotes(c)
    select_and_start(c)
    terminal = finish(c)
    assert terminal.contexto.intento_id == renewed.contexto.intento_id
    assert scalar(c, 'SELECT count(*) FROM presupuestos') == 2
    if thread:
        history = c.messages.thread_messages(thread, c.tenant)
        assert not history['puede_enviar']
        assert any('canceló' in item['texto'] for item in history['items'])


@pytest.fixture(params=['psycopg2', 'psycopg'])
def cancellation_driver_case(request, monkeypatch):
    # Elegir el controlador antes de construir la base descartable del fixture.
    url = make_url(os.environ['AARI_TEST_POSTGRES_URL'])
    assert url.get_backend_name() == 'postgresql'
    assert url.host in {'127.0.0.1', 'localhost', '::1'}, 'Sólo PostgreSQL local.'
    url = url.set(drivername=f'postgresql+{request.param}')
    monkeypatch.setenv('AARI_TEST_POSTGRES_URL', url.render_as_string(hide_password=False))
    case = request.getfixturevalue('workflow_case')
    assert case.db.dialect.driver == request.param
    return case


@pytest.mark.parametrize('expense', ['ordinario', 'extraordinario'])
@pytest.mark.parametrize('stage', ['recepcion', 'comparacion', 'seleccion'])
def test_cancellation_recipient_uuid_is_typed_for_both_drivers(cancellation_driver_case, expense, stage):
    c = cancellation_driver_case
    begin(c, expense)
    if expense == 'extraordinario':
        authorize(c)
    active_provider(c, n=1)
    choose(c)
    quotes(c, close=stage != 'recepcion')
    if stage == 'seleccion':
        select_and_start(c)
    selected = scalar(c, 'SELECT proveedor_seleccionado_id FROM reclamos WHERE id=:id', id=c.claim)
    assert (selected is not None) == (stage == 'seleccion')
    detail = c.cancel.get(c.claim, c.actor)
    payload = CoordinationCancellationRequest(request_id=uuid4(), eleccion_id=detail['eleccion_id'],
        expected_updated_at=detail['updated_at'], confirmar=True)
    result = c.cancel.cancel(c.claim, c.actor, payload)
    assert result['repetida'] is False
    assert scalar(c, 'SELECT count(*) FROM reclamo_cancelaciones_coordinacion') == 1
    assert scalar(c, 'SELECT estado FROM reclamos WHERE id=:id', id=c.claim) == result['estado_resultante']
    key = f"hu24:{result['id']}:proveedor:%"
    expected = 1 if stage == 'seleccion' else 2
    assert scalar(c, 'SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :key', key=key) == expected
    before = durable(c)
    assert c.cancel.cancel(c.claim, c.actor, payload)['repetida'] is True
    assert durable(c) == before


def test_real_rejection_sync_does_not_reopen_or_repeat_notifications(workflow_case):
    c = workflow_case
    begin(c, 'extraordinario')
    info = c.auth.get(c.claim, c.actor)
    c.auth.decide(c.claim, c.actor, ExpenseDecisionRequest(
        request_id=uuid4(), expected_updated_at=info.updated_at), decision='rechazar')
    sync(c, 'rechazado')
    before = durable(c)
    assert repository(c).synchronize_due() == 0
    assert durable(c) == before


def test_domain_commit_survives_projection_failure_and_recovers(workflow_case, monkeypatch):
    c = workflow_case
    begin(c)
    c.repo.choose(c.claim, c.actor, choice_body(c))
    before = durable(c)
    original = PostgresCoordinationRepository._checkpoint
    def fail(conn, snapshot, event):
        original(conn, snapshot, event)
        raise ValueError('Fallo sintético después del checkpoint.')
    with monkeypatch.context() as scope:
        scope.setattr(PostgresCoordinationRepository, '_checkpoint', staticmethod(fail))
        assert repository(c).synchronize_due() == 0
    assert durable(c) == before
    sync(c, 'esperando_presupuestos')


def test_two_reconcilers_write_one_version_and_polling_never_refreshes(workflow_case):
    c = workflow_case
    first = begin(c)
    c.repo.choose(c.claim, c.actor, choice_body(c))
    barrier = Barrier(2)
    def work(_):
        barrier.wait(timeout=10)
        return repository(c).synchronize_due()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(work, range(2))) == 1
    result = repository(c).get(c.claim, c.actor)
    assert result.contexto.version == first.contexto.version+1
    before = durable(c)
    c.now += timedelta(hours=10)
    for _ in range(3):
        assert repository(c).synchronize_due() == 0
        repository(c).get(c.claim, c.actor)
    assert durable(c) == before


def test_closed_quote_round_uses_general_72h_without_refreshing_specific_deadlines(workflow_case):
    c = workflow_case
    begin(c)
    choose(c)
    waiting = quotes(c)
    assert waiting.contexto.dominio.vencimiento_especifico is None
    c.now = c.initial.ultima_actividad+timedelta(hours=72)-timedelta(microseconds=1)
    assert repository(c).expire_due() == 0
    c.now += timedelta(microseconds=1)
    assert repository(c).expire_due() == 1
    assert repository(c).expire_due() == 0
    assert repository(c).get(c.claim, c.actor).contexto.etapa == 'expirada'
    assert scalar(c, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :pattern",
                  pattern='hu21:%:expiracion') == 1


@pytest.mark.parametrize('change', ['inactive', 'first_login', 'tenant_moved', 'tenant_inactive',
                                   'wrong_profile', 'owner_unlinked'])
def test_current_identity_is_required_even_for_an_existing_checkpoint(workflow_case, change):
    c = workflow_case
    first = begin(c, 'extraordinario' if change == 'owner_unlinked' else 'ordinario')
    with c.db.begin() as conn:
        if change == 'inactive':
            conn.execute(text('UPDATE usuarios SET activo=false WHERE id=:id'), {'id': c.actor.id})
        elif change == 'first_login':
            conn.execute(text('UPDATE usuarios SET primer_ingreso=true WHERE id=:id'), {'id': c.actor.id})
        elif change == 'tenant_moved':
            new_property = conn.execute(text('''INSERT INTO propiedades(direccion,provincia,localidad,tipo,propietario_id)
                SELECT 'Otra unidad sintética.',provincia,localidad,tipo,propietario_id
                FROM propiedades LIMIT 1 RETURNING id''')).scalar_one()
            conn.execute(text('UPDATE inquilinos SET propiedad_id=:id'), {'id': new_property})
        elif change == 'tenant_inactive':
            conn.execute(text("UPDATE inquilinos SET estado='sin_propiedad_asignada',propiedad_id=NULL"))
        elif change == 'owner_unlinked':
            conn.execute(text('UPDATE propietarios SET usuario_id=NULL'))
        else:
            c.actor = c.actor.model_copy(update={'perfil_id': uuid4()})
    before = durable(c)
    with pytest.raises(CoordinationError): repository(c).get(c.claim, c.actor)
    with pytest.raises(CoordinationError):
        repository(c).resume(c.claim, ResumeRequest(evento_id=uuid4(),
            version_esperada=first.contexto.version, intento_id=first.contexto.intento_id), c.actor)
    assert durable(c) == before


def test_reconciliation_page_advances_past_unchanged_and_locked_claims(workflow_case):
    c = workflow_case
    begin(c)
    first_claim = c.claim
    first_actor = c.actor
    with c.db.begin() as conn:
        property_id = conn.execute(text('''INSERT INTO propiedades(direccion,provincia,localidad,tipo,propietario_id)
            SELECT 'Unidad sintética de paginación.',provincia,localidad,tipo,propietario_id
            FROM propiedades LIMIT 1 RETURNING id''')).scalar_one()
        user_id = conn.execute(text('''INSERT INTO usuarios(email,password_hash,rol,primer_ingreso)
            VALUES ('tenant-page@example.com','unused','inquilino',false) RETURNING id''')).scalar_one()
        profile_id = conn.execute(text('''INSERT INTO inquilinos(nombre_completo,dni,email,telefono,propiedad_id,usuario_id)
            VALUES ('Inquilino Sintetico Dos','10000005','tenant-page@example.com','00000000',:property,:user)
            RETURNING id'''), {'property': property_id, 'user': user_id}).scalar_one()
        second_claim = conn.execute(text('''INSERT INTO reclamos(descripcion,urgencia,inquilino_id,propiedad_id)
            VALUES ('Segundo caso sintético de paginación.','media',:tenant,:property) RETURNING id'''),
            {'tenant': profile_id, 'property': property_id}).scalar_one()
    second_actor = first_actor.model_copy(update={'id': user_id,
        'email': 'tenant-page@example.com', 'perfil_id': profile_id})
    c.claim = second_claim
    c.actors['inquilino'] = second_actor
    begin(c)
    c.claim = max(first_claim, second_claim)
    c.actor = first_actor if c.claim == first_claim else second_actor
    c.repo.choose(c.claim, c.actor, choice_body(c))
    worker = repository(c)
    assert worker.synchronize_due(limit=1) == 0  # Primera página sin cambios.
    with c.connect() as conn:
        conn.execute('SELECT id FROM public.reclamos WHERE id=%s FOR UPDATE', (c.claim,))
        assert worker.synchronize_due(limit=1) == 0  # No esperar un lock ajeno.
    assert worker.synchronize_due(limit=1) == 0  # Vuelta del cursor.
    assert worker.synchronize_due(limit=1) == 0  # Otra vez la fila sin cambios.
    assert worker.synchronize_due(limit=1) == 1  # Recupera la fila antes bloqueada.
    assert not repository(c).get(c.claim, c.actor).requiere_sincronizacion


@pytest.mark.parametrize('expense', ['ordinario', 'expensa'])
def test_reconciliation_does_not_initialize_history_or_touch_expenses(workflow_case, expense):
    c = workflow_case
    c.claims.persist_classification(c.claim, classification(expense))
    before = durable(c)
    assert repository(c).synchronize_due() == 0
    assert repository(c).expire_due() == 0
    assert durable(c) == before


def unprojected_reelection(c, expense):
    """Avanza módulos reales sin reconciliar HU21 después de cancelar."""
    begin(c, expense)
    if expense == 'extraordinario': authorize(c)
    choose(c)
    quotes(c)
    old = repository(c).get(c.claim, c.actor)
    detail = c.cancel.get(c.claim, c.actor)
    c.cancel.cancel(c.claim, c.actor, CoordinationCancellationRequest(request_id=uuid4(),
        eleccion_id=detail['eleccion_id'], expected_updated_at=detail['updated_at'], confirmar=True))
    choice = choice_body(c)
    c.repo.choose(c.claim, c.actor, choice)
    c.portal.publish(c.claim)
    rid = c.portal.list_own(c.provider)['items'][0]['id']
    c.portal.submit(rid, c.provider, budget())
    round_id = scalar(c, 'SELECT id FROM aari_rondas_presupuesto WHERE eleccion_id=:id',
                      id=choice.solicitud_id)
    with c.db.begin() as conn:
        conn.execute(text("""UPDATE aari_rondas_presupuesto
            SET publicada_en=clock_timestamp()-interval '25 hours',
                vence_en=clock_timestamp()-interval '1 hour' WHERE id=:id"""), {'id': round_id})
    assert c.portal.finalize_one_portal(round_id, c.claim)
    c.now = c.initial.ultima_actividad+timedelta(hours=73)
    assert repository(c).get(c.claim, c.actor).requiere_sincronizacion
    return old


def assert_expired_attempt(c, old_attempt, expected_attempt=None):
    repo = repository(c)
    expired = repo.get(c.claim, c.actor)
    attempt = expired.contexto.intento_id
    assert attempt != old_attempt
    if expected_attempt is not None:
        assert attempt == expected_attempt
    assert expired.contexto.etapa == 'expirada' and not expired.requiere_sincronizacion
    assert expired.contexto.dominio.cancelacion_id == scalar(c, 'SELECT id FROM cancelaciones')
    assert expired.ultima_actividad == c.initial.ultima_actividad
    with c.connect() as conn:
        conn.execute('SET LOCAL search_path=aari_coordinacion,pg_catalog')
        session = conn.execute('SELECT * FROM public.sesiones_agente WHERE reclamo_id=%s',
                               (c.claim,)).fetchone()
        checkpoint = build_coordination_graph(PostgresSaver(conn)).get_state(
            {'configurable': {'thread_id': str(c.claim)}}).values['contexto']
        assert session['intento_id'] == attempt
        assert session['estado_grafo'] == checkpoint == expired.contexto.model_dump(mode='json')
        event = conn.execute('SELECT intento_id FROM aari_coordinacion.eventos '
                             'WHERE reclamo_id=%s ORDER BY version DESC LIMIT 1', (c.claim,)).fetchone()
        assert event['intento_id'] == attempt
    key = f"hu21:{session['id']}:{attempt}:expiracion"
    assert scalar(c, 'SELECT count(*) FROM notificaciones WHERE clave_idempotencia=:key', key=key) == 1
    before = durable(c)
    assert repo.synchronize_due() == 0 and repo.expire_due() == 0
    assert durable(c) == before


@pytest.mark.parametrize('expense', ['ordinario', 'extraordinario'])
@pytest.mark.parametrize('already_synced', [False, True])
def test_expiration_reconciles_same_claim_when_sync_page_missed_it(workflow_case, expense, already_synced):
    c = workflow_case
    old = unprojected_reelection(c, expense)
    worker = repository(c)
    worker._sync_cursor = type(c.claim)(int=(1 << 128)-1)
    assert worker.synchronize_due(limit=1) == 0  # Quedó fuera del lote por el cursor.
    expected = None
    if already_synced:
        assert worker.synchronize_due(limit=1) == 1  # Control: ya tiene el intento nuevo.
        expected = worker.get(c.claim, c.actor).contexto.intento_id
    assert worker.expire_due(limit=1) == 1
    assert_expired_attempt(c, old.contexto.intento_id, expected)


@pytest.mark.parametrize('expense', ['ordinario', 'extraordinario'])
def test_expiration_rolls_back_its_reconciliation_if_alert_fails(workflow_case, expense):
    c = workflow_case
    old = unprojected_reelection(c, expense)
    with c.connect() as conn:
        conn.execute("""CREATE FUNCTION public.fail_expiration_alert() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.clave_idempotencia LIKE 'hu21:%:expiracion' THEN
                RAISE EXCEPTION 'Fallo sintético al guardar alerta';
            END IF; RETURN NEW; END $$""")
        conn.execute('CREATE TRIGGER fail_expiration_alert BEFORE INSERT ON public.notificaciones '
                     'FOR EACH ROW EXECUTE FUNCTION public.fail_expiration_alert()')
    before = durable(c)
    with pytest.raises(psycopg.Error): repository(c).expire_due()
    assert durable(c) == before
    with c.connect() as conn:
        conn.execute('DROP TRIGGER fail_expiration_alert ON public.notificaciones')
        conn.execute('DROP FUNCTION public.fail_expiration_alert()')
    assert repository(c).expire_due() == 1
    assert_expired_attempt(c, old.contexto.intento_id)


@pytest.mark.parametrize('expense', ['ordinario', 'extraordinario'])
def test_selection_competes_with_expiration_of_unprojected_reelection(workflow_case, expense):
    c = workflow_case
    old = unprojected_reelection(c, expense)
    payload = selection(c)
    barrier = Barrier(2)
    def run(index):
        barrier.wait(timeout=10)
        if index == 0:
            return repository(c).expire_due()
        from app.services.quote_portal import QuotePortalError
        try:
            c.selection.choose(c.claim, c.actor, payload)
            return 1
        except QuotePortalError:
            return 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(run, range(2))) == 1
    if scalar(c, 'SELECT estado FROM reclamos') == 'Sesión expirada':
        assert_expired_attempt(c, old.contexto.intento_id)
    else:
        result = sync(c, 'esperando_disponibilidad')
        assert result.contexto.intento_id != old.contexto.intento_id
        assert scalar(c, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 1
