"""HU32: contratos HTTP, correo simulado y autenticación sin llamadas externas."""

from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.api.auth import get_current_user, require_admin
from app.api.provider_access import get_provider_access_service
from app.main import app
from app.schemas.auth import AuthenticatedUser, LoginRequest
from app.schemas.provider_access import ProviderActivationRequest, ProviderInvitationRequest
from app.services.auth_service import AuthService, InactiveAccountError
from app.services.provider_access_service import (
    InvitationDelivery, ProviderAccessError, ProviderAccessService, SmtpProviderInvitationSender, invitation_digest,
)
from tests.test_auth_service import FakeUsuariosRepository, user_record


PROVIDER = UUID("00000000-0000-0000-0000-000000000032")
TOKEN = "x" * 43


def test_email_normalized_before_validation():
    data = ProviderInvitationRequest(email="  Service@EXAMPLE.COM  ", request_id=uuid4())
    assert data.email == "service@example.com"


@pytest.mark.parametrize("changes", [
    {"token": "corto"}, {"password_nueva": "sinumeros"},
    {"confirmacion_password": "distinta1"}, {"password_nueva": "á" * 40 + "1"},
])
def test_activation_rejects_invalid_fields(changes):
    with pytest.raises(ValidationError):
        ProviderActivationRequest(**{"token": TOKEN, "password_nueva": "Prueba123", "confirmacion_password": "Prueba123", **changes})


@pytest.mark.parametrize("changes", [
    {"activo": False}, {"proveedor_activo": False}, {"perfil_id": None}, {"primer_ingreso": True},
])
def test_provider_session_rechecks_domain_status(changes):
    values = {"rol": "proveedor", "perfil_id": PROVIDER, "proveedor_activo": True, **changes}
    service = AuthService(FakeUsuariosRepository(user_record(**values)))
    with pytest.raises(InactiveAccountError):
        service.login(LoginRequest(email="service@example.com", password="Prueba123"))
    with pytest.raises(InactiveAccountError):
        service.get_active_user(PROVIDER)


def test_provider_valid_login_and_no_secrets_in_representations():
    repo = FakeUsuariosRepository(user_record(rol="proveedor", perfil_id=PROVIDER, proveedor_activo=True))
    assert AuthService(repo).get_active_user(PROVIDER).perfil_id == PROVIDER
    assert TOKEN not in repr(InvitationDelivery("id", "service@example.com", "Servicio", TOKEN))
    assert TOKEN not in repr(ProviderActivationRequest(token=TOKEN, password_nueva="Prueba123", confirmacion_password="Prueba123"))


class FakeRepo:
    def __init__(self):
        self.prepared = None
        self.sent = None
        self.replay = False

    def prepare_invitation(self, provider_id, **kwargs):
        self.prepared = kwargs
        return None if self.replay else InvitationDelivery("i", kwargs["email"], "Servicio", kwargs["token"])

    def record_delivery(self, invitation_id, *, sent):
        self.sent = sent

    def get_access(self, provider_id, **kwargs):
        return {"proveedor_id": provider_id, "email": "service@example.com", "estado": "pendiente",
                "envio_estado": "enviado" if self.sent else "fallido", "puede_invitar": True}


def test_service_only_persists_digest_and_does_not_deliver_replays():
    repo, messages = FakeRepo(), []
    service = ProviderAccessService(repo, SimpleNamespace(send=messages.append))
    payload = ProviderInvitationRequest(email="service@example.com", request_id=uuid4())
    result = service.invite(PROVIDER, payload)
    assert repo.sent and len(messages) == 1
    assert repo.prepared["token_hash"] == invitation_digest(messages[0].token)
    assert repo.prepared["expires"] > repo.prepared["now"]
    assert "token" not in result.model_dump()
    repo.replay = True
    service.invite(PROVIDER, payload)
    assert len(messages) == 1


def test_smtp_failure_is_safe_and_does_not_delete_account():
    repo = FakeRepo()
    def fail(_):
        raise RuntimeError("secreto-no-debe-propagarse")
    result = ProviderAccessService(repo, SimpleNamespace(send=fail)).invite(
        PROVIDER, ProviderInvitationRequest(email="service@example.com", request_id=uuid4()))
    assert repo.sent is False and result.envio_estado == "fallido"
    assert "secreto" not in result.model_dump_json()


def test_email_contains_activation_fragment_not_password(monkeypatch):
    messages = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self): pass
        def login(self, *args): pass
        def send_message(self, message): messages.append(message)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "AARI <agency@example.com>")
    monkeypatch.setenv("APP_LOGIN_URL", "https://aari.example.com/login")
    monkeypatch.setattr("app.services.provider_access_service.smtplib.SMTP", SMTP)
    SmtpProviderInvitationSender().send(InvitationDelivery("i", "service@example.com", "Servicio", TOKEN))
    body = messages[0].get_content()
    assert "/activar-proveedor#token=" + TOKEN in body
    assert "Contraseña temporal" not in body


@pytest.fixture
def client():
    class Service:
        def get(self, provider_id):
            return {"proveedor_id": provider_id, "estado": "sin_acceso", "puede_invitar": True}
        def invite(self, provider_id, payload): return self.get(provider_id)
        def activate(self, payload):
            if payload.token != TOKEN:
                raise ProviderAccessError("Invitación vencida.", code="invalid_provider_invitation", status=400)
        def profile(self, user):
            return {"proveedor_id": user.perfil_id, "nombre_razon_social": "Servicio", "email": user.email}
    app.dependency_overrides[get_provider_access_service] = Service
    yield TestClient(app)
    app.dependency_overrides.pop(get_provider_access_service, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_admin_can_manage_invitation_and_responses_are_not_cached(client):
    response = client.post(f"/proveedores/{PROVIDER}/acceso", json={"email": "service@example.com", "request_id": str(uuid4())})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("role", ["proveedor", "inquilino", "propietario", "operador"])
def test_other_roles_cannot_manage_access(client, role):
    app.dependency_overrides.pop(require_admin)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="user@example.com", rol=role, primer_ingreso=False, perfil_id=PROVIDER)
    assert client.get(f"/proveedores/{PROVIDER}/acceso").status_code == 403
    assert client.post(f"/proveedores/{PROVIDER}/acceso", json={"email": "service@example.com", "request_id": str(uuid4())}).status_code == 403


def test_private_provider_profile_and_explicit_integration_pending(client):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), email="service@example.com", rol="proveedor", primer_ingreso=False, perfil_id=PROVIDER)
    result = client.get("/proveedor/perfil")
    assert result.status_code == 200 and result.json()["solicitudes_disponibles"] is False
    assert "HU19" in result.json()["aviso_integracion"]


def test_anonymous_cannot_read_provider_profile(client):
    assert client.get("/proveedor/perfil").status_code == 401


def test_public_activation_and_safe_validation(client):
    payload = {"token": TOKEN, "password_nueva": "Prueba123", "confirmacion_password": "Prueba123"}
    assert client.post("/auth/proveedores/activar", json=payload).status_code == 200
    response = client.post("/auth/proveedores/activar", json={**payload, "confirmacion_password": "otra1234"})
    assert response.status_code == 422
    assert TOKEN not in response.text and "Prueba123" not in response.text


def test_invalid_token_does_not_create_session(client):
    response = client.post("/auth/proveedores/activar", json={
        "token": "z" * 43, "password_nueva": "Prueba123", "confirmacion_password": "Prueba123"})
    assert response.status_code == 400
    assert "set-cookie" not in response.headers
