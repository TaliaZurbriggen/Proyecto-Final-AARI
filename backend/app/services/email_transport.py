"""Correo común HU35: HTTPS explícito, secretos sólo en backend y errores seguros."""

import base64
import json
import os
import smtplib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, getaddresses
from functools import lru_cache
from pathlib import Path
from threading import Lock
from time import monotonic
from uuid import uuid4

import httpx

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
HTTP_TIMEOUT = 5.0
DELIVERY_BUDGET = 20.0
MAX_RESPONSE_BYTES = 65536
MAX_MESSAGE_BYTES = 262144


class EmailDeliveryError(Exception):
    """Sólo mensajes propios; nunca incluir respuestas HTTP ni secretos."""

    def __init__(self, message, *, retryable=False, uncertain=False, code="email_delivery_failed"):
        super().__init__(message)
        self.retryable = retryable
        self.uncertain = uncertain
        self.code = code


def _config_error():
    return EmailDeliveryError("La configuración del servicio de correo es inválida.",
                              code="email_configuration_invalid")


def _address(value, *, allow_name=False):
    if not isinstance(value, str) or "\r" in value or "\n" in value:
        raise _config_error()
    addresses = getaddresses([value])
    if len(addresses) != 1:
        raise _config_error()
    name, address = addresses[0]
    if not address or address.count("@") != 1 or (name and not allow_name):
        raise _config_error()
    if not allow_name and value != address:
        raise _config_error()
    return value


def _message(sender, recipient, subject, body):
    _address(sender, allow_name=True)
    _address(recipient)
    if not isinstance(subject, str) or "\r" in subject or "\n" in subject:
        raise _config_error()
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, recipient, subject
    message["Date"] = format_datetime(datetime.now(UTC), usegmt=True)
    # No usar el hostname, usuario, token ni destinatario para identificar el MIME.
    domain = message["From"].addresses[0].domain
    message["Message-ID"] = f"<{uuid4().hex}.aari@{domain}>"
    message.set_content(body)
    if len(message.as_bytes()) > MAX_MESSAGE_BYTES:
        raise EmailDeliveryError("El correo supera el tamaño permitido.")
    return message


