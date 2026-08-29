from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.schemas.auth import LoginRequest
from app.services.auth_service import (
    AccountLockedError,
    AuthService,
    InactiveAccountError,
    InvalidCredentialsError,
)


USER_ID = UUID("00000000-0000-0000-0000-000000000056")
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


class FakeUsuariosRepository:
    def __init__(self, record=None) -> None:
        self.record = record
        self.failed_attempts = 0
        self.reset_calls = 0

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
