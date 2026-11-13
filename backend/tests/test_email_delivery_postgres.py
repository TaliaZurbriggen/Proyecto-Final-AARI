"""HU35: resultados terminales y transitorios en PostgreSQL dedicado local."""

import os

import pytest
from sqlalchemy import text

from app.services.claim_notifications import ClaimEmailDeliveryError, ClaimNotificationService
from tests.test_responsible_actor_postgres import claim_case, classification, local_engine

pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Sólo PostgreSQL local dedicado.")


@pytest.mark.parametrize("reason", ["Autorización de correo vencida.", "Envío incierto; revisar antes de reenviar."])
def test_nonretryable_delivery_stops_after_one_real_attempt_without_losing_history(claim_case, reason):
    db, repo, claim_id = claim_case
    notice = repo.persist_classification(claim_id, classification("expensa")).notification_id
    calls = []
    class Sender:
        def send(self, **kwargs):
            calls.append(kwargs)
            raise ClaimEmailDeliveryError(reason, retryable=False)
    service = ClaimNotificationService(repo, Sender())
    assert not service.deliver(notice)
    assert not service.deliver(notice)
    with db.connect() as conn:
        row = conn.execute(text("SELECT estado_envio,intentos,ultimo_error,proximo_intento_en,bloqueado_hasta FROM notificaciones WHERE id=:id"), {"id": notice}).mappings().one()
        assert dict(row) == {"estado_envio": "fallido", "intentos": 1, "ultimo_error": reason,
                             "proximo_intento_en": None, "bloqueado_hasta": None}
        assert conn.execute(text("SELECT estado FROM reclamos WHERE id=:id"), {"id": claim_id}).scalar_one() == "Pendiente de respuesta del responsable"
    assert len(calls) == 1


def test_recoverable_rejection_retries_later_and_success_preserves_business_transition(claim_case):
    db, repo, claim_id = claim_case
    notice = repo.persist_classification(claim_id, classification("expensa")).notification_id
    calls = []
    class Sender:
        def send(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise ClaimEmailDeliveryError("Límite temporal de Google.", retryable=True)
    service = ClaimNotificationService(repo, Sender())
    assert not service.deliver(notice)
    assert not service.deliver(notice)  # Respeta los 60 segundos persistidos.
    with db.begin() as conn:
        row = conn.execute(text("SELECT estado_envio,intentos,proximo_intento_en IS NOT NULL AS retry FROM notificaciones WHERE id=:id"), {"id": notice}).mappings().one()
        assert dict(row) == {"estado_envio": "pendiente", "intentos": 1, "retry": True}
        conn.execute(text("UPDATE notificaciones SET proximo_intento_en=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": notice})
    assert service.deliver(notice)
    assert not service.deliver(notice)
    with db.connect() as conn:
        assert conn.execute(text("SELECT estado FROM reclamos WHERE id=:id"), {"id": claim_id}).scalar_one() == "Derivado a inmobiliaria (expensa)"
        assert conn.execute(text("SELECT intentos FROM notificaciones WHERE id=:id AND estado_envio='enviado'"), {"id": notice}).scalar_one() == 2
    assert len(calls) == 2


def test_late_terminal_error_cannot_cancel_a_newer_attempt(claim_case):
    db, repo, claim_id = claim_case
    notice = repo.persist_classification(claim_id, classification("expensa")).notification_id
    first = repo.claim_notification(notice)
    with db.begin() as conn:
        conn.execute(text("UPDATE notificaciones SET bloqueado_hasta=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": notice})
    second = repo.claim_notification(notice)
    assert second.attempt_number == first.attempt_number + 1
    assert not repo.mark_notification_result(notice, attempt_number=first.attempt_number,
                                             sent=False, safe_error="Resultado tardío.", retryable=False)
    assert repo.mark_notification_result(notice, attempt_number=second.attempt_number, sent=True)
