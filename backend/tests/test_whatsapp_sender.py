"""Mock HTTP de Meta. Ninguna prueba puede abrir una conexión externa."""

from dataclasses import replace
import json

import httpx
import pytest

from app.core.whatsapp import WhatsAppSettings
from app.services.whatsapp_sender import MetaWhatsAppSender, WhatsAppSendError
from tests.whatsapp_helpers import SETTINGS


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Una prueba intentó usar red real.")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


def sender(handler=None, settings=SETTINGS):
    calls = []
    def record(request):
        calls.append(request)
        return handler(request) if handler else httpx.Response(200, json={"messages": [{"id": "wamid.synthetic.accepted"}]})
    return MetaWhatsAppSender(settings, transport=httpx.MockTransport(record)), calls


def send(client, **kwargs):
    return client.send_template(recipient="15555550100", template_name="synthetic_budget_request",
                                parameters=("Problema sintético",), **kwargs)


def test_config_is_off_by_default_and_secrets_are_not_printable(monkeypatch):
    for key in ("WHATSAPP_WEBHOOK_ENABLED", "WHATSAPP_OUTBOUND_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    settings = WhatsAppSettings.from_env()
    assert not settings.outbound_enabled and not settings.webhook_enabled
    for secret in (SETTINGS.app_secret, SETTINGS.access_token, SETTINGS.verify_token, SETTINGS.test_recipients[0]):
        assert secret not in repr(SETTINGS)


def test_disabled_sender_makes_zero_requests():
    client, calls = sender(settings=replace(SETTINGS, outbound_enabled=False))
    with pytest.raises(WhatsAppSendError) as raised:
        send(client)
    assert raised.value.outcome == "not_sent" and calls == []


def test_mock_send_acceptance_is_not_delivery_and_uses_bearer_header():
    client, calls = sender()
    receipt = send(client)
    assert receipt.outcome == "accepted" and receipt.message_id == "wamid.synthetic.accepted"
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == f"https://graph.facebook.com/v26.0/{SETTINGS.phone_number_id}/messages"
    assert "access_token" not in str(request.url)
    assert request.headers["Authorization"] == f"Bearer {SETTINGS.access_token}"
    data = json.loads(request.content)
    assert data["to"] == "15555550100" and data["type"] == "template"
    assert data["template"]["components"][0]["parameters"][0]["text"] == "Problema sintético"


@pytest.mark.parametrize("changes", [
    {"access_token": ""}, {"phone_number_id": "../outside"}, {"waba_id": ""},
    {"api_version": "https://invalid.example"}, {"test_recipients": ()},
    {"test_recipients": ("invalid",)}, {"test_recipients": tuple(f"1555555010{i}" for i in range(6))},
    {"test_recipients": ("15555550101",)},
])
def test_invalid_config_or_non_authorized_recipient_never_sends(changes):
    client, calls = sender(settings=replace(SETTINGS, **changes))
    with pytest.raises(WhatsAppSendError):
        send(client)
    assert calls == []


@pytest.mark.parametrize("kwargs", [{"template_name": "Invalid Name"}, {"language": "../es"},
                                     {"parameters": ("",)}, {"parameters": ("x" * 4097,)},
                                     {"template_name": 1}, {"language": ["es_AR"]},
                                     {"parameters": ("bad\x00text",)}, {"parameters": ("\ud800",)}])
def test_invalid_template_never_sends(kwargs):
    client, calls = sender()
    values = {"recipient": "15555550100", "template_name": "synthetic_request", **kwargs}
    with pytest.raises(WhatsAppSendError):
        client.send_template(**values)
    assert calls == []


@pytest.mark.parametrize("status,outcome", [(400, "rejected"), (401, "rejected"), (429, "rejected"),
                                           (302, "unknown"), (500, "unknown"), (503, "unknown")])
def test_failures_do_not_retry_redirect_or_leak_meta_errors(status, outcome):
    client, calls = sender(lambda _: httpx.Response(status, headers={"Location": "https://invalid.example"},
        json={"error": {"message": SETTINGS.access_token}}))
    with pytest.raises(WhatsAppSendError) as raised:
        send(client)
    assert raised.value.outcome == outcome and not raised.value.retryable
    assert SETTINGS.access_token not in str(raised.value) and len(calls) == 1


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_failure_is_uncertain_not_automatically_retried(error):
    def failed(request):
        raise error("synthetic private transport failure", request=request)
    client, calls = sender(failed)
    with pytest.raises(WhatsAppSendError) as raised:
        send(client)
    assert raised.value.outcome == "unknown" and not raised.value.retryable
    assert "private transport" not in str(raised.value) and len(calls) == 1


@pytest.mark.parametrize("result", [{}, {"messages": []}, {"messages": [{"id": ""}]}, [], None])
def test_missing_receipt_is_not_reported_as_success(result):
    client, calls = sender(lambda _: httpx.Response(200, json=result))
    with pytest.raises(WhatsAppSendError) as raised:
        send(client)
    assert raised.value.outcome == "unknown" and len(calls) == 1


def test_international_prefix_is_normalized_without_using_a_test_slot():
    client, calls = sender(settings=replace(SETTINGS, test_recipients=("+15555550100",)))
    client.send_template(recipient="+15555550100", template_name="synthetic_request")
    assert json.loads(calls[0].content)["to"] == "15555550100"


def test_env_settings_are_not_enabled_by_arbitrary_truthy_strings(monkeypatch):
    monkeypatch.setenv("WHATSAPP_OUTBOUND_ENABLED", "false-but-not-empty")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_ENABLED", "no")
    assert not WhatsAppSettings.from_env().outbound_enabled
    assert not WhatsAppSettings.from_env().webhook_enabled
