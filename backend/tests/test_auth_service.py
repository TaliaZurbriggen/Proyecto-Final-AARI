from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.services.auth_service import (
    AccountLockedError,
    AuthService,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
)


USER_ID = UUID("00000000-0000-0000-0000-000000000056")
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


class FakeUsuariosRepository:
    def __init__(self, record=None) -> None:
        self.record = record
        self.failed_attempts = 0
        self.reset_calls = 0
        self.password_change_result = True
        self.password_changes = []

    def find_for_login(self, email, password):
        del email, password
        return self.record

    def get_by_id(self, user_id):
        del user_id
        return self.record

    def record_failed_attempt(self, user_id, *, now, max_attempts, lock_minutes):
        del user_id, now, lock_minutes
        self.failed_attempts += 1
        return NOW + timedelta(minutes=15) if self.failed_attempts >= max_attempts else None

    def reset_failed_attempts(self, user_id, *, now):
        del user_id, now
        self.reset_calls += 1

    def change_password(self, user_id, *, current_password, new_password):
        self.password_changes.append((user_id, current_password, new_password))
        if self.password_change_result and self.record:
            self.record["primer_ingreso"] = False
        return self.password_change_result


def user_record(**changes):
    return {
        "id": USER_ID,
        "email": "admin@example.com",
        "rol": "administrador",
        "primer_ingreso": False,
        "activo": True,
        "intentos_fallidos": 0,
        "bloqueado_hasta": None,
        "password_valid": True,
        **changes,
    }


def credentials():
    return LoginRequest(email="ADMIN@EXAMPLE.COM", password="correcta")


def test_login_returns_normalized_authenticated_user():
    repository = FakeUsuariosRepository(user_record())

    user = AuthService(repository).login(credentials(), now=NOW)

    assert user.id == USER_ID
    assert user.email == "admin@example.com"
    assert repository.reset_calls == 1


def test_login_rejects_unknown_user():
    with pytest.raises(InvalidCredentialsError):
        AuthService(FakeUsuariosRepository()).login(credentials(), now=NOW)


def test_login_records_invalid_password():
    repository = FakeUsuariosRepository(user_record(password_valid=False))

    with pytest.raises(InvalidCredentialsError):
        AuthService(repository).login(credentials(), now=NOW)

    assert repository.failed_attempts == 1


def test_third_invalid_password_locks_account():
    repository = FakeUsuariosRepository(user_record(password_valid=False))
    repository.failed_attempts = 2

    with pytest.raises(AccountLockedError):
        AuthService(repository).login(credentials(), now=NOW)


def test_login_rejects_account_still_locked():
    repository = FakeUsuariosRepository(
        user_record(bloqueado_hasta=NOW + timedelta(minutes=1))
    )

    with pytest.raises(AccountLockedError):
        AuthService(repository).login(credentials(), now=NOW)


def test_login_allows_account_after_lock_expired():
    repository = FakeUsuariosRepository(
        user_record(bloqueado_hasta=NOW - timedelta(seconds=1))
    )

    user = AuthService(repository).login(credentials(), now=NOW)

    assert user.id == USER_ID
    assert repository.reset_calls == 1


def test_login_rejects_inactive_account():
    with pytest.raises(InactiveAccountError):
        AuthService(FakeUsuariosRepository(user_record(activo=False))).login(
            credentials(), now=NOW
        )


def test_change_password_activates_account_and_returns_updated_user():
    repository = FakeUsuariosRepository(user_record(primer_ingreso=True))
    payload = ChangePasswordRequest(
        password_actual="30123456",
        password_nueva="segura123",
        confirmacion_password="segura123",
    )

    user = AuthService(repository).change_password(USER_ID, payload)

    assert user.primer_ingreso is False
    assert repository.password_changes == [(USER_ID, "30123456", "segura123")]


def test_change_password_rejects_invalid_current_password():
    repository = FakeUsuariosRepository(user_record(primer_ingreso=True))
    repository.password_change_result = False
    payload = ChangePasswordRequest(
        password_actual="incorrecta",
        password_nueva="segura123",
        confirmacion_password="segura123",
    )

    with pytest.raises(InvalidCurrentPasswordError):
        AuthService(repository).change_password(USER_ID, payload)
