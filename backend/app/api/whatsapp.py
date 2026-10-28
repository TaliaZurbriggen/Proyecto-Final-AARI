"""Único ingreso público de WhatsApp: challenge o evento autenticado por Meta."""

import hmac
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.core.whatsapp import WhatsAppConfigurationError, WhatsAppSettings
from app.db.whatsapp import SqlAlchemyWhatsAppInbox
from app.services.whatsapp_webhook import (
    MAX_WEBHOOK_BYTES, WhatsAppAssetError, WhatsAppPayloadError, parse_events, valid_signature,
)


router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp"])


def get_whatsapp_settings():
    return WhatsAppSettings.from_env()


def get_whatsapp_inbox():
    return SqlAlchemyWhatsAppInbox()


def _enabled(settings):
    if not settings.webhook_enabled:
        raise HTTPException(404, "Canal no disponible.")


@router.get("")
def verify_webhook(request: Request, settings: WhatsAppSettings = Depends(get_whatsapp_settings)):
    _enabled(settings)
    try:
        settings.validate_verification()
    except WhatsAppConfigurationError:
        raise HTTPException(503, "La verificación de WhatsApp no está configurada.") from None
    query = request.query_params
    # Rechazar parámetros repetidos: no aceptar interpretaciones ambiguas.
    if any(len(query.getlist(key)) != 1 for key in ("hub.mode", "hub.verify_token", "hub.challenge")):
        raise HTTPException(403, "Verificación inválida.")
    challenge = query["hub.challenge"]
    if (query["hub.mode"] != "subscribe" or not re.fullmatch(r"[0-9]{1,256}", challenge)
            or not hmac.compare_digest(query["hub.verify_token"].encode(), settings.verify_token.encode())):
        raise HTTPException(403, "Verificación inválida.")
    return PlainTextResponse(challenge, headers={"Cache-Control": "no-store"})


@router.post("")
async def receive_webhook(
    request: Request, settings: WhatsAppSettings = Depends(get_whatsapp_settings),
    inbox=Depends(get_whatsapp_inbox),
):
    _enabled(settings)
    try:
        settings.validate_receiving()
    except WhatsAppConfigurationError:
        raise HTTPException(503, "La recepción de WhatsApp no está configurada.") from None
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Se requiere JSON.")
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise HTTPException(415, "No se admite contenido comprimido.")
    signatures = request.headers.getlist("x-hub-signature-256")
    if len(signatures) != 1:
        raise HTTPException(403, "Firma de WhatsApp inválida.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_WEBHOOK_BYTES:
            raise HTTPException(413, "Evento demasiado grande.")
        raw.extend(chunk)
    raw = bytes(raw)
    if not valid_signature(raw, signatures[0], settings.app_secret):
        raise HTTPException(403, "Firma de WhatsApp inválida.")
    try:
        events = parse_events(raw, settings)
    except WhatsAppAssetError:
        raise HTTPException(403, "Recurso de WhatsApp no autorizado.") from None
    except WhatsAppPayloadError:
        raise HTTPException(400, "Evento de WhatsApp inválido.") from None
    try:
        await run_in_threadpool(inbox.save_events, events)
    except SQLAlchemyError:
        # No reconocer un evento que no quedó guardado. Meta podrá reenviarlo.
        raise HTTPException(503, "No se pudo registrar el evento de WhatsApp.") from None
    return {"received": True}
