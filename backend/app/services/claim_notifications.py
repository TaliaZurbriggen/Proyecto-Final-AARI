"""Confirmación por correo posterior al alta del reclamo."""

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol
from uuid import UUID


class ClaimEmailDeliveryError(Exception):
    """El correo no se pudo entregar; el reclamo permanece creado."""


@dataclass(frozen=True)
class ClaimNotificationContext:
    recipient: str
    claim_number: int
    message: str


class ClaimNotificationRepository(Protocol):
    def get_notification_context(
        self, notification_id: UUID
    ) -> ClaimNotificationContext | None: ...

    def mark_notification_result(
        self,
        notification_id: UUID,
        *,
        sent: bool,
        safe_error: str | None = None,
    ) -> None: ...


class ClaimEmailSender(Protocol):
    def send(self, *, recipient: str, claim_number: int, message: str) -> None: ...


class SmtpClaimEmailSender:
    """Envía la confirmación con un límite de conexión menor a 30 segundos."""

    def send(self, *, recipient: str, claim_number: int, message: str) -> None:
        host = os.getenv("SMTP_HOST", "").strip()
        sender = os.getenv("SMTP_FROM", "").strip()
        if not host or not sender:
            raise ClaimEmailDeliveryError("El servicio de correo no está configurado.")
        try:
            port = int(os.getenv("SMTP_PORT", "587"))
        except ValueError as error:
            raise ClaimEmailDeliveryError(
                "La configuración del servicio de correo es inválida."
            ) from error

        username = os.getenv("SMTP_USERNAME", "").strip()
        password = os.getenv("SMTP_PASSWORD", "")
        use_starttls = os.getenv("SMTP_STARTTLS", "true").lower() not in {
            "0",
            "false",
            "no",
        }
        email = EmailMessage()
        email["Subject"] = f"AARI - Reclamo #{claim_number:06d} recibido"
        email["From"] = sender
        email["To"] = recipient
        email.set_content(message)

        try:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if use_starttls:
                    smtp.starttls()
                if username:
                    smtp.login(username, password)
                smtp.send_message(email)
        except (OSError, smtplib.SMTPException) as error:
            raise ClaimEmailDeliveryError(
                "No se pudo entregar la confirmación por correo."
            ) from error


class ClaimNotificationService:
    """Entrega en segundo plano y registra el resultado sin borrar el reclamo."""

    def __init__(
        self,
        repository: ClaimNotificationRepository,
        sender: ClaimEmailSender,
    ) -> None:
        self.repository = repository
        self.sender = sender

    def deliver(self, notification_id: UUID) -> bool:
        context = self.repository.get_notification_context(notification_id)
        if context is None:
            return False
        try:
            self.sender.send(
                recipient=context.recipient,
                claim_number=context.claim_number,
                message=context.message,
            )
        except ClaimEmailDeliveryError as error:
            self.repository.mark_notification_result(
                notification_id,
                sent=False,
                safe_error=str(error),
            )
            return False
        except Exception:
            self.repository.mark_notification_result(
                notification_id,
                sent=False,
                safe_error="No se pudo entregar la confirmación por correo.",
            )
            return False
        self.repository.mark_notification_result(notification_id, sent=True)
        return True
