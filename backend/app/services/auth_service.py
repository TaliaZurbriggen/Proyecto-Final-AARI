"""Reglas de autenticación independientes del transporte HTTP."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.schemas.auth import AuthenticatedUser, ChangePasswordRequest, LoginRequest


MAX_FAILED_ATTEMPTS = 3
LOCK_MINUTES = 15


class InvalidCredentialsError(Exception):
    """Las credenciales no son válidas."""


class AccountLockedError(Exception):
    """La cuenta se encuentra temporalmente bloqueada."""


class InactiveAccountError(Exception):
    """La cuenta fue desactivada."""


class InvalidCurrentPasswordError(Exception):
    """La contraseña actual no coincide con la credencial vigente."""


class UsuariosRepository(Protocol):
    def find_for_login(self, email: str, password: str) -> dict[str, object] | None: ...

    def get_by_id(self, user_id: UUID) -> dict[str, object] | None: ...

    def record_failed_attempt(
        self,
        user_id: UUID,
        *,
        now: datetime,
        max_attempts: int,
        lock_minutes: int,
    ) -> datetime | None: ...

    def reset_failed_attempts(self, user_id: UUID, *, now: datetime) -> None: ...


class PasswordRepository(Protocol):
    def change_password(
        self,
        user_id: UUID,
        *,
        current_password: str,
        new_password: str,
    ) -> bool: ...


class AuthService:
    def __init__(
        self,
        repository: UsuariosRepository,
        password_repository: PasswordRepository | None = None,
    ) -> None:
        self.repository = repository
        self.password_repository = password_repository or repository

    def login(
        self,
        payload: LoginRequest,
        *,
        now: datetime | None = None,
    ) -> AuthenticatedUser:
        current_time = now or datetime.now(UTC)
        record = self.repository.find_for_login(payload.email, payload.password)
        if record is None:
            raise InvalidCredentialsError

        user_id = UUID(str(record["id"]))
        blocked_until = record.get("bloqueado_hasta")
        if isinstance(blocked_until, datetime) and blocked_until > current_time:
            raise AccountLockedError

        if not bool(record["activo"]):
            raise InactiveAccountError

        if not bool(record["password_valid"]):
            new_blocked_until = self.repository.record_failed_attempt(
                user_id,
                now=current_time,
                max_attempts=MAX_FAILED_ATTEMPTS,
                lock_minutes=LOCK_MINUTES,
            )
            if new_blocked_until is not None:
                raise AccountLockedError
            raise InvalidCredentialsError

        self.repository.reset_failed_attempts(user_id, now=current_time)
        return AuthenticatedUser(
            id=user_id,
            email=record["email"],
            rol=str(record["rol"]),
            primer_ingreso=bool(record["primer_ingreso"]),
            perfil_id=record.get("perfil_id"),
        )

    def get_active_user(self, user_id: UUID) -> AuthenticatedUser:
        record = self.repository.get_by_id(user_id)
        if record is None:
            raise InvalidCredentialsError
        if not bool(record["activo"]):
            raise InactiveAccountError
        return AuthenticatedUser(
            id=user_id,
            email=record["email"],
            rol=str(record["rol"]),
            primer_ingreso=bool(record["primer_ingreso"]),
            perfil_id=record.get("perfil_id"),
        )

    def change_password(
        self,
        user_id: UUID,
        payload: ChangePasswordRequest,
    ) -> AuthenticatedUser:
        changed = self.password_repository.change_password(
            user_id,
            current_password=payload.password_actual,
            new_password=payload.password_nueva,
        )
        if not changed:
            raise InvalidCurrentPasswordError
        return self.get_active_user(user_id)
