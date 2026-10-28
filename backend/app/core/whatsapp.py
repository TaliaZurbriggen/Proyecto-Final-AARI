"""Configuración privada de HU19: ni recepción ni envíos se activan por defecto."""

import os
import re
from dataclasses import dataclass, field


class WhatsAppConfigurationError(RuntimeError):
    """Configuración ausente o insegura; nunca incluye valores privados."""


def canonical_recipient(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\+?[1-9][0-9]{5,14}", value):
        raise ValueError("El destinatario debe estar en formato internacional.")
    return value.removeprefix("+")


@dataclass(frozen=True)
class WhatsAppSettings:
    webhook_enabled: bool = False
    outbound_enabled: bool = False
    verify_token: str = field(default="", repr=False)
    app_secret: str = field(default="", repr=False)
    access_token: str = field(default="", repr=False)
    waba_id: str = ""
    phone_number_id: str = ""
    api_version: str = "v26.0"
    test_recipients: tuple[str, ...] = field(default=(), repr=False)

    @classmethod
    def from_env(cls):
        def enabled(name):
            return os.getenv(name, "false").strip().lower() in {"true", "1", "yes"}

        return cls(
            webhook_enabled=enabled("WHATSAPP_WEBHOOK_ENABLED"),
            outbound_enabled=enabled("WHATSAPP_OUTBOUND_ENABLED"),
            verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", ""),
            app_secret=os.getenv("WHATSAPP_APP_SECRET", ""),
            access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
            waba_id=os.getenv("WHATSAPP_WABA_ID", "").strip(),
            phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            api_version=os.getenv("WHATSAPP_API_VERSION", "v26.0").strip(),
            test_recipients=tuple(
                item.strip() for item in os.getenv("WHATSAPP_TEST_RECIPIENTS", "").split(",")
                if item.strip()
            ),
        )

    def validate_verification(self):
        # El token de verificación NO es el token OAuth ni el secreto de la app.
        if len(self.verify_token) < 16 or len(self.verify_token) > 256:
            raise WhatsAppConfigurationError("La verificación de WhatsApp no está configurada.")
        try:
            self.verify_token.encode("ascii")
        except UnicodeEncodeError:
            raise WhatsAppConfigurationError("La verificación de WhatsApp no está configurada.") from None

    def validate_receiving(self):
        if len(self.app_secret) < 16 or not self._valid_assets():
            raise WhatsAppConfigurationError("La recepción de WhatsApp no está configurada.")

    def validate_sending(self):
        if (not self.access_token.strip() or not self._valid_assets()
                or not re.fullmatch(r"v[1-9][0-9]{0,2}\.0", self.api_version)):
            raise WhatsAppConfigurationError("El envío de WhatsApp no está configurado.")
        try:
            recipients = {canonical_recipient(item) for item in self.test_recipients}
        except ValueError:
            raise WhatsAppConfigurationError("La lista de destinatarios de prueba es inválida.") from None
        if not recipients or len(recipients) > 5:
            raise WhatsAppConfigurationError("Se requieren entre uno y cinco destinatarios de prueba.")

    def _valid_assets(self):
        return bool(re.fullmatch(r"[0-9]{1,32}", self.waba_id)
                    and re.fullmatch(r"[0-9]{1,32}", self.phone_number_id))