@dataclass(frozen=True)
class GmailSettings:
    sender: str = field(repr=False)
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    refresh_token: str = field(repr=False)

    @classmethod
    def from_environment(cls):
        sender = _address(os.getenv("EMAIL_FROM", "").strip(), allow_name=True)
        path = os.getenv("GMAIL_CREDENTIALS_FILE", "").strip()
        values = [os.getenv(key, "").strip() for key in
                  ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")]
        if path:
            if any(values):
                raise _config_error()  # Evitar mezclar dos autorizaciones.
            try:
                raw = Path(path).read_bytes()
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError
                data = json.loads(raw)
                if (data.get("token_uri") != TOKEN_URL
                        or set(data.get("scopes", [])) != {SEND_SCOPE}):
                    raise ValueError
                values = [data.get(key) for key in ("client_id", "client_secret", "refresh_token")]
            except (OSError, ValueError, TypeError, AttributeError):
                raise _config_error() from None
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise _config_error()
        return cls(sender, *values)


class GmailApiEmailTransport:
    """Una llamada de envío por intento; sin reenvío ni fallback implícitos."""

    def __init__(self, settings, *, client_factory=None, clock=monotonic):
        self._settings = settings
        self._client_factory = client_factory or (lambda: httpx.Client(
            timeout=HTTP_TIMEOUT, follow_redirects=False, trust_env=False,
        ))
        self._clock = clock
        self._token_lock = Lock()
        self._token = None
        self._expires_at = 0.0

    def _post(self, client, url, *, deadline, sending=False, **kwargs):
        if self._clock() >= deadline:
            raise EmailDeliveryError("El servicio de correo demoró demasiado.", retryable=True)
        phase_timeout = min(HTTP_TIMEOUT, max(0.001, (deadline - self._clock()) / 4))
        try:
            with client.stream("POST", url, timeout=phase_timeout,
                               follow_redirects=False, **kwargs) as response:
                parts, size = [], 0
                for part in response.iter_bytes():
                    size += len(part)
                    if size > MAX_RESPONSE_BYTES or self._clock() >= deadline:
                        raise EmailDeliveryError(
                            "No se pudo confirmar el envío; revisar antes de reenviar."
                            if sending else "Respuesta de autorización no válida.",
                            uncertain=sending,
                        )
                    parts.append(part)
                try:
                    data = json.loads(b"".join(parts))
                except (ValueError, UnicodeError):
                    data = None
                return response.status_code, data
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise EmailDeliveryError("No se pudo conectar con el servicio de correo.",
                                      retryable=True) from None
        except httpx.HTTPError:
            raise EmailDeliveryError(
                "No se pudo confirmar el envío; revisar antes de reenviar."
                if sending else "No se pudo renovar la autorización de correo.",
                retryable=not sending, uncertain=sending,
            ) from None

    def _access_token(self, client, deadline):
        if not self._token_lock.acquire(timeout=HTTP_TIMEOUT):
            raise EmailDeliveryError("La autorización de correo está ocupada.", retryable=True)
        try:
            if self._token and self._clock() < self._expires_at:
                return self._token
            status, data = self._post(client, TOKEN_URL, deadline=deadline, data={
                "client_id": self._settings.client_id,
                "client_secret": self._settings.client_secret,
                "refresh_token": self._settings.refresh_token,
                "grant_type": "refresh_token",
            })
            if status == 400 and isinstance(data, dict) and data.get("error") == "invalid_grant":
                raise EmailDeliveryError(
                    "La autorización de correo venció o fue revocada. Volvé a autorizar la cuenta de AARI.",
                    code="gmail_reauthorization_required",
                )
            if not 200 <= status < 300:
                raise EmailDeliveryError("Google no pudo renovar la autorización de correo.",
                                          retryable=status == 429 or status >= 500)
            if not isinstance(data, dict):
                raise _config_error()
            scope = data.get("scope", "")
            token = data.get("access_token")
            seconds = data.get("expires_in")
            token_type = data.get("token_type")
            if (not isinstance(scope, str) or set(scope.split()) != {SEND_SCOPE}
                    or not isinstance(token_type, str) or token_type.lower() != "bearer"
                    or not isinstance(token, str) or not token.strip() or len(token) > 16384
                    or "\r" in token or "\n" in token
                    or not isinstance(seconds, (int, float)) or isinstance(seconds, bool)
                    or not 0 < seconds <= 86400):
                raise _config_error()
            self._token = token
            self._expires_at = self._clock() + max(0, min(seconds, 3600) - 60)
            return token
        finally:
            self._token_lock.release()

    def send(self, *, recipient, subject, body):
        message = _message(self._settings.sender, recipient, subject, body)
        deadline = self._clock() + DELIVERY_BUDGET
        with self._client_factory() as client:
            token = self._access_token(client, deadline)
            status, data = self._post(client, SEND_URL, deadline=deadline, sending=True,
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")})
        if 200 <= status < 300:
            if isinstance(data, dict) and isinstance(data.get("id"), str) and data["id"]:
                return
            raise EmailDeliveryError("No se pudo confirmar el envío; revisar antes de reenviar.",
                                      uncertain=True)
        if status == 401:
            with self._token_lock:
                if self._token == token:
                    self._token = None
            raise EmailDeliveryError("Google rechazó la autorización de envío.", retryable=True)
        if status >= 500:
            # Un error posterior al POST no prueba que no haya sido aceptado.
            raise EmailDeliveryError("No se pudo confirmar el envío; revisar antes de reenviar.",
                                      uncertain=True)
        if status == 429:
            raise EmailDeliveryError("Google limitó temporalmente el envío de correos.", retryable=True)
        if status == 403 and isinstance(data, dict):
            error = data.get("error")
            errors = error.get("errors", []) if isinstance(error, dict) else []
            if isinstance(errors, list) and any(
                isinstance(item, dict) and item.get("reason") in
                {"rateLimitExceeded", "userRateLimitExceeded"} for item in errors
            ):
                raise EmailDeliveryError("Google limitó temporalmente el envío de correos.", retryable=True)
        raise EmailDeliveryError("Google rechazó el correo. Revisá la configuración y el destinatario.")


class SmtpEmailTransport:
    """Compatibilidad optativa para entornos SMTP ya configurados."""

    def send(self, *, recipient, subject, body):
        sender = os.getenv("EMAIL_FROM", "").strip() or os.getenv("SMTP_FROM", "").strip()
        host = os.getenv("SMTP_HOST", "").strip()
        if not host or not sender:
            raise EmailDeliveryError("El servicio de correo no está configurado.")
        message = _message(sender, recipient, subject, body)
        try:
            port = int(os.getenv("SMTP_PORT", "587"))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            raise _config_error() from None
        try:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if os.getenv("SMTP_STARTTLS", "true").lower() not in {"0", "false", "no"}:
                    smtp.starttls()
                username = os.getenv("SMTP_USERNAME", "").strip()
                if username:
                    smtp.login(username, os.getenv("SMTP_PASSWORD", ""))
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise EmailDeliveryError("No se pudo entregar el correo por SMTP.", retryable=True) from None


@lru_cache(maxsize=4)
def _gmail_transport(settings):
    # Comparte la renovación entre rutas/hilos del mismo proceso; una credencial
    # renovada cambia la clave sin guardar tokens de acceso en disco.
    return GmailApiEmailTransport(settings)


_registry_lock = Lock()


def get_email_transport():
    provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower()
    if provider == "gmail_api":
        settings = GmailSettings.from_environment()
        with _registry_lock:
            return _gmail_transport(settings)
    if provider == "smtp":
        return SmtpEmailTransport()
    raise _config_error()


def send_email(*, recipient, subject, body):
    try:
        get_email_transport().send(recipient=recipient, subject=subject, body=body)
    except EmailDeliveryError:
        raise
    except Exception:
        # No propagar errores de bibliotecas que puedan incluir tokens o el MIME.
        raise EmailDeliveryError("No se pudo confirmar el envío; revisar antes de reenviar.",
                                  uncertain=True) from None
