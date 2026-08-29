from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_auth_service, get_current_user, require_admin
from app.core.security import COOKIE_NAME
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.services.auth_service import AccountLockedError, InvalidCredentialsError


USER = AuthenticatedUser(
    id=UUID("00000000-0000-0000-0000-000000000056"),
    email="admin@example.com",
    rol="administrador",
    primer_ingreso=False,
)


class FakeAuthService:
    def __init__(self, error=None):
        self.error = error

    def login(self, payload):
        del payload
        if self.error:
            raise self.error
        return USER

    def get_active_user(self, user_id):
        assert user_id == USER.id
        return USER


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-characters")
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    yield TestClient(app)
    app.dependency_overrides.pop(get_auth_service, None)


def test_login_sets_http_only_cookie(client):
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correcta"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["rol"] == "administrador"
    cookie = response.headers["set-cookie"]
    assert f"{COOKIE_NAME}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_login_returns_401_for_invalid_credentials(client):
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        InvalidCredentialsError()
    )

    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "incorrecta"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_login_returns_423_for_locked_account(client):
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        AccountLockedError()
    )

    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "incorrecta"},
    )

    assert response.status_code == 423
    assert response.json()["detail"]["code"] == "account_locked"


def test_me_reads_valid_session_cookie(client):
    login_response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correcta"},
    )

    response = client.get("/auth/me")

    assert login_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "admin@example.com"


def test_logout_removes_session_cookie(client):
    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert f"{COOKIE_NAME}=\"\"" in response.headers["set-cookie"]


def test_admin_route_requires_authentication(client):
    app.dependency_overrides.pop(require_admin, None)

    response = client.get("/propietarios")

    assert response.status_code == 401


def test_admin_route_rejects_a_different_role(client):
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides[get_current_user] = lambda: USER.model_copy(
        update={"rol": "operador"}
    )

    response = client.get("/propietarios")

    app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"
