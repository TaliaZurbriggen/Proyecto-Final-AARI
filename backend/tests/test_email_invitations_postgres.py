"""HU35: invitación HTTP -> PostgreSQL -> MIME Gmail -> activación, sin red."""

import base64
import json
import os
from email import message_from_bytes, policy
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api.auth import get_auth_service, require_admin
from app.api.provider_access import get_provider_access_service
from app.db.usuarios import SqlAlchemyUsuariosRepository
from app.main import app
from app.services import email_transport as mail
from app.services.auth_service import AuthService
from app.services.provider_access_service import ProviderAccessService, invitation_digest
from tests.test_provider_access_postgres import case


pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"),
                                reason="Sólo PostgreSQL local dedicado.")


def configured_client(case, monkeypatch, handler):
    engine, repo, _, provider, _ = case
    sessions = sessionmaker(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO usuarios(email,password_hash,rol,primer_ingreso,activo)
            VALUES ('admin@example.com',crypt(:password,gen_salt('bf')),
                    'administrador',false,true)
        """), {"password": "PruebaLocal123"})
    monkeypatch.delitem(app.dependency_overrides, require_admin, raising=False)
    monkeypatch.setitem(app.dependency_overrides, get_auth_service,
                        lambda: AuthService(SqlAlchemyUsuariosRepository(sessions)))
    monkeypatch.setitem(app.dependency_overrides, get_provider_access_service,
                        lambda: ProviderAccessService(repo))
    monkeypatch.setenv("JWT_SECRET", "local-testing-secret-with-more-than-32-characters")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("APP_LOGIN_URL", "https://aari.example.com/login")
    transport = mail.GmailApiEmailTransport(
        mail.GmailSettings("AARI <sender@example.com>", "fake-client", "fake-secret", "fake-refresh"),
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(mail, "get_email_transport", lambda: transport)
    monkeypatch.setattr(mail.smtplib, "SMTP", lambda *a, **k: pytest.fail("No debe abrir SMTP"))
    return TestClient(app)


def test_real_http_invitation_uses_configured_gmail_and_activation_fragment(case, monkeypatch):
    engine, repo, _, provider, _ = case
    messages, calls = [], []

    def handler(request):
        calls.append(str(request.url))
        if str(request.url) == mail.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "fake", "token_type": "Bearer",
                                            "expires_in": 3600, "scope": mail.SEND_SCOPE})
        assert str(request.url) == mail.SEND_URL
        messages.append(message_from_bytes(
            base64.urlsafe_b64decode(json.loads(request.content)["raw"]), policy=policy.default))
        return httpx.Response(200, json={"id": "synthetic"})

    with configured_client(case, monkeypatch, handler) as client:
        endpoint = f"/proveedores/{provider}/acceso"
        payload = {"email": "service@example.com", "request_id": str(uuid4())}
        assert client.post(endpoint, json=payload).status_code == 401
        assert client.post("/auth/login", json={"email": "admin@example.com",
                                               "password": "PruebaLocal123"}).status_code == 200
        response = client.post(endpoint, json=payload)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["envio_estado"] == "enviado"
        assert client.post(endpoint, json=payload).status_code == 200  # Replay no reenvía.
        assert calls == [mail.TOKEN_URL, mail.SEND_URL] and len(messages) == 1
        message = messages[0]
        assert message["Subject"] == "Activá tu acceso de proveedor a AARI"
        assert str(message["To"]) == "service@example.com"
        assert message["Date"] and message["Message-ID"]
        body = message.get_content()
        assert "Contraseña temporal" not in body and "PruebaLocal123" not in body
        link = urlsplit(body.split("Elegí tu contraseña en: ", 1)[1].splitlines()[0])
        assert (link.scheme, link.netloc, link.path, link.query) == (
            "https", "aari.example.com", "/activar-proveedor", "")
        token = parse_qs(link.fragment)["token"][0]
        assert token not in response.text
        with engine.connect() as connection:
            row = connection.execute(text("SELECT token_hash,envio_estado,usado_en FROM proveedor_invitaciones")).mappings().one()
            assert row["token_hash"] == invitation_digest(token)
            assert row["envio_estado"] == "enviado" and row["usado_en"] is None
        client.cookies.clear()
        activation = {"token": token, "password_nueva": "PruebaLocal123",
                      "confirmacion_password": "PruebaLocal123"}
        assert client.post("/auth/proveedores/activar", json=activation).status_code == 200
        assert client.post("/auth/proveedores/activar", json=activation).status_code == 400
        assert client.post("/auth/login", json={"email": "service@example.com",
                                               "password": "PruebaLocal123"}).status_code == 200
        profile = client.get("/proveedor/perfil")
        assert profile.status_code == 200 and profile.json()["proveedor_id"] == str(provider)
        assert client.post(endpoint, json=payload).status_code == 403
        assert calls == [mail.TOKEN_URL, mail.SEND_URL]


@pytest.mark.parametrize("phase,status", [("token", 400), ("send", 429), ("send", 503)])
def test_invitation_failure_is_persisted_once_without_smtp_or_active_account(case, monkeypatch, phase, status):
    engine, repo, _, provider, _ = case
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if str(request.url) == mail.TOKEN_URL:
            return (httpx.Response(status, json={"error": "invalid_grant"}) if phase == "token"
                    else httpx.Response(200, json={"access_token": "fake", "token_type": "Bearer",
                                                  "expires_in": 3600, "scope": mail.SEND_SCOPE}))
        return httpx.Response(status, json={"error": {"message": "private-error-not-to-save"}})

    with configured_client(case, monkeypatch, handler) as client:
        assert client.post("/auth/login", json={"email": "admin@example.com",
                                               "password": "PruebaLocal123"}).status_code == 200
        payload = {"email": "service@example.com", "request_id": str(uuid4())}
        endpoint = f"/proveedores/{provider}/acceso"
        response = client.post(endpoint, json=payload)
        assert response.status_code == 200 and response.json()["envio_estado"] == "fallido"
        assert "private-error" not in response.text and "fake-refresh" not in response.text
        assert client.post(endpoint, json=payload).status_code == 200
        assert len(calls) == (1 if phase == "token" else 2)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT envio_estado FROM proveedor_invitaciones")).scalar_one() == "fallido"
            assert connection.execute(text("SELECT activo FROM usuarios WHERE rol='proveedor'")).scalar_one() is False
