"""Datos sintéticos y dobles; nunca representa una entrega real de WhatsApp."""

import hashlib
import hmac
import json
from threading import Lock

from app.core.whatsapp import WhatsAppSettings
from app.schemas.whatsapp import WhatsAppIngestionResult


SETTINGS = WhatsAppSettings(
    webhook_enabled=True, outbound_enabled=True,
    verify_token="synthetic-verification-not-a-real-token",
    app_secret="synthetic-app-secret-not-for-production",
    access_token="synthetic-oauth-not-a-real-token",
    waba_id="100000000000001", phone_number_id="100000000000002",
    test_recipients=("15555550100",),
)


def message(message_id="wamid.synthetic", **changes):
    return {"id": message_id, "from": "15555550100", "timestamp": "1792440000",
            "type": "text", "text": {"body": "Presupuesto sintético: ARS 12500 por la reparación."}, **changes}


def payload(messages=None, *, statuses=None):
    value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": SETTINGS.phone_number_id},
             "contacts": [{"profile": {"name": "Nombre sintético que no debe almacenarse"}}]}
    value["messages"] = [message()] if messages is None else messages
    if statuses is not None:
        value["statuses"] = statuses
    return {"object": "whatsapp_business_account", "entry": [
        {"id": SETTINGS.waba_id, "changes": [{"field": "messages", "value": value}]},
    ]}


def body(data=None):
    return json.dumps(payload() if data is None else data, ensure_ascii=False).encode("utf-8")


def signature(raw, secret=SETTINGS.app_secret):
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


class MemoryInbox:
    """Sólo pruebas: PostgreSQL y su unicidad se prueban por separado."""

    def __init__(self):
        self.rows = {}
        self.calls = 0
        self.lock = Lock()

    def save_events(self, events):
        with self.lock:
            self.calls += 1
            inserted = 0
            for event in events:
                key = event.waba_id, event.phone_number_id, event.event_key
                if key not in self.rows:
                    self.rows[key] = event
                    inserted += 1
            return WhatsAppIngestionResult(inserted, len(events) - inserted)
