"""Entrega segura y reintento de credenciales iniciales."""

import os
import smtplib
from email.message import EmailMessage
from typing import Protocol
from uuid import UUID


class WelcomeEmailDeliveryError(Exception):
    """El correo no pudo enviarse; el mensaje siempre es seguro para persistir."""


class AccessNotFoundError(Exception):
    """No existe una cuenta vinculada a la persona solicitada."""


class AccessAlreadyActivatedError(Exception):
    """La contraseña temporal ya fue reemplazada y no debe reenviarse."""


class AccessRepository(Protocol):
    def mark_delivery_result(
        self,
        user_id: UUID,
        *,
        sent: bool,
        safe_error: str | None = None,
    ) -> None: ...

    def get_delivery_context(
        self,
        *,
        entity: str,
        entity_id: UUID,
    ) -> dict[str, object] | None: ...


class WelcomeEmailSender(Protocol):
    def send(
        self,
        *,
        recipient: str,
        person_name: str,
        temporary_password: str,
    ) -> None: ...


class SmtpWelcomeEmailSender:
    """Envía el correo sin registrar ni exponer la contraseña temporal."""

    def send(
        self,
        *,
        recipient: str,
        person_name: str,
        temporary_password: str,
    ) -> None:
        host = os.getenv("SMTP_HOST", "").strip()
        sender = os.getenv("SMTP_FROM", "").strip()
        if not host or not sender:
            raise WelcomeEmailDeliveryError(
                "El servicio de correo no está configurado."
            )

        try:
            port = int(os.getenv("SMTP_PORT", "587"))
        except ValueError as error:
            raise WelcomeEmailDeliveryError(
                "La configuración del servicio de correo es inválida."
            ) from error

        username = os.getenv("SMTP_USERNAME", "").strip()
        password = os.getenv("SMTP_PASSWORD", "")
        login_url = os.getenv("APP_LOGIN_URL", "http://localhost:5173/login").strip()
        use_starttls = os.getenv("SMTP_STARTTLS", "true").lower() not in {
            "0",
            "false",
            "no",
        }

        message = EmailMessage()
        message["Subject"] = "Tus credenciales de acceso a AARI"
        message["From"] = sender
        message["To"] = recipient
        message.set_content(
            "\n".join(
                [
                    f"Hola {person_name},",
                    "",
                    "La inmobiliaria creó tu acceso a AARI.",
                    f"Usuario: {recipient}",
                    f"Contraseña temporal: {temporary_password}",
                    f"Ingresá en: {login_url}",
                    "",
                    "Por seguridad, al ingresar deberás elegir una contraseña nueva.",
                ]
            )
        )

        try:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if use_starttls:
                    smtp.starttls()
                if username:
                    smtp.login(username, password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            raise WelcomeEmailDeliveryError(
                "No se pudo entregar el correo de bienvenida."
            ) from error


class AccessInvitationService:
    """Orquesta envío inicial y reintentos sin afectar la cuenta creada."""

    def __init__(
        self,
        repository: AccessRepository,
        sender: WelcomeEmailSender,
    ) -> None:
        self.repository = repository
        self.sender = sender

    def deliver(
        self,
        *,
        user_id: UUID,
        recipient: str,
        person_name: str,
        temporary_password: str,
    ) -> bool:
        try:
            self.sender.send(
                recipient=recipient,
                person_name=person_name,
                temporary_password=temporary_password,
            )
        except WelcomeEmailDeliveryError as error:
            self.repository.mark_delivery_result(
                user_id,
                sent=False,
                safe_error=str(error),
            )
            return False
        except Exception:
            self.repository.mark_delivery_result(
                user_id,
                sent=False,
                safe_error="No se pudo entregar el correo de bienvenida.",
            )
            return False

        self.repository.mark_delivery_result(user_id, sent=True)
        return True

    def retry(self, *, entity: str, entity_id: UUID) -> bool:
        context = self.repository.get_delivery_context(
            entity=entity,
            entity_id=entity_id,
        )
        if context is None:
            raise AccessNotFoundError
        if not bool(context["primer_ingreso"]):
            raise AccessAlreadyActivatedError
        return self.deliver(
            user_id=UUID(str(context["usuario_id"])),
            recipient=str(context["email"]),
            person_name=str(context["nombre_completo"]),
            temporary_password=str(context["dni"]),
        )
