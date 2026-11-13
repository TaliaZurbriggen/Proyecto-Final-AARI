"""HU35: plantillas y servicios reales con Gmail/SMTP simulados."""

import base64
import json
from email import message_from_bytes, policy
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.services import email_transport as mail
from app.services.access_service import AccessInvitationService, ConfiguredWelcomeEmailSender
from app.services.claim_notifications import ClaimNotificationContext, ClaimNotificationService, ConfiguredClaimEmailSender
from app.services.provider_access_service import ConfiguredProviderInvitationSender, InvitationDelivery


def test_all_adapters_preserve_templates_and_use_gmail_only(monkeypatch):
    messages, requests = [], []
    def handler(request):
        requests.append(str(request.url))
        if str(request.url) == mail.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "fake", "scope": mail.SEND_SCOPE,
                                           "token_type": "Bearer", "expires_in": 3600})
        messages.append(message_from_bytes(base64.urlsafe_b64decode(json.loads(request.content)["raw"]), policy=policy.default))
        return httpx.Response(200, json={"id": "synthetic"})
    transport = mail.GmailApiEmailTransport(
        mail.GmailSettings("sender@example.com", "fake-client", "fake-secret", "fake-refresh"),
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(mail, "get_email_transport", lambda: transport)
    monkeypatch.setattr(mail.smtplib, "SMTP", lambda *a, **k: pytest.fail("No debe abrir SMTP"))
    monkeypatch.setenv("APP_LOGIN_URL", "https://aari.example.com/login")
    ConfiguredWelcomeEmailSender().send(recipient="person@example.com", person_name="Persona sintética",
                                        temporary_password="fake-temporary-password")
    ConfiguredProviderInvitationSender().send(InvitationDelivery(
        "synthetic", "provider@example.com", "Servicio sintético", "fake-invitation-token"))
    ConfiguredClaimEmailSender().send(recipient="person@example.com", claim_number=123,
                                      subject="AARI - Reclamo #000123", message="Presupuesto y coordinación sintéticos.")
    assert requests.count(mail.TOKEN_URL) == 1 and requests.count(mail.SEND_URL) == 3
    assert [str(message["To"]) for message in messages] == ["person@example.com", "provider@example.com", "person@example.com"]
    assert "fake-temporary-password" in messages[0].get_content()
    assert "https://aari.example.com/login" in messages[0].get_content()
    assert "/activar-proveedor#token=fake-invitation-token" in messages[1].get_content()
    assert "Contraseña temporal" not in messages[1].get_content()
    assert messages[2].get_content().strip() == "Presupuesto y coordinación sintéticos."


def failing_transport(monkeypatch, *, retryable=False, uncertain=False):
    def fail(**kwargs):
        raise mail.EmailDeliveryError("Error de correo sintético seguro.", retryable=retryable, uncertain=uncertain)
    monkeypatch.setattr(mail, "get_email_transport", lambda: SimpleNamespace(send=fail))


def test_welcome_failure_keeps_created_account_and_safe_result(monkeypatch):
    failing_transport(monkeypatch)
    results = []
    repo = SimpleNamespace(mark_delivery_result=lambda user, **data: results.append(data))
    assert not AccessInvitationService(repo, ConfiguredWelcomeEmailSender()).deliver(
        user_id=uuid4(), recipient="person@example.com", person_name="Persona", temporary_password="fake-password")
    assert results == [{"sent": False, "safe_error": "Error de correo sintético seguro."}]


@pytest.mark.parametrize("retryable,uncertain", [(False, False), (False, True), (True, False)])
def test_outbox_honors_transport_retry_decision_without_exposing_message(monkeypatch, retryable, uncertain):
    failing_transport(monkeypatch, retryable=retryable, uncertain=uncertain)
    context = ClaimNotificationContext(uuid4(), "person@example.com", 123, "email", "Aviso", "Texto", 1)
    results, validations = [], []
    repo = SimpleNamespace(claim_notification=lambda _: context,
        prepare_notification_delivery=lambda _: validations.append(True) or True,
        mark_notification_result=lambda _, **data: results.append(data))
    assert not ClaimNotificationService(repo, ConfiguredClaimEmailSender()).deliver(context.id)
    assert validations == [True]
    expected = {"attempt_number": 1, "sent": False, "safe_error": "Error de correo sintético seguro."}
    if not retryable:
        expected["retryable"] = False
    assert results == [expected]


def test_api_factories_use_configured_senders_without_network(monkeypatch):
    from app.api import inquilinos, operadores, propietarios, reclamos
    from app.services.access_service import SmtpWelcomeEmailSender
    from app.services.claim_notifications import SmtpClaimEmailSender
    assert SmtpWelcomeEmailSender is ConfiguredWelcomeEmailSender
    assert SmtpClaimEmailSender is ConfiguredClaimEmailSender
    assert isinstance(reclamos.get_claim_notification_service().senders["email"], ConfiguredClaimEmailSender)
    # No se envía ni se consulta la base al construir estas dependencias.
    assert isinstance(operadores.get_operadores_service().sender, ConfiguredWelcomeEmailSender)
    assert isinstance(propietarios.get_propietarios_service().access_service.sender, ConfiguredWelcomeEmailSender)
    assert isinstance(inquilinos.get_inquilinos_service().access_service.sender, ConfiguredWelcomeEmailSender)
