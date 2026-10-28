"""Contrato HTTP y seguridad sin Meta, LLM, Supabase ni correo."""

from copy import deepcopy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.whatsapp import get_whatsapp_inbox, get_whatsapp_settings
from app.core.whatsapp import WhatsAppSettings
from app.main import app
from app.services.whatsapp_webhook import MAX_WEBHOOK_BYTES, parse_events
from tests.whatsapp_helpers import SETTINGS, MemoryInbox, body, message, payload, signature


@pytest.fixture
def webhook():
    inbox = MemoryInbox()
    app.dependency_overrides[get_whatsapp_settings] = lambda: SETTINGS
    app.dependency_overrides[get_whatsapp_inbox] = lambda: inbox
    with TestClient(app) as client:
        yield client, inbox
    app.dependency_overrides.pop(get_whatsapp_settings, None)
    app.dependency_overrides.pop(get_whatsapp_inbox, None)


def post(client, raw=None, **kwargs):
    raw = body() if raw is None else raw
    return client.post("/webhooks/whatsapp", content=raw,
                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature(raw),
                                **kwargs.pop("headers", {})}, **kwargs)


def test_get_challenge_returns_plain_text_without_json_quotes(webhook):
    client, inbox = webhook
    response = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe",
                          "hub.verify_token": SETTINGS.verify_token, "hub.challenge": "001158201444"})
    assert response.status_code == 200 and response.text == "001158201444"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store" and inbox.calls == 0


@pytest.mark.parametrize("query", [
    {}, {"hub.mode": "invalid"}, {"hub.verify_token": "incorrect"},
    {"hub.challenge": "<script>"}, {"hub.challenge": ""}, {"hub.challenge": "1" * 257},
])
def test_invalid_verification_fails_without_echoing_secrets(webhook, query):
    client, _ = webhook
    params = {"hub.mode": "subscribe", "hub.verify_token": SETTINGS.verify_token, "hub.challenge": "123"}
    if query:
        params.update(query)
    else:
        params = {}
    response = client.get("/webhooks/whatsapp", params=params)
    assert response.status_code == 403 and SETTINGS.verify_token not in response.text


def test_duplicate_verification_parameters_are_rejected(webhook):
    client, _ = webhook
    response = client.get("/webhooks/whatsapp", params=[("hub.mode", "subscribe"),
        ("hub.verify_token", SETTINGS.verify_token), ("hub.challenge", "1"), ("hub.challenge", "2")])
    assert response.status_code == 403


@pytest.mark.parametrize("method", ["get", "post"])
def test_routes_fail_closed_by_default(webhook, method):
    client, inbox = webhook
    app.dependency_overrides[get_whatsapp_settings] = WhatsAppSettings
    assert getattr(client, method)("/webhooks/whatsapp").status_code == 404
    assert inbox.calls == 0


@pytest.mark.parametrize("settings", [replace(SETTINGS, app_secret=""), replace(SETTINGS, phone_number_id=""),
                                      replace(SETTINGS, waba_id="https://invalid.example")])
def test_missing_receive_configuration_never_writes(webhook, settings):
    client, inbox = webhook
    app.dependency_overrides[get_whatsapp_settings] = lambda: settings
    assert post(client).status_code == 503 and inbox.calls == 0


def test_verification_can_be_prepared_without_a_phone_or_oauth_token(webhook):
    client, _ = webhook
    app.dependency_overrides[get_whatsapp_settings] = lambda: replace(SETTINGS, phone_number_id="", access_token="")
    response = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe",
        "hub.verify_token": SETTINGS.verify_token, "hub.challenge": "123"})
    assert response.status_code == 200


@pytest.mark.parametrize("header", ["", "sha256=" + "0" * 64, "sha1=" + "0" * 40, "sha256=invalid"])
def test_invalid_signature_rejected_before_parsing_or_writing(webhook, header):
    client, inbox = webhook
    response = post(client, b"not json", headers={"X-Hub-Signature-256": header})
    assert response.status_code == 403 and inbox.calls == 0


def test_signature_uses_original_bytes_and_detects_tampering(webhook):
    client, inbox = webhook
    raw = body()
    assert post(client, raw + b" ", headers={"X-Hub-Signature-256": signature(raw)}).status_code == 403
    assert post(client, raw).status_code == 200
    assert len(inbox.rows) == 1
    assert "contacts" not in next(iter(inbox.rows.values())).data


@pytest.mark.parametrize("raw", [b"not json", b"[]", b"null", b'{"object":NaN}',
                                b'{"object":1,"object":2}', b'\xff', b'[' * 1100])
def test_signed_but_malformed_input_is_not_acknowledged(webhook, raw):
    client, inbox = webhook
    assert post(client, raw).status_code == 400 and inbox.calls == 0


