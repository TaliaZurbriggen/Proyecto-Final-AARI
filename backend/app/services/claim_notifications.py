"""Entrega desacoplada de notificaciones de reclamos con reintentos persistidos."""

import asyncio
import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol
from uuid import UUID


LOGGER = logging.getLogger(__name__)
MAX_DELIVERY_ATTEMPTS = 3
RETRY_INTERVAL_SECONDS = 60
DEFAULT_DELIVERY_LEASE_SECONDS = 120
MIN_DELIVERY_LEASE_SECONDS = 30
MAX_DELIVERY_LEASE_SECONDS = 3600


def notification_lease_seconds() -> int:
    """Devuelve una reserva SMTP acotada y tolerante a configuración inválida."""

    configured = os.getenv(
        "NOTIFICATION_LEASE_SECONDS",
        str(DEFAULT_DELIVERY_LEASE_SECONDS),
    )
    try:
        seconds = int(configured)
    except ValueError:
        return DEFAULT_DELIVERY_LEASE_SECONDS
    return max(MIN_DELIVERY_LEASE_SECONDS, min(seconds, MAX_DELIVERY_LEASE_SECONDS))


class ClaimMessageDeliveryError(Exception):
    """El canal no pudo aceptar el mensaje."""


class ClaimEmailDeliveryError(ClaimMessageDeliveryError):
    """Compatibilidad: el correo no pudo entregarse."""


@dataclass(frozen=True)
class ClaimNotificationContext:
    id: UUID
    recipient: str
    claim_number: int
    channel: str
    subject: str
    message: str
    attempt_number: int


class ClaimNotificationRepository(Protocol):
    def claim_notification(
        self, notification_id: UUID
    ) -> ClaimNotificationContext | None: ...

    def claim_due_notifications(
        self, *, limit: int
    ) -> list[ClaimNotificationContext]: ...

    def mark_notification_result(
        self,
        notification_id: UUID,
        *,
        attempt_number: int,
        sent: bool,
        safe_error: str | None = None,
    ) -> bool: ...


class ClaimMessageSender(Protocol):
    def send(
        self,
        *,
        recipient: str,
        claim_number: int,
        subject: str,
        message: str,
    ) -> None: ...


class SmtpClaimEmailSender:
    """Envía correo con un máximo de 10 segundos por operación SMTP."""

    def send(
        self,
        *,
        recipient: str,
        claim_number: int,
        subject: str,
        message: str,
    ) -> None:
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
        email["Subject"] = subject
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
                "No se pudo entregar la notificación por correo."
            ) from error


class DisabledWhatsappSender:
    """Puerto explícito hasta que HU19 configure WhatsApp Business."""

    def send(self, **_: object) -> None:
        raise ClaimMessageDeliveryError(
            "El canal WhatsApp todavía no está configurado."
        )


class ClaimNotificationService:
    """Entrega mensajes reclamados atómicamente desde la bandeja de salida."""

    def __init__(
        self,
        repository: ClaimNotificationRepository,
        email_sender: ClaimMessageSender,
        whatsapp_sender: ClaimMessageSender | None = None,
    ) -> None:
        self.repository = repository
        self.senders = {
            "email": email_sender,
            "whatsapp": whatsapp_sender or DisabledWhatsappSender(),
        }

    def deliver(self, notification_id: UUID) -> bool:
        """Intenta una notificación concreta sin bloquear la petición HTTP."""

        context = self.repository.claim_notification(notification_id)
        if context is None:
            return False
        return self._deliver_claimed(context)

    def deliver_due(self, *, limit: int = 10) -> int:
        """Procesa un lote vencido; los bloqueos evitan envíos duplicados."""

        contexts = self.repository.claim_due_notifications(limit=limit)
        for context in contexts:
            self._deliver_claimed(context)
        return len(contexts)

    def _deliver_claimed(self, context: ClaimNotificationContext) -> bool:
        sender = self.senders.get(context.channel)
        if sender is None:
            safe_error = "El canal de notificación no está soportado."
            self.repository.mark_notification_result(
                context.id,
                attempt_number=context.attempt_number,
                sent=False,
                safe_error=safe_error,
            )
            return False

        try:
            sender.send(
                recipient=context.recipient,
                claim_number=context.claim_number,
                subject=context.subject,
                message=context.message,
            )
        except ClaimMessageDeliveryError as error:
            safe_error = str(error)
        except Exception:
            LOGGER.exception(
                "Fallo inesperado al enviar la notificación %s.", context.id
            )
            safe_error = "No se pudo entregar la notificación."
        else:
            recorded = self.repository.mark_notification_result(
                context.id,
                attempt_number=context.attempt_number,
                sent=True,
            )
            if not recorded:
                LOGGER.warning(
                    "Se ignoró el resultado de un intento vencido para %s.",
                    context.id,
                )
            return recorded

        self.repository.mark_notification_result(
            context.id,
            attempt_number=context.attempt_number,
            sent=False,
            safe_error=safe_error,
        )
        if context.attempt_number >= MAX_DELIVERY_ATTEMPTS:
            LOGGER.error(
                "Notificación %s agotada luego de %s intentos: %s",
                context.id,
                context.attempt_number,
                safe_error,
            )
        return False


async def run_notification_worker(
    service: ClaimNotificationService,
    stop_event: asyncio.Event,
    *,
    poll_interval_seconds: float = 5,
) -> None:
    """Recupera pendientes y reintenta según la fecha guardada en PostgreSQL."""

    while not stop_event.is_set():
        try:
            await asyncio.to_thread(service.deliver_due)
        except Exception:
            LOGGER.exception("No se pudo consultar la bandeja de notificaciones.")

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=poll_interval_seconds,
            )
        except TimeoutError:
            continue
