"""HU36 sobre una visita real de HU23 y PostgreSQL descartable."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.api.visits import get_visits, participant, router
from app.db.visits import validate_visit_notice
from app.schemas.conversations import ConversationMessageRequest
from app.schemas.visits import VisitAbsenceRequest, VisitConfirmationRequest, VisitRescheduleDecision, VisitRescheduleRequest
from app.services.visits import VisitError
from tests.test_visits_postgres import (
    MIGRATIONS, action, claim_case, choice_base, local_engine, portal_case, publish, scalar, visit_case,
)


pytestmark = pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'), reason='PostgreSQL local dedicado.')


@pytest.fixture
def followup_case(visit_case):
    case = visit_case
    availability = publish(case)
    case.date = availability.opciones[0].desde
    confirmation = VisitConfirmationRequest(**action(case, case.provider), fecha=case.date)
    case.visits.act(case.claim, case.provider, 'confirmar', confirmation)
    assert case.visits.get(case.claim, case.tenant)['seguimiento'] is None
    with case.db.connect() as conn:
        with conn.connection.cursor() as cursor:
            cursor.execute((MIGRATIONS / '20261111120000_hu36_reprogramacion_visitas.sql').read_text(encoding='utf-8'))
        conn.commit()
    return case


def proposal(case, date, user=None):
    user = user or case.tenant
    payload = VisitRescheduleRequest(**action(case, user), fecha=date, motivo='Cambio de disponibilidad')
    result = case.visits.act(case.claim, user, 'reprogramar', payload)
    return payload, result['seguimiento']['propuesta_pendiente']


def decision(case, pending, user, value='aceptar'):
    return VisitRescheduleDecision(**action(case, user), propuesta_id=pending['id'], decision=value)


@pytest.mark.parametrize('visit_case', ['ordinario', 'extraordinario'], indirect=True)
def test_accept_through_http_preserves_participants_and_audits(followup_case):
    case = followup_case
    date = case.date + timedelta(days=3)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_visits] = lambda: case.visits
    app.dependency_overrides[participant] = lambda: case.tenant
    http = TestClient(app)
    url = f'/reclamos/{case.claim}/visita'
    proposal_payload = VisitRescheduleRequest(**action(case), fecha=date, motivo='Cambio de disponibilidad')
    sent = http.post(f'{url}/reprogramar', json=proposal_payload.model_dump(mode='json'))
    assert sent.status_code == 200, sent.text
    assert sent.headers['cache-control'] == 'no-store'
    assert scalar(case, 'SELECT fecha_visita FROM reclamos') == case.date
    assert sent.json()['seguimiento']['decisiones'] == ['retirar']
    pending = case.visits.get(case.claim, case.provider)['seguimiento']['propuesta_pendiente']
    assert pending['fecha_anterior'] == case.date
    if case.actor.rol == 'propietario':
        assert case.visits.get(case.claim, case.actor)['seguimiento'] is None
    with pytest.raises(VisitError):
        case.visits.act(case.claim, case.tenant, 'decidir-reprogramacion', decision(case, pending, case.tenant))

    thread = case.visits.get(case.claim, case.tenant)['hilo_id']
    case.visits.thread_send(thread, case.provider, ConversationMessageRequest(request_id=uuid4(), texto='Me queda bien.'))
    assert scalar(case, 'SELECT fecha_visita FROM reclamos') == case.date
    app.dependency_overrides[participant] = lambda: case.provider
    payload = decision(case, pending, case.provider).model_dump(mode='json')
    accepted = http.post(f'{url}/decidir-reprogramacion', json=payload)
    assert accepted.status_code == 200, accepted.text
    assert http.post(f'{url}/decidir-reprogramacion', json=payload).json()['repetida']
    history = accepted.json()['seguimiento']['reprogramaciones']
    assert len(history) == 1 and history[0]['estado'] == 'aceptada'
    assert history[0]['decision_rol'] == 'proveedor'
    assert scalar(case, 'SELECT fecha_visita FROM reclamos') == date
    assert scalar(case, 'SELECT estado FROM reclamos') == 'Visita programada'
    assert scalar(case, 'SELECT count(*) FROM visitas') == 1
    assert scalar(case, 'SELECT version_horario FROM aari_visita_coordinaciones') == 1


def test_one_proposal_then_rejection_withdrawal_and_expiry(followup_case, monkeypatch):
    case = followup_case
    _, first = proposal(case, case.date + timedelta(days=1))
    assert first['vence_en'] == first['creada_en'] + timedelta(hours=24)
    with pytest.raises(VisitError):
        proposal(case, case.date + timedelta(days=2), case.provider)
    case.visits.act(case.claim, case.provider, 'decidir-reprogramacion', decision(case, first, case.provider, 'rechazar'))
    _, second = proposal(case, case.date + timedelta(days=2), case.provider)
    case.visits.act(case.claim, case.provider, 'decidir-reprogramacion', decision(case, second, case.provider, 'retirar'))
    now = case.date - timedelta(hours=2)
    monkeypatch.setattr(case.visits, '_now', lambda _: now)
    _, last = proposal(case, case.date - timedelta(hours=1))
    assert last['vence_en'] == last['fecha_propuesta']
    now = last['vence_en']
    view = case.visits.get(case.claim, case.provider)
    assert view['acciones'] == ['reprogramar']
    assert {item['estado'] for item in view['seguimiento']['reprogramaciones']} == {'rechazada', 'retirada', 'vencida'}
    assert scalar(case, 'SELECT estado FROM aari_visita_reprogramaciones WHERE id=:id', id=last['id']) == 'pendiente'
    with pytest.raises(VisitError):
        case.visits.act(case.claim, case.provider, 'decidir-reprogramacion', decision(case, last, case.provider))
    _, next_proposal = proposal(case, case.date + timedelta(days=1))
    assert next_proposal['vence_en'] == case.date
    assert scalar(case, 'SELECT estado FROM aari_visita_reprogramaciones WHERE id=:id', id=last['id']) == 'vencida'
    assert scalar(case, 'SELECT fecha_visita FROM reclamos') == case.date


def test_two_reports_after_schedule_keep_both_versions(followup_case, monkeypatch):
    case = followup_case
    tenant_report = VisitAbsenceRequest(**action(case), tipo='contraparte_ausente', observaciones='Esperé en la unidad.')
    with pytest.raises(VisitError):
        case.visits.act(case.claim, case.tenant, 'informar-ausencia', tenant_report)
    monkeypatch.setattr(case.visits, '_now', lambda _: case.date)
    case.visits.act(case.claim, case.tenant, 'informar-ausencia', tenant_report)
    assert case.visits.act(case.claim, case.tenant, 'informar-ausencia', tenant_report)['repetida']
    other = VisitAbsenceRequest(**action(case, case.provider), tipo='no_realizada', observaciones='No pude acceder.')
    result = case.visits.act(case.claim, case.provider, 'informar-ausencia', other)
    assert {entry['autor_rol'] for entry in result['seguimiento']['ausencias']} == {'inquilino', 'proveedor'}
    assert result['acciones'] == []
    assert scalar(case, 'SELECT estado FROM visitas') == 'confirmada'
    assert scalar(case, 'SELECT estado FROM reclamos') == 'Visita programada'
    assert scalar(case, 'SELECT proveedor_seleccionado_id FROM reclamos') == case.provider.perfil_id
    with pytest.raises(VisitError):
        case.visits.act(case.claim, case.tenant, 'informar-ausencia', tenant_report.model_copy(update=action(case)))
    with pytest.raises(VisitError) as error:
        case.visits.get(case.claim, case.provider.model_copy(update={'perfil_id': uuid4()}))
    assert error.value.status == 404


def test_previous_queued_reminders_are_obsolete_and_new_schedule_gets_its_own(followup_case, monkeypatch):
    case = followup_case
    now = case.date - timedelta(hours=1)
    monkeypatch.setattr(case.visits, '_now', lambda _: now)
    case.visits.follow_up(case.claim)
    assert scalar(case, "SELECT count(*) FROM aari_visita_avisos WHERE evento IN ('recordatorio_24','recordatorio_2')") == 4
    old = scalar(case, "SELECT notificacion_id FROM aari_visita_avisos WHERE evento='recordatorio_2' LIMIT 1")
    new_date = case.date + timedelta(days=3)
    _, pending = proposal(case, new_date)
    case.visits.act(case.claim, case.provider, 'decidir-reprogramacion', decision(case, pending, case.provider))
    assert scalar(case, 'SELECT estado_envio FROM notificaciones WHERE id=:id', id=old) == 'fallido'
    now = new_date - timedelta(hours=1)
    case.visits.follow_up(case.claim)
    case.visits.follow_up(case.claim)
    assert scalar(case, "SELECT count(*) FROM aari_visita_avisos WHERE evento IN ('recordatorio_24:horario:1','recordatorio_2:horario:1')") == 4
    new = scalar(case, "SELECT notificacion_id FROM aari_visita_avisos WHERE evento='recordatorio_2:horario:1' LIMIT 1")
    with case.db.begin() as session:
        assert not validate_visit_notice(session, old)
        assert validate_visit_notice(session, new)


def test_concurrent_accept_and_reject_only_one_decision(followup_case):
    case = followup_case
    _, pending = proposal(case, case.date + timedelta(days=1))
    payloads = [decision(case, pending, case.provider, value) for value in ('aceptar', 'rechazar')]
    barrier = Barrier(2, timeout=10)

    def submit(payload):
        barrier.wait()
        try:
            result = case.visits.act(case.claim, case.provider, 'decidir-reprogramacion', payload)
        except VisitError as exc:
            return exc.status
        return result['seguimiento']['reprogramaciones'][0]['estado']

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, payloads))
    assert results.count(409) == 1
    status = scalar(case, 'SELECT estado FROM aari_visita_reprogramaciones')
    assert status in {'aceptada', 'rechazada'} and status in results
    expected = pending['fecha_propuesta'] if status == 'aceptada' else case.date
    assert scalar(case, 'SELECT fecha_visita FROM reclamos') == expected


def test_acceptance_rolls_back_if_notification_cannot_be_recorded(followup_case, monkeypatch):
    case = followup_case
    _, pending = proposal(case, case.date + timedelta(days=3))
    payload = decision(case, pending, case.provider)

    def fail(*_):
        raise RuntimeError('Fallo sintético de persistencia del aviso')

    with monkeypatch.context() as local:
        local.setattr(case.visits, '_notice', fail)
        with pytest.raises(RuntimeError, match='Fallo sintético'):
            case.visits.act(case.claim, case.provider, 'decidir-reprogramacion', payload)

    assert scalar(case, 'SELECT estado FROM aari_visita_reprogramaciones') == 'pendiente'
    assert scalar(case, 'SELECT version_horario FROM aari_visita_coordinaciones') == 0
    assert scalar(case, 'SELECT fecha_visita FROM reclamos') == case.date
    assert scalar(case, 'SELECT count(*) FROM aari_visita_acciones WHERE request_id=:key', key=payload.request_id) == 0
    case.visits.act(case.claim, case.provider, 'decidir-reprogramacion', payload)
    assert scalar(case, 'SELECT fecha_visita FROM reclamos') == pending['fecha_propuesta']