@pytest.mark.parametrize("field", ["waba", "phone"])
def test_rejects_other_assets_including_mixed_batches_atomically(webhook, field):
    client, inbox = webhook
    data = payload()
    other = deepcopy(data["entry"][0])
    if field == "waba":
        other["id"] = "99999"
    else:
        other["changes"][0]["value"]["metadata"]["phone_number_id"] = "99999"
    data["entry"].append(other)
    assert post(client, body(data)).status_code == 403 and inbox.calls == 0


def test_retries_and_changed_duplicate_content_do_not_overwrite_original(webhook):
    client, inbox = webhook
    assert post(client).status_code == 200
    changed = payload([message(text={"body": "Contenido distinto para el mismo ID."})])
    assert post(client).status_code == post(client, body(changed)).status_code == 200
    assert len(inbox.rows) == 1
    event = next(iter(inbox.rows.values()))
    assert event.data["text"].startswith("Presupuesto sintético")
    assert event.state == "pendiente"  # No crea ni acepta un presupuesto.


def test_statuses_are_not_quotes_and_keep_out_of_order_history(webhook):
    client, inbox = webhook
    statuses = [{"id": "wamid.outgoing", "status": status, "timestamp": str(1792440000 + index),
                 "recipient_id": "15555550100", "biz_opaque_callback_data": "synthetic-correlation"}
                for index, status in enumerate(("read", "sent", "delivered"))]
    data = body(payload([], statuses=statuses))
    assert post(client, data).status_code == post(client, data).status_code == 200
    assert len(inbox.rows) == 3
    assert {event.kind for event in inbox.rows.values()} == {"estado"}
    assert {event.event_type for event in inbox.rows.values()} == {"read", "sent", "delivered"}


def test_media_is_audited_without_fetching_its_url(webhook):
    client, inbox = webhook
    data = payload([message(type="image", image={"url": "https://invalid.example/private"})])
    assert post(client, body(data)).status_code == 200
    event = next(iter(inbox.rows.values()))
    assert event.state == "no_soportado" and "url" not in str(event.data)


@pytest.mark.parametrize("change", [
    {"timestamp": "-1"}, {"timestamp": True}, {"timestamp": "999999999999"}, {"from": "not-a-number"},
    {"text": {"body": "\x00"}}, {"text": {"body": "\ud800"}}, {"text": {"body": "x" * 4097}},
])
def test_bad_event_fields_fail_before_persistence(webhook, change):
    client, inbox = webhook
    import json
    raw = json.dumps(payload([message(**change)]), ensure_ascii=True).encode()
    assert post(client, raw).status_code == 400 and inbox.calls == 0


def test_storage_failure_returns_503_so_meta_can_retry(webhook):
    client, inbox = webhook
    def unavailable(_events):
        raise SQLAlchemyError("synthetic private DB failure")
    inbox.save_events = unavailable
    response = post(client)
    assert response.status_code == 503 and "private DB" not in response.text


def test_size_limit_is_enforced_without_trusting_content_length(webhook, monkeypatch):
    client, inbox = webhook
    monkeypatch.setattr("app.api.whatsapp.MAX_WEBHOOK_BYTES", 32)
    raw = body()
    assert post(client, raw, headers={"Content-Length": "1"}).status_code == 413
    assert inbox.calls == 0 and MAX_WEBHOOK_BYTES == 4 * 1024 * 1024


@pytest.mark.parametrize("headers", [{"Content-Type": "text/plain"}, {"Content-Encoding": "gzip"}])
def test_unsupported_encoding_fails_closed(webhook, headers):
    client, inbox = webhook
    assert post(client, headers=headers).status_code == 415 and inbox.calls == 0


def test_large_valid_batch_and_duplicate_ids(webhook):
    client, inbox = webhook
    raw = body(payload([message(f"wamid.synthetic.{index}") for index in range(1000)]))
    assert post(client, raw).status_code == 200 and len(inbox.rows) == 1000
    raw = body(payload([message(f"wamid.synthetic.{index}") for index in range(1001)]))
    assert post(client, raw).status_code == 400 and len(inbox.rows) == 1000


def test_unrelated_field_is_ignored_without_writes(webhook):
    client, inbox = webhook
    data = payload()
    data["entry"][0]["changes"][0] = {"field": "message_template_status_update", "value": {}}
    assert post(client, body(data)).status_code == 200 and inbox.rows == {}


def test_context_id_is_preserved_for_future_request_correlation():
    event = parse_events(body(payload([message(context={"id": "wamid.request"})])), SETTINGS)[0]
    assert event.data["context_message_id"] == "wamid.request"
