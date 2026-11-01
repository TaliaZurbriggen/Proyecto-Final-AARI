"""HU20 con HU19/17/16 reales, PostgreSQL LOCAL descartable y sin red."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.quote_selections import SqlAlchemyQuoteSelections
from app.schemas.quote_selections import QuoteSelectionRequest
from app.services.quote_portal import QuotePortalError
from app.services.claim_notifications import ClaimEmailDeliveryError, ClaimNotificationService
from tests.test_quote_portal_postgres import (
    portal_case, active_provider, request, budget, scalar, past_deadline,
)
from tests.test_provider_choices_postgres import choice_base
from tests.test_responsible_actor_postgres import claim_case, local_engine, MIGRATIONS
from tests.test_quote_requests_postgres import eligible


pytestmark = pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'), reason='Sólo PostgreSQL local descartable.')


@pytest.fixture
def selection_case(portal_case, monkeypatch):
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED', 'false')
    with portal_case.db.connect() as c:
        cursor = c.connection.cursor()
        cursor.execute((MIGRATIONS/'20261029120000_hu20_seleccion_presupuesto.sql').read_text(encoding='utf-8'))
        c.connection.commit()
        cursor.close()
    portal_case.selection = SqlAlchemyQuoteSelections(sessionmaker(bind=portal_case.db))
    return portal_case


def quoted(case, expense='ordinario', count=1):
    eligible(case, expense)
    users = [active_provider(case, i) for i in range(count)]
    case.portal.publish(case.claim)
    for i, user in enumerate(users):
        p = budget().model_copy(update={'monto': budget().monto + i})
        case.portal.submit(request(case, user)['id'], user, p)
    return users


def selection(case, index=0, **changes):
    view = case.selection.get(case.claim, case.actor)
    return QuoteSelectionRequest(request_id=uuid4(), ronda_id=view['ronda_id'],
        expected_updated_at=view['updated_at'], modalidad='fidelizado',
        presupuesto_id=view['items'][index]['id'], **changes)


@pytest.mark.parametrize('expense', ['ordinario', 'extraordinario'])
@pytest.mark.parametrize('kind', ['exacto', 'minimo'])
def test_selects_current_quote_and_replays_without_duplicate_notice(selection_case, expense, kind):
    case = selection_case
    quoted(case, expense)
    with case.db.begin() as c:
        c.execute(text('UPDATE presupuestos SET tipo_importe=:kind'), {'kind': kind})
    payload = selection(case)
    first = case.selection.choose(case.claim, case.actor, payload)
    assert first['tipo_importe'] == kind and first['monto'] == '10000.50'
    assert first['estado_resultante'] == 'Proveedor seleccionado'
    assert case.selection.choose(case.claim, case.actor, payload)['repetida']
    assert scalar(case, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 1
    assert scalar(case, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE 'hu20:%'") == 1
    assert scalar(case, 'SELECT fecha_visita FROM reclamos') is None
    assert case.selection.get(case.claim, case.actor)['decision']['id'] == first['id']
    assert not case.selection.get(case.claim, case.actor)['puede_elegir']


def test_reading_own_provider_alternative_never_changes_domain(selection_case):
    case = selection_case
    users = quoted(case)
    with case.db.connect() as c:
        original = dict(c.execute(text('SELECT * FROM reclamo_elecciones_proveedor')).mappings().one())
    case.selection.get(case.claim, case.actor)
    assert scalar(case, 'SELECT estado FROM reclamos') == 'Pendiente de asignación'
    assert scalar(case, 'SELECT count(*) FROM proveedores_externos') == 0
    assert scalar(case, 'SELECT cerrada_en FROM aari_rondas_presupuesto') is None
    assert scalar(case, 'SELECT count(*) FROM presupuestos') == 1
    with case.db.connect() as c:
        assert dict(c.execute(text('SELECT * FROM reclamo_elecciones_proveedor')).mappings().one()) == original
    assert case.portal.get_own(request(case, users[0])['id'], users[0])['estado'] == 'respondida'
    assert scalar(case, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 0


@pytest.mark.parametrize('change', ['inactive', 'coverage', 'description', 'actor', 'state', 'version', 'round', 'quote'])
def test_stale_selection_never_changes_domain(selection_case, change):
    case = selection_case
    quoted(case)
    payload = selection(case)
    with case.db.begin() as c:
        if change == 'inactive': c.execute(text('UPDATE proveedores SET activo=false'))
        elif change == 'coverage': c.execute(text("UPDATE proveedor_coberturas SET localidad='Otra localidad'"))
        elif change == 'description': c.execute(text("UPDATE reclamos SET descripcion='Descripción modificada por otro proceso sintético'"))
        elif change == 'actor': c.execute(text('UPDATE inquilinos SET usuario_id=NULL'))
        elif change == 'state': c.execute(text("UPDATE reclamos SET estado='Resuelto'"))
        elif change == 'version': c.execute(text('UPDATE reclamos SET updated_at=clock_timestamp()'))
    if change == 'round': payload = payload.model_copy(update={'ronda_id': uuid4()})
    if change == 'quote': payload = payload.model_copy(update={'presupuesto_id': uuid4()})
    with pytest.raises(QuotePortalError): case.selection.choose(case.claim, case.actor, payload)
    assert scalar(case, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 0
    assert scalar(case, 'SELECT proveedor_seleccionado_id FROM reclamos') is None


def test_two_opposite_choices_have_one_winner(selection_case):
    case = selection_case
    quoted(case, count=2)
    payloads = [selection(case, i) for i in range(2)]
    barrier = Barrier(2)
    def choose(p):
        barrier.wait(timeout=5)
        try: return case.selection.choose(case.claim, case.actor, p)
        except QuotePortalError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(x is not None for x in pool.map(choose, payloads)) == 1
    assert scalar(case, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 1


def test_partial_results_survive_deadline_and_late_answers_cannot_reactivate(selection_case):
    case = selection_case
    eligible(case)
    users = [active_provider(case, i) for i in range(2)]
    case.portal.publish(case.claim)
    case.portal.submit(request(case, users[0])['id'], users[0], budget())
    past_deadline(case)
    case.portal.finalize_due_portal()
    case.selection.choose(case.claim, case.actor, selection(case))
    with pytest.raises(QuotePortalError): case.portal.submit(request(case, users[1])['id'], users[1], budget())
    assert scalar(case, 'SELECT estado FROM reclamos') == 'Proveedor seleccionado'


def test_reused_key_and_no_quotes_do_not_fabricate_selection(selection_case):
    case = selection_case
    eligible(case)
    active_provider(case)
    case.portal.publish(case.claim)
    view = case.selection.get(case.claim, case.actor)
    assert view['items'] == []
    payload = QuoteSelectionRequest(request_id=uuid4(), ronda_id=view['ronda_id'],
        expected_updated_at=view['updated_at'], modalidad='fidelizado', presupuesto_id=uuid4())
    with pytest.raises(QuotePortalError): case.selection.choose(case.claim, case.actor, payload)
    assert scalar(case, 'SELECT count(*) FROM presupuestos') == 0


def test_chat_notice_only_reaches_selected_provider_and_responsible(selection_case, monkeypatch):
    case = selection_case
    with case.db.connect() as c:
        cursor = c.connection.cursor()
        cursor.execute((MIGRATIONS/'20261028210000_hu33_conversaciones.sql').read_text(encoding='utf-8'))
        c.connection.commit()
        cursor.close()
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED', 'true')
    quoted(case, count=2)
    payload = selection(case)
    case.selection.choose(case.claim, case.actor, payload)
    assert scalar(case, "SELECT count(*) FROM aari_conversacion_mensajes WHERE clave_evento LIKE 'hu20:%'") == 2
    assert case.selection.choose(case.claim, case.actor, payload)['repetida']
    assert scalar(case, "SELECT count(*) FROM aari_conversacion_mensajes WHERE clave_evento LIKE 'hu20:%'") == 2


def test_same_key_with_different_quote_cannot_overwrite_selection(selection_case):
    case = selection_case
    quoted(case, count=2)
    payload, other = selection(case), selection(case, 1)
    first = case.selection.choose(case.claim, case.actor, payload)
    with pytest.raises(QuotePortalError):
        case.selection.choose(case.claim, case.actor,
                              other.model_copy(update={'request_id': payload.request_id}))
    assert scalar(case, 'SELECT presupuesto_seleccionado_id FROM reclamos') == first['presupuesto_id']
    assert scalar(case, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 1


def test_simultaneous_retries_of_same_request_return_same_decision(selection_case):
    case = selection_case
    quoted(case)
    payload = selection(case)
    barrier = Barrier(2)
    def choose():
        barrier.wait(timeout=5)
        return case.selection.choose(case.claim, case.actor, payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: choose(), range(2)))
    assert results[0]['id'] == results[1]['id']
    assert sum(result['repetida'] for result in results) == 1
    assert scalar(case, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE 'hu20:%'") == 1


def test_failure_in_audit_rolls_back_domain_history_and_notices(selection_case):
    case = selection_case
    quoted(case)
    payload = selection(case)
    def snapshot():
        with case.db.connect() as c:
            return {table: [dict(row) for row in c.execute(text(f'SELECT * FROM {table} ORDER BY id')).mappings()]
                    for table in ('reclamos', 'notificaciones', 'reclamo_historial_estados',
                                  'aari_rondas_presupuesto', 'reclamo_selecciones_presupuesto')}
    before = snapshot()
    def fail_audit(conn, cursor, statement, parameters, context, many):
        if 'INSERT INTO reclamo_selecciones_presupuesto' in statement:
            raise RuntimeError('Fallo sintético al auditar')
    event.listen(case.db, 'before_cursor_execute', fail_audit)
    try:
        with pytest.raises(RuntimeError, match='Fallo sintético'):
            case.selection.choose(case.claim, case.actor, payload)
    finally:
        event.remove(case.db, 'before_cursor_execute', fail_audit)
    assert snapshot() == before
    assert not case.selection.choose(case.claim, case.actor, payload)['repetida']


@pytest.mark.parametrize('change', ['other_actor', 'profile', 'inactive_account', 'first_login', 'role'])
def test_current_identity_and_profile_are_required(selection_case, change):
    case = selection_case
    quoted(case)
    payload = selection(case)
    user = case.actor
    if change == 'other_actor': user = case.actors['propietario']
    elif change == 'profile': user = user.model_copy(update={'perfil_id': uuid4()})
    else:
        assignment = {'inactive_account': 'activo=false', 'first_login': 'primer_ingreso=true',
                      'role': "rol='operador',nombre_completo='Operador Sintetico'"}[change]
        with case.db.begin() as c:
            c.execute(text(f'UPDATE usuarios SET {assignment} WHERE id=:id'), {'id': user.id})
    for operation in (lambda: case.selection.get(case.claim, user),
                      lambda: case.selection.choose(case.claim, user, payload)):
        with pytest.raises(QuotePortalError): operation()
    assert scalar(case, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 0


def test_comparison_orders_amounts_within_currency_and_batches_provider_reads(selection_case):
    case = selection_case
    users = quoted(case, count=3)
    with case.db.begin() as c:
        for user, amount, currency in zip(users, ['100', '20', '1'], ['ARS', 'ARS', 'USD']):
            c.execute(text('UPDATE presupuestos SET monto=:amount,moneda=:currency WHERE proveedor_id=:id'),
                      {'id': user.perfil_id, 'amount': amount, 'currency': currency})
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(case.db, 'before_cursor_execute', capture)
    try:
        view = case.selection.get(case.claim, case.actor)
    finally:
        event.remove(case.db, 'before_cursor_execute', capture)
    assert [(q['moneda'], q['monto']) for q in view['items']] == [('ARS', '20.00'), ('ARS', '100.00'), ('USD', '1.00')]
    assert all(q['especialidades'] and q['zonas'] for q in view['items'])
    assert len(statements) <= 16  # Constante: nunca tres consultas más por proveedor.
    items = case.portal.for_claim(case.claim, case.actor)['items']
    assert [q['presupuesto']['monto'] for q in items] == ['20.00', '100.00', '1.00']


def test_migration_enforces_money_snapshot_and_denies_browser_roles(selection_case):
    case = selection_case
    quoted(case)
    case.selection.choose(case.claim, case.actor, selection(case))
    with pytest.raises(IntegrityError):
        with case.db.begin() as c:
            c.execute(text('UPDATE reclamo_selecciones_presupuesto SET monto=0'))
    with case.db.connect() as c:
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='reclamo_selecciones_presupuesto'::regclass")).scalar_one()
        assert c.execute(text("SELECT count(*) FROM pg_policies WHERE tablename='reclamo_selecciones_presupuesto'")).scalar_one() == 0
        for role in ('anon', 'authenticated'):
            for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                assert not c.execute(text("SELECT has_table_privilege(:role,'reclamo_selecciones_presupuesto',:privilege)"),
                                     {'role': role, 'privilege': privilege}).scalar_one()


def test_chosen_provider_name_is_preserved_after_profile_edits(selection_case):
    case = selection_case
    quoted(case)
    first = case.selection.choose(case.claim, case.actor, selection(case))
    with case.db.begin() as c:
        c.execute(text("UPDATE proveedores SET nombre_razon_social='Nuevo nombre sintético'"))
    assert case.selection.get(case.claim, case.actor)['decision']['proveedor_nombre'] == first['proveedor_nombre']


def test_selected_provider_can_see_private_notice_without_hu33(selection_case):
    case = selection_case
    users = quoted(case, count=2)
    payload = selection(case)
    result = case.selection.choose(case.claim, case.actor, payload)
    views = [case.portal.get_own(request(case, user)['id'], user) for user in users]
    assert sum(v['seleccionado'] for v in views) == 1
    selected = next(v for v in views if v['seleccionado'])
    assert selected['presupuesto']['id'] == result['presupuesto_id']
    assert not any('items' in v or 'proveedor_nombre' in v for v in views)


def test_email_retry_does_not_repeat_selection_or_contact_competitors(selection_case):
    case = selection_case
    quoted(case, count=2)
    saved = case.selection.choose(case.claim, case.actor, selection(case))
    notice_id = scalar(case, "SELECT id FROM notificaciones WHERE clave_idempotencia LIKE 'hu20:%'")
    class Sender:
        def __init__(self): self.messages = []
        def send(self, **message):
            self.messages.append(message)
            if len(self.messages) == 1: raise ClaimEmailDeliveryError('Fallo SMTP simulado')
    sender = Sender()
    service = ClaimNotificationService(case.claims, sender)
    assert not service.deliver(notice_id)
    with case.db.begin() as c:
        c.execute(text('UPDATE notificaciones SET proximo_intento_en=clock_timestamp() WHERE id=:id'), {'id': notice_id})
    assert service.deliver(notice_id)
    assert not service.deliver(notice_id)
    assert sender.messages[0] == sender.messages[1]
    email = scalar(case, 'SELECT email FROM proveedores WHERE id=:id', id=saved['proveedor_id'])
    assert sender.messages[0]['recipient'] == email
    assert scalar(case, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 1


@pytest.mark.parametrize('change', ['inactive', 'email', 'state'])
def test_obsolete_selected_notice_is_never_delivered(selection_case, change):
    case = selection_case
    quoted(case)
    case.selection.choose(case.claim, case.actor, selection(case))
    notice_id = scalar(case, "SELECT id FROM notificaciones WHERE clave_idempotencia LIKE 'hu20:%'")
    context = case.claims.claim_notification(notice_id)
    assert context is not None
    with case.db.begin() as c:
        if change == 'inactive': c.execute(text('UPDATE proveedores SET activo=false'))
        elif change == 'email':
            c.execute(text("UPDATE proveedores SET email='new-contact@example.com'"))
            c.execute(text("UPDATE usuarios SET email='new-contact@example.com' WHERE rol='proveedor'"))
        else: c.execute(text("UPDATE reclamos SET estado='Resuelto'"))
    assert not case.claims.prepare_notification_delivery(context)
    assert scalar(case, 'SELECT estado_envio FROM notificaciones WHERE id=:id', id=notice_id) == 'fallido'


def test_authenticated_http_flow_uses_real_database_and_replays(selection_case, monkeypatch):
    from app.api.auth import get_current_user
    from app.api.quote_selections import get_quote_selections
    from app.main import app
    case = selection_case
    quoted(case)
    monkeypatch.setenv('AARI_QUOTE_PORTAL_ENABLED', 'true')
    app.dependency_overrides[get_current_user] = lambda: case.actor
    app.dependency_overrides[get_quote_selections] = lambda: case.selection
    path = f'/reclamos/{case.claim}/seleccion-presupuesto'
    try:
        with TestClient(app) as http:
            view = http.get(path)
            assert view.status_code == 200 and view.headers['cache-control'] == 'no-store'
            payload = {'request_id': str(uuid4()), 'ronda_id': view.json()['ronda_id'],
                       'expected_updated_at': view.json()['updated_at'], 'modalidad': 'fidelizado',
                       'presupuesto_id': view.json()['items'][0]['id']}
            first = http.post(path, json=payload)
            assert first.status_code == 200
            assert http.post(path, json=payload).json()['repetida']
            assert http.get(path).json()['decision']['id'] == first.json()['id']
            assert not http.get(path).json()['puede_elegir']
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_quote_selections, None)


@pytest.mark.parametrize('expense', ['ordinario', 'extraordinario'])
def test_alternative_hu18_closes_round_only_after_contact_confirmation(selection_case, expense):
    from app.db.external_providers import SqlAlchemyExternalProvidersRepository
    from app.schemas.external_providers import ExternalProviderRequest
    case = selection_case
    with case.db.connect() as c:
        cursor = c.connection.cursor()
        cursor.execute((MIGRATIONS/'20261029235000_hu18_proveedor_externo.sql').read_text(encoding='utf-8'))
        c.connection.commit()
        cursor.close()
    users = quoted(case, expense)
    view = case.selection.get(case.claim, case.actor)
    assert view['puede_cargar_propio']
    assert scalar(case, 'SELECT cerrada_en FROM aari_rondas_presupuesto') is None
    external = SqlAlchemyExternalProvidersRepository(sessionmaker(bind=case.db))
    detail = external.get(case.claim, case.actor)
    assert detail.puede_registrar
    data = ExternalProviderRequest(request_id=uuid4(), eleccion_id=detail.eleccion_id,
        expected_updated_at=detail.updated_at, nombre='Persona Sintetica', telefono='15555550100')
    external.register(case.claim, case.actor, data)
    assert scalar(case, 'SELECT estado FROM reclamos') == 'Derivado a proveedor externo'
    assert scalar(case, 'SELECT estado FROM aari_rondas_presupuesto') == 'cancelada'
    assert scalar(case, 'SELECT count(*) FROM reclamo_selecciones_presupuesto') == 0
    assert not case.selection.get(case.claim, case.actor)['puede_elegir']
    assert not case.selection.get(case.claim, case.actor)['puede_cargar_propio']
    assert not case.portal.get_own(request(case, users[0])['id'], users[0])['puede_responder']
