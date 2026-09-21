"""Garantías del reclamo atómico de la bandeja de notificaciones."""

import inspect

from app.db.reclamos import SqlAlchemyClaimsRepository
from app.services.claim_notifications import notification_lease_seconds


SOURCE = inspect.getsource(SqlAlchemyClaimsRepository._claim_notifications).lower()
RESULT_SOURCE = inspect.getsource(
    SqlAlchemyClaimsRepository.mark_notification_result
).lower()
FOLLOWUP_SOURCE = inspect.getsource(
    SqlAlchemyClaimsRepository.enqueue_due_responsible_followups
).lower()


def test_claims_due_notifications_without_blocking_other_workers() -> None:
    assert "for update skip locked" in SOURCE
    assert "set estado_envio = 'procesando'" in SOURCE
    assert "make_interval(secs => :lease_seconds)" in SOURCE


def test_closes_an_interrupted_last_attempt_instead_of_leaving_it_processing() -> None:
    assert "set estado_envio = 'fallido'" in SOURCE
    assert "intentos >= 3" in SOURCE
    assert "bloqueado_hasta <= current_timestamp" in SOURCE


def test_only_the_worker_that_claimed_an_attempt_can_store_its_result() -> None:
    assert "and intentos = :attempt_number" in RESULT_SOURCE


def test_notification_lease_is_configurable_and_bounded(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_LEASE_SECONDS", "180")
    assert notification_lease_seconds() == 180

    monkeypatch.setenv("NOTIFICATION_LEASE_SECONDS", "invalid")
    assert notification_lease_seconds() == 120

    monkeypatch.setenv("NOTIFICATION_LEASE_SECONDS", "5")
    assert notification_lease_seconds() == 30


def test_followups_are_claimed_without_blocking_and_are_idempotent() -> None:
    assert FOLLOWUP_SOURCE.count("for update of rr skip locked") == 2
    assert "on conflict (clave_idempotencia)" in FOLLOWUP_SOURCE
    assert "responsable_recordatorio" in FOLLOWUP_SOURCE
    assert "responsable_vencido" in FOLLOWUP_SOURCE


def test_overdue_flow_changes_state_before_notifying_an_operator() -> None:
    assert "pendiente de respuesta - vencido" in FOLLOWUP_SOURCE
    assert "_operator_recipient" in FOLLOWUP_SOURCE
    assert "set_config('app.origen_reclamo', 'sistema', true)" in FOLLOWUP_SOURCE
