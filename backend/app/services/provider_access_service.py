"""Invitaciones HU32: secreto efímero, persistencia por hash y envío sin transacción abierta."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import os
import secrets
import smtplib
from email.message import EmailMessage
from urllib.parse import urlsplit, urlunsplit

from app.schemas.provider_access import ProviderAccessResponse, ProviderProfileResponse


class ProviderAccessError(Exception):
    def __init__(self, message, *, code="provider_access_conflict", status=409, field_name=None):
        super().__init__(message)
        self.code, self.status, self.field_name = code, status, field_name


def invitation_digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def invitation_hours():
    try:
        return max(1, min(168, int(os.getenv("PROVIDER_INVITATION_HOURS", "24"))))
    except ValueError:
        return 24


@dataclass(frozen=True)
class InvitationDelivery:
    invitation_id: str
    email: str = field(repr=False)
    name: str = field(repr=False)
    token: str = field(repr=False)


class SmtpProviderInvitationSender:
    def send(self, delivery):
        login = urlsplit(os.getenv("APP_LOGIN_URL", "http://localhost:5173/login"))
        if (login.username or login.password or not login.hostname or
            (login.scheme != "https" and not
             (login.scheme == "http" and login.hostname in {"localhost", "127.0.0.1", "::1"}))):
            raise ValueError("La URL de acceso no es segura.")
        link = urlunsplit((login.scheme, login.netloc, "/activar-proveedor", "", "token=" + delivery.token))
        host, sender = os.getenv("SMTP_HOST", "").strip(), os.getenv("SMTP_FROM", "").strip()
        if not host or not sender:
            raise ValueError("El servicio de correo no está configurado.")
        message = EmailMessage()
        message["Subject"] = "Activá tu acceso de proveedor a AARI"
        message["From"], message["To"] = sender, delivery.email
        message.set_content(
            f"Hola {delivery.name},\n\nLa inmobiliaria te invitó a AARI.\n"
            f"Elegí tu contraseña en: {link}\n\n"
            "El enlace tiene vencimiento y es de un solo uso. No lo compartas.\n"
            "Si no esperabas esta invitación, contactá a la inmobiliaria."
        )
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as smtp:
            if os.getenv("SMTP_STARTTLS", "true").lower() not in {"false", "0", "no"}:
                smtp.starttls()
            username = os.getenv("SMTP_USERNAME", "").strip()
            if username:
                smtp.login(username, os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)


class ProviderAccessService:
    def __init__(self, repository, sender=None):
        self.repository = repository
        self.sender = sender or SmtpProviderInvitationSender()

    def get(self, provider_id, *, now=None):
        return ProviderAccessResponse(**self.repository.get_access(provider_id, now=now or datetime.now(UTC)))

    def invite(self, provider_id, payload, *, now=None):
        current = now or datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        delivery = self.repository.prepare_invitation(
            provider_id, email=str(payload.email), request_id=payload.request_id,
            token_hash=invitation_digest(token), now=current,
            expires=current + timedelta(hours=invitation_hours()), token=token,
        )
        if delivery is not None:
            try:
                self.sender.send(delivery)
            except Exception:
                # No persistir la excepción: puede contener destinatario, URL o secreto SMTP.
                self.repository.record_delivery(delivery.invitation_id, sent=False)
            else:
                self.repository.record_delivery(delivery.invitation_id, sent=True)
        return self.get(provider_id, now=current)

    def activate(self, payload, *, now=None):
        self.repository.activate(invitation_digest(payload.token), payload.password_nueva,
                                 now=now or datetime.now(UTC))

    def profile(self, user):
        record = self.repository.profile(user)
        enabled = os.getenv('AARI_QUOTE_PORTAL_ENABLED', 'false').lower() in {'1','true','yes'}
        return ProviderProfileResponse(**record, solicitudes_disponibles=enabled)
