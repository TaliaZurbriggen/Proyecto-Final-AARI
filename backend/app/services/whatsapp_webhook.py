"""Autentica y normaliza eventos sin consultar LLM, descargar medios ni decidir gastos."""

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime

from app.core.whatsapp import WhatsAppSettings, canonical_recipient
from app.schemas.whatsapp import WhatsAppInboundEvent


MAX_WEBHOOK_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 1000


class WhatsAppPayloadError(ValueError):
    pass


class WhatsAppAssetError(WhatsAppPayloadError):
    pass


def valid_signature(raw: bytes, signature: str, app_secret: str) -> bool:
    if not re.fullmatch(r"sha256=[0-9a-fA-F]{64}", signature):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature[7:].lower())


def _string(value, maximum=512):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or "\x00" in value:
        raise WhatsAppPayloadError("Evento de WhatsApp inválido.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise WhatsAppPayloadError("Evento de WhatsApp inválido.") from None
    return value


def _array(value):
    if not isinstance(value, list) or len(value) > MAX_EVENTS:
        raise WhatsAppPayloadError("Lote de WhatsApp inválido.")
    return value


def _object(value):
    if not isinstance(value, dict):
        raise WhatsAppPayloadError("Evento de WhatsApp inválido.")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WhatsAppPayloadError("JSON con claves duplicadas.")
        result[key] = value
    return result


def _reject_constant(_value):
    raise WhatsAppPayloadError("JSON inválido.")


def parse_events(raw: bytes, settings: WhatsAppSettings) -> list[WhatsAppInboundEvent]:
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant)
        if _object(payload).get("object") != "whatsapp_business_account":
            raise WhatsAppPayloadError("Objeto de webhook no soportado.")
        events = []
        changes_seen = 0
        for entry in _array(payload.get("entry")):
            entry = _object(entry)
            if entry.get("id") != settings.waba_id:
                raise WhatsAppAssetError("Cuenta de WhatsApp no autorizada.")
            for change in _array(entry.get("changes")):
                changes_seen += 1
                if changes_seen > MAX_EVENTS:
                    raise WhatsAppPayloadError("Lote de WhatsApp demasiado grande.")
                change = _object(change)
                if change.get("field") != "messages":
                    continue
                value = _object(change.get("value"))
                if value.get("messaging_product") != "whatsapp":
                    raise WhatsAppPayloadError("Producto no soportado.")
                metadata = _object(value.get("metadata"))
                if metadata.get("phone_number_id") != settings.phone_number_id:
                    raise WhatsAppAssetError("Número de WhatsApp no autorizado.")
                for kind, items in (("mensaje", value.get("messages", [])),
                                    ("estado", value.get("statuses", []))):
                    for item in _array(items):
                        events.append(_event(_object(item), kind, settings))
                        if len(events) > MAX_EVENTS:
                            raise WhatsAppPayloadError("Lote de WhatsApp demasiado grande.")
        return events
    except WhatsAppPayloadError:
        raise
    except (ValueError, TypeError, OverflowError, OSError, RecursionError):
        raise WhatsAppPayloadError("Evento de WhatsApp inválido.") from None


def _event(item, kind, settings):
    external_id = _string(item.get("id"))
    timestamp = item.get("timestamp")
    if isinstance(timestamp, bool) or not re.fullmatch(r"[0-9]{1,12}", str(timestamp)):
        raise WhatsAppPayloadError("Fecha de evento inválida.")
    occurred_at = datetime.fromtimestamp(int(timestamp), UTC)
    event_type = _string(item.get("type") if kind == "mensaje" else item.get("status"), 64)
    participant = canonical_recipient(item.get("from") if kind == "mensaje" else item.get("recipient_id"))
    supported = kind == "estado" and event_type in {"sent", "delivered", "read", "failed", "deleted"}
    data = {"type": event_type}
    if kind == "mensaje":
        if event_type == "text":
            data["text"] = _string(_object(item.get("text")).get("body"), 4096)
            supported = True
        if item.get("context") is not None:
            data["context_message_id"] = _string(_object(item["context"]).get("id"))
    else:
        if item.get("biz_opaque_callback_data") is not None:
            data["correlation"] = _string(item["biz_opaque_callback_data"])
        if item.get("errors") is not None:
            data["error_codes"] = []
            for error in _array(item["errors"]):
                code = _object(error).get("code")
                if not isinstance(code, int) or isinstance(code, bool):
                    raise WhatsAppPayloadError("Código de error inválido.")
                data["error_codes"].append(code)
    # El mismo mensaje conserva su identidad aunque Meta cambie el envoltorio.
    # Los estados se conservan por tipo y fecha, incluso si llegan desordenados.
    identity = [kind, external_id] if kind == "mensaje" else [kind, external_id, event_type, str(timestamp)]
    key = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
    return WhatsAppInboundEvent(
        waba_id=settings.waba_id, phone_number_id=settings.phone_number_id,
        event_key=key, external_id=external_id, kind=kind, event_type=event_type,
        participant=participant, occurred_at=occurred_at, data=data,
        state="pendiente" if supported else "no_soportado",
    )
