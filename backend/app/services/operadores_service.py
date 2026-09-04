"""Altas y bajas de operadores sin acoplar la cuenta a la disponibilidad SMTP."""

import logging
import secrets
import string
from math import ceil
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.schemas.operadores import (
    OperadorCreate, OperadorDesactivadoResponse, OperadorResponse, OperadoresPage,
)
from app.services.access_service import WelcomeEmailSender

logger = logging.getLogger(__name__)


class OperadorNotFoundError(Exception):
    pass


class DuplicateOperadorEmailError(Exception):
    pass


class OperadorAccessConflictError(Exception):
    """La cuenta está inactiva, activada o tiene un envío en curso."""


class OperadoresRepository(Protocol):
    def create(self, data: dict, temporary_password: str) -> dict: ...
    def get(self, user_id: UUID) -> dict | None: ...
    def list(self, *, page: int, page_size: int, search: str | None) -> tuple[list, int]: ...
    def prepare_retry(self, user_id: UUID, temporary_password: str) -> dict: ...
    def record_delivery(self, context: dict, *, sent: bool) -> None: ...
    def deactivate(self, user_id: UUID) -> int: ...


def generate_temporary_password() -> str:
    """Ocho caracteres criptográficamente aleatorios, con letras y números."""
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(8))
        if any(c.isalpha() for c in password) and any(c.isdigit() for c in password):
            return password


class OperadoresService:
    def __init__(self, repository: OperadoresRepository, sender: WelcomeEmailSender):
        self.repository = repository
        self.sender = sender

    def _deliver(self, context: dict, temporary_password: str) -> None:
        # El alta/rotación ya está confirmada; no se mantiene una transacción en SMTP.
        try:
            self.sender.send(
                recipient=context["email"],
                person_name=context["nombre_completo"],
                temporary_password=temporary_password,
            )
            sent = True
        except Exception:
            # Nunca persistir detalles del proveedor que puedan incluir credenciales.
            sent = False
        try:
            self.repository.record_delivery(context, sent=sent)
        except SQLAlchemyError:
            # La cuenta existe y el estado queda pendiente; se permite recuperar el envío.
            logger.warning("No se pudo registrar el resultado del correo de operador.")

    def create(self, payload: OperadorCreate) -> OperadorResponse:
        password = generate_temporary_password()
        context = self.repository.create(payload.model_dump(), password)
        self._deliver(context, password)
        return self.get(UUID(str(context["id"])))

    def get(self, user_id: UUID) -> OperadorResponse:
        record = self.repository.get(user_id)
        if record is None:
            raise OperadorNotFoundError
        return OperadorResponse.model_validate(record)

    def list(self, *, page: int, page_size: int, search: str | None) -> OperadoresPage:
        items, total = self.repository.list(
            page=page, page_size=page_size, search=search.strip() if search else None,
        )
        return OperadoresPage(
            items=items, total=total, page=page, page_size=page_size,
            total_pages=ceil(total / page_size),
        )

    def retry_access(self, user_id: UUID) -> OperadorResponse:
        password = generate_temporary_password()
        context = self.repository.prepare_retry(user_id, password)
        self._deliver(context, password)
        return self.get(user_id)

    def deactivate(self, user_id: UUID) -> OperadorDesactivadoResponse:
        count = self.repository.deactivate(user_id)
        return OperadorDesactivadoResponse(
            operador=self.get(user_id), reclamos_liberados=count,
        )
