"""Adaptador de envío explícito. Sin worker, endpoint de envío ni reintentos automáticos."""

import re

import httpx

from app.core.whatsapp import WhatsAppConfigurationError, WhatsAppSettings, canonical_recipient
from app.schemas.whatsapp import WhatsAppSendReceipt


class WhatsAppSendError(RuntimeError):
    def __init__(self, message, *, outcome="not_sent"):
        super().__init__(message)
        self.outcome = outcome
        # Un timeout puede ocurrir DESPUÉS de que Meta aceptó el mensaje.
        self.retryable = False


class MetaWhatsAppSender:
    def __init__(self, settings: WhatsAppSettings, *, transport=None):
        self.settings = settings
        self.transport = transport

    def send_template(self, *, recipient, template_name, language="es_AR", parameters=()):
        """Enviar una plantilla ya aprobada por Meta; no abre ventanas de 24h."""
        if not isinstance(template_name, str) or not re.fullmatch(r"[a-z0-9_]{1,512}", template_name):
            raise WhatsAppSendError("La plantilla de WhatsApp es inválida.")
        if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", language):
            raise WhatsAppSendError("El idioma de la plantilla es inválido.")
        if (not isinstance(parameters, (list, tuple)) or len(parameters) > 20
                or any(not isinstance(value, str) or not 1 <= len(value) <= 4096
                       or "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
                       for value in parameters)):
            raise WhatsAppSendError("Los parámetros de la plantilla son inválidos.")
        template = {"name": template_name, "language": {"code": language}}
        if parameters:
            template["components"] = [{"type": "body", "parameters": [
                {"type": "text", "text": value} for value in parameters
            ]}]
        return self._send(recipient, {"type": "template", "template": template})

    def _send(self, recipient, payload):
        if not self.settings.outbound_enabled:
            raise WhatsAppSendError("Los envíos de WhatsApp están desactivados.")
        try:
            self.settings.validate_sending()
            recipient = canonical_recipient(recipient)
        except (WhatsAppConfigurationError, ValueError):
            raise WhatsAppSendError("El envío de WhatsApp no está configurado correctamente.") from None
        allowed = {canonical_recipient(value) for value in self.settings.test_recipients}
        if recipient not in allowed:
            raise WhatsAppSendError("El destinatario no está autorizado para pruebas.")
        url = f"https://graph.facebook.com/{self.settings.api_version}/{self.settings.phone_number_id}/messages"
        try:
            # Host fijo, TLS, sin redirects/proxies heredados y una sola solicitud.
            with httpx.Client(transport=self.transport, timeout=httpx.Timeout(10, connect=5),
                              follow_redirects=False, trust_env=False) as client:
                response = client.post(url, headers={"Authorization": f"Bearer {self.settings.access_token}"},
                                       json={"messaging_product": "whatsapp", "recipient_type": "individual",
                                             "to": recipient, **payload})
        except httpx.TransportError:
            raise WhatsAppSendError("El resultado del envío es desconocido; requiere revisión antes de repetirlo.",
                                    outcome="unknown") from None
        if response.status_code >= 500 or 300 <= response.status_code < 400:
            raise WhatsAppSendError("El resultado del envío es desconocido; requiere revisión antes de repetirlo.",
                                    outcome="unknown")
        if not 200 <= response.status_code < 300:
            # No propagar el cuerpo de error de Meta ni request/headers privados.
            raise WhatsAppSendError("Meta rechazó el envío de WhatsApp.", outcome="rejected")
        try:
            result = response.json()
            message_id = result["messages"][0]["id"]
            if not isinstance(message_id, str) or not 1 <= len(message_id) <= 512:
                raise ValueError
        except (ValueError, KeyError, IndexError, TypeError):
            raise WhatsAppSendError("Meta respondió sin un identificador verificable; requiere revisión.",
                                    outcome="unknown") from None
        return WhatsAppSendReceipt(message_id)
