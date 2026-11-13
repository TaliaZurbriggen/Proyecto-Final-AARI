"""HU35: resultados terminales y transitorios en PostgreSQL dedicado local."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from sqlalchemy import event, text

from app.services import email_transport as mail
from app.services.claim_notifications import ClaimEmailDeliveryError, ClaimNotificationService, ConfiguredClaimEmailSender
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


@pytest.mark.parametrize("kind", ["expired_grant", "uncertain_send"])
def test_terminal_gmail_result_after_lease_expiry_stops_current_attempt(claim_case, monkeypatch, kind):
    db, repo, claim_id = claim_case
    notice = repo.persist_classification(claim_id, classification("expensa")).notification_id
    calls, now = [], [0.0]

    def expire_reservation():
        with db.begin() as connection:
            connection.execute(text("UPDATE notificaciones SET bloqueado_hasta=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": notice})

    def handler(request):
        calls.append(str(request.url))
        if str(request.url) == mail.TOKEN_URL:
            if kind == "expired_grant":
                expire_reservation()
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "fake", "token_type": "Bearer",
                                            "scope": mail.SEND_SCOPE, "expires_in": 3600})
        assert str(request.url) == mail.SEND_URL
        expire_reservation()
        now[0] = 31.0  # El POST devuelve control después del presupuesto de 20 s.
        return httpx.Response(200, json={"id": "synthetic-accepted"})

    transport = mail.GmailApiEmailTransport(
        mail.GmailSettings("sender@example.com", "fake-client", "fake-secret", "fake-refresh"),
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: now[0])
    monkeypatch.setattr(mail, "get_email_transport", lambda: transport)
    monkeypatch.setattr(mail.smtplib, "SMTP", lambda *a, **k: pytest.fail("No debe abrir SMTP"))
    service = ClaimNotificationService(repo, ConfiguredClaimEmailSender())
    assert not service.deliver(notice)
    with db.connect() as connection:
        row = connection.execute(text("SELECT estado_envio,intentos,ultimo_error,proximo_intento_en,bloqueado_hasta FROM notificaciones WHERE id=:id"), {"id": notice}).mappings().one()
        assert row["estado_envio"] == "fallido" and row["intentos"] == 1
        assert row["proximo_intento_en"] is None and row["bloqueado_hasta"] is None
        assert "fake" not in row["ultimo_error"]
        assert ("Volvé a autorizar" if kind == "expired_grant" else "revisar antes de reenviar") in row["ultimo_error"]
        assert connection.execute(text("SELECT estado FROM reclamos WHERE id=:id"), {"id": claim_id}).scalar_one() == "Pendiente de respuesta del responsable"
    assert not service.deliver(notice) and repo.claim_due_notifications(limit=5) == []
    assert calls == ([mail.TOKEN_URL] if kind == "expired_grant" else [mail.TOKEN_URL, mail.SEND_URL])


@pytest.mark.parametrize("reclaimed", [False, True])
def test_terminal_result_waiting_for_claim_lock_only_updates_current_attempt(claim_case, reclaimed):
    db, repo, claim_id = claim_case
    notice = repo.persist_classification(claim_id, classification("expensa")).notification_id
    first = repo.claim_notification(notice)
    waiting = Event()

    def reached_lock(conn, cursor, statement, parameters, execution_context, executemany):
        if "SELECT id FROM reclamos" in statement and "FOR UPDATE" in statement:
            waiting.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with db.begin() as blocking:
                blocking.execute(text("SELECT id FROM reclamos WHERE id=:id FOR UPDATE"), {"id": claim_id})
                event.listen(db, "before_cursor_execute", reached_lock)
                result = pool.submit(repo.mark_notification_result, notice, attempt_number=first.attempt_number,
                                     sent=False, retryable=False, safe_error="Resultado terminal sintético.")
                assert waiting.wait(timeout=5)
                with db.begin() as connection:
                    connection.execute(text("UPDATE notificaciones SET bloqueado_hasta=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": notice})
                if reclaimed:
                    second = repo.claim_notification(notice)
                    assert second.attempt_number == first.attempt_number + 1
            assert result.result(timeout=5) is (not reclaimed)
        finally:
            event.remove(db, "before_cursor_execute", reached_lock)
    with db.connect() as connection:
        row = connection.execute(text("SELECT estado_envio,intentos,ultimo_error FROM notificaciones WHERE id=:id"), {"id": notice}).mappings().one()
        assert row["estado_envio"] == ("procesando" if reclaimed else "fallido")
        assert row["intentos"] == (2 if reclaimed else 1)
        assert row["ultimo_error"] == (None if reclaimed else "Resultado terminal sintético.")


@pytest.mark.parametrize("status", ["fallido", "enviado"])
def test_late_terminal_result_never_overwrites_a_finished_or_cancelled_notice(claim_case, status):
    db, repo, claim_id = claim_case
    notice = repo.persist_classification(claim_id, classification("expensa")).notification_id
    first = repo.claim_notification(notice)
    with db.begin() as connection:
        connection.execute(text("UPDATE notificaciones SET estado_envio=:state,ultimo_error='Resultado previo.',bloqueado_hasta=NULL,proximo_intento_en=NULL WHERE id=:id"), {"state": status, "id": notice})
    assert not repo.mark_notification_result(notice, attempt_number=first.attempt_number,
                                             sent=False, retryable=False, safe_error="Resultado tardío.")
    with db.connect() as connection:
        row = connection.execute(text("SELECT estado_envio,ultimo_error FROM notificaciones WHERE id=:id"), {"id": notice}).mappings().one()
        assert dict(row) == {"estado_envio": status, "ultimo_error": "Resultado previo."}


@pytest.mark.parametrize("failure", ["quit", "send"])
def test_smtp_cleanup_and_uncertainty_do_not_requeue_expense_report(claim_case, monkeypatch, failure):
    db, repo, claim_id = claim_case
    notice = repo.persist_classification(claim_id, classification("expensa")).notification_id
    events = []

    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args):
            try: self.quit()
            finally: self.close()
        def starttls(self): pass
        def send_message(self, message):
            events.append("send")
            if failure == "send":
                raise mail.smtplib.SMTPServerDisconnected("private-lost-response")
        def quit(self):
            events.append("quit")
            raise mail.smtplib.SMTPResponseException(421, b"private-close")
        def close(self): events.append("close")

    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "")
    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    service = ClaimNotificationService(repo, ConfiguredClaimEmailSender())
    assert service.deliver(notice) is (failure == "quit")
    assert not service.deliver(notice)
    assert events == ["send", "quit", "close"]
    with db.connect() as connection:
        row = connection.execute(text("SELECT estado_envio,intentos,proximo_intento_en FROM notificaciones WHERE id=:id"), {"id": notice}).mappings().one()
        assert dict(row) == {"estado_envio": "enviado" if failure == "quit" else "fallido",
                             "intentos": 1, "proximo_intento_en": None}
