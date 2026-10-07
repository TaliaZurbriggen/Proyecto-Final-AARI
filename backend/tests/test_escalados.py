"""HU13: contratos HTTP, permisos, validación y entrada del grafo sin LLM."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.agents.classification.graph import build_manual_classification_graph
from app.api.auth import get_current_user
from app.api.escalados import get_escalated_repository, get_manual_service, get_staff_photo_storage
from app.api.reclamos import get_claim_notification_service
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.escalados import ManualClassificationRequest, ManualClassificationResponse
from app.services.claim_storage import SupabaseClaimPhotoStorage
from app.services.claims_creation_service import ClaimPhotoStorageError
import httpx
from app.services.escalated_claims_service import (
    EscalatedClaimNotFoundError, EscalatedClaimsService, ManualClassificationConflictError,
    PersistedManualClassification, ensure_manual_classification_allowed,
)


CLAIM_ID = uuid4()
VERSION = datetime(2026, 10, 5, 12, tzinfo=UTC)


def payload(expense="ordinario"):
    return {"tipo_gasto": expense, "fundamento": "Decisión sintética basada en el caso.",
            "expected_updated_at": VERSION.isoformat()}


class Repository:
    def __init__(self):
        self.calls = []
        self.failure = None

    def resolve_manual(self, claim_id, result, decision):
        if self.failure:
            raise self.failure
        self.calls.append((claim_id, result, decision))
        return PersistedManualClassification(ManualClassificationResponse(
            reclamo_id=claim_id, estado="Pendiente de respuesta del responsable",
            tipo_gasto=result.tipo_gasto, actor_responsable=result.actor_responsable,
            origen=decision.role, decidido_en=VERSION,
        ), uuid4())

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return {"items": [], "total": 0, "page": kwargs["page"],
                "page_size": kwargs["page_size"], "total_pages": 1}

    def get(self, claim_id):
        raise EscalatedClaimNotFoundError


@pytest.fixture
def api():
    repository = Repository()
    sent = []
    class Notifications:
        def deliver(self, notification_id):
            sent.append(notification_id)
    app.dependency_overrides[get_escalated_repository] = lambda: repository
    app.dependency_overrides[get_manual_service] = lambda: EscalatedClaimsService(
        repository, build_manual_classification_graph())
    app.dependency_overrides[get_claim_notification_service] = Notifications
    def login(role="administrador", first_login=False):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            email="staff@example.com", rol=role, primer_ingreso=first_login,
        )
    login()
    yield TestClient(app), repository, sent, login
    for dependency in (get_current_user, get_escalated_repository, get_manual_service,
                       get_claim_notification_service, get_staff_photo_storage):
        app.dependency_overrides.pop(dependency, None)


@pytest.mark.parametrize("role", ["administrador", "operador"])
@pytest.mark.parametrize("expense,actor", [("ordinario", "inquilino"), ("extraordinario", "propietario"), ("expensa", "inmobiliaria")])
def test_staff_decides_and_graph_continues_without_gemini(api, monkeypatch, role, expense, actor):
    client, repository, sent, login = api
    login(role)
    def forbidden(*args, **kwargs):
        pytest.fail("El recorrido humano no puede consultar Gemini.")
    monkeypatch.setattr("app.agents.classification.nodes.get_gemini_classifier", forbidden)
    result = client.post(f"/reclamos/{CLAIM_ID}/resolver-escalado", json=payload(expense))
    assert result.status_code == 200
    assert result.json()["actor_responsable"] == actor
    assert result.json()["origen"] == role
    assert len(sent) == 1 and len(repository.calls) == 1
    assert repository.calls[0][1].confianza is None
    assert repository.calls[0][1].fundamento == payload()["fundamento"]


@pytest.mark.parametrize("role,first_login", [("inquilino", False), ("propietario", False), ("operador", True)])
@pytest.mark.parametrize("path", ["/reclamos/escalados", f"/reclamos/escalados/{CLAIM_ID}"])
def test_other_roles_cannot_read_the_queue(api, role, first_login, path):
    client, repository, sent, login = api
    login(role, first_login)
    assert client.get(path).status_code == 403
    assert repository.calls == [] and sent == []
    assert client.post(f"/reclamos/{CLAIM_ID}/resolver-escalado", json=payload()).status_code == 403


def test_queue_is_registered_before_tenant_uuid_route(api):
    client, repository, _, _ = api
    result = client.get("/reclamos/escalados?page=2&page_size=5&search=unidad")
    assert result.status_code == 200
    assert repository.calls == [{"page": 2, "page_size": 5, "search": "unidad"}]


@pytest.mark.parametrize("changes", [{"tipo_gasto": "cualquier_cosa"}, {"fundamento": "    "},
    {"fundamento": "x" * 1001}, {"expected_updated_at": "2026-10-05T12:00:00"},
    {"origen": "agente"}, {"usuario_id": str(uuid4())}, {"confianza": 1}])
def test_invalid_or_spoofed_decision_is_rejected_before_saving(api, changes):
    client, repository, sent, _ = api
    assert client.post(f"/reclamos/{CLAIM_ID}/resolver-escalado", json={**payload(), **changes}).status_code == 422
    assert repository.calls == [] and sent == []


@pytest.mark.parametrize("failure,status", [(ManualClassificationConflictError("El caso cambió."), 409), (EscalatedClaimNotFoundError(), 404)])
def test_conflict_or_missing_claim_never_sends_notifications(api, failure, status):
    client, repository, sent, _ = api
    repository.failure = failure
    assert client.post(f"/reclamos/{CLAIM_ID}/resolver-escalado", json=payload()).status_code == status
    assert sent == []


def test_reason_is_normalized_before_length_validation():
    value = ManualClassificationRequest.model_validate({**payload(), "fundamento": "   Texto explicativo.   "})
    assert value.fundamento == "Texto explicativo."
    with pytest.raises(ValidationError):
        ManualClassificationRequest.model_validate({**payload(), "fundamento": "  corto  "})


@pytest.mark.parametrize("state,expense,responsible,origin", [
    ("Autorizado", None, False, "agente"), ("Escalado", "ordinario", False, "agente"),
    ("Escalado", None, True, "agente"), ("Clasificación pendiente", None, False, "operador"),
])
def test_manual_decision_cannot_replace_a_started_management(state, expense, responsible, origin):
    with pytest.raises(ManualClassificationConflictError):
        ensure_manual_classification_allowed(estado=state, tipo_gasto=expense, has_responsible=responsible, origen=origin)


@pytest.mark.parametrize("path", ["/reclamos/escalados", f"/reclamos/escalados/{CLAIM_ID}",
    f"/reclamos/escalados/{CLAIM_ID}/fotos/{uuid4()}", f"/reclamos/{CLAIM_ID}/resolver-escalado"])
def test_missing_session_cannot_access_staff_endpoints(api, path):
    client, repository, sent, _ = api
    app.dependency_overrides.pop(get_current_user)
    result = client.post(path, json=payload()) if path.endswith("resolver-escalado") else client.get(path)
    assert result.status_code == 401
    assert repository.calls == [] and sent == []


def test_photo_bytes_remain_private_and_authorized(api):
    client, repository, _, login = api
    photo_id = uuid4()
    calls = []
    def photo(claim_id, requested_photo):
        calls.append((claim_id, requested_photo))
        return {"url": "synthetic/private/photo.png", "formato": "PNG"}
    repository.photo = photo
    class Storage:
        def download(self, path):
            assert path == "synthetic/private/photo.png"
            return b"synthetic image bytes"
    app.dependency_overrides[get_staff_photo_storage] = Storage
    path = f"/reclamos/escalados/{CLAIM_ID}/fotos/{photo_id}"
    result = client.get(path)
    assert result.status_code == 200 and result.content == b"synthetic image bytes"
    assert result.headers["cache-control"] == "private, no-store"
    assert result.headers["x-content-type-options"] == "nosniff"
    assert result.headers["content-type"] == "image/png"
    assert calls == [(CLAIM_ID, photo_id)]
    login("inquilino")
    assert client.get(path).status_code == 403
    assert len(calls) == 1


@pytest.mark.parametrize("failure,status", [(EscalatedClaimNotFoundError(), 404), (ClaimPhotoStorageError("Foto no disponible."), 503)])
def test_photo_errors_are_readable_without_exposing_private_paths(api, failure, status):
    client, repository, *_ = api
    def photo(*args):
        if isinstance(failure, EscalatedClaimNotFoundError):
            raise failure
        return {"url": "synthetic/private.jpg", "formato": "JPG"}
    repository.photo = photo
    class Storage:
        def download(self, path):
            raise failure
    app.dependency_overrides[get_staff_photo_storage] = Storage
    response = client.get(f"/reclamos/escalados/{CLAIM_ID}/fotos/{uuid4()}")
    assert response.status_code == status
    assert "synthetic/private" not in response.text


def test_private_storage_download_uses_only_server_credentials(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-test-only")
    def get(url, *, headers, timeout):
        assert url == "https://synthetic.example/storage/v1/object/authenticated/reclamos-fotos/private/photo%20one.jpg"
        assert headers["Authorization"] == "Bearer synthetic-test-only" and timeout == 10
        return httpx.Response(200, content=b"test image", request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    storage = SupabaseClaimPhotoStorage()
    assert storage.download("private/photo one.jpg") == b"test image"
    def fail(*args, **kwargs):
        raise httpx.ConnectError("synthetic failure")
    monkeypatch.setattr(httpx, "get", fail)
    with pytest.raises(ClaimPhotoStorageError, match="No se pudo recuperar"):
        storage.download("private/photo.jpg")
