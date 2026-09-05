"""Contrato HTTP del alta de reclamos con todas las salidas externas simuladas."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.auth import require_inquilino
from app.api.reclamos import (
    get_claim_creation_service,
    get_claim_notification_service,
)
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.reclamos import ClaimCreatedResponse, ClaimPropertyContext
from app.services.claims_creation_service import (
    ActiveClaimExistsError,
    PersistedClaim,
    TenantClaimContext,
)


USER = AuthenticatedUser(
    id=uuid4(),
    email="lucia@example.com",
    rol="inquilino",
    primer_ingreso=False,
    perfil_id=uuid4(),
)
CONTEXT = TenantClaimContext(
    tenant_id=USER.perfil_id,
    tenant_name="Lucía Pérez",
    tenant_email="lucia@example.com",
    property=ClaimPropertyContext(
        id=uuid4(),
        direccion="Av. San Martín 120",
        provincia="Santa Fe",
        localidad="San Francisco",
        tipo="departamento",
        piso=0,
        numero="B",
    ),
)


class FakeCreationService:
    def __init__(self, *, active_claim: bool = False) -> None:
        self.active_claim = active_claim
        self.payload = None
        self.notification_id = uuid4()

    def get_context(self, **data) -> TenantClaimContext:
        assert data == {"user_id": USER.id, "profile_id": USER.perfil_id}
        return CONTEXT

    def create(self, **data) -> PersistedClaim:
        if self.active_claim:
            raise ActiveClaimExistsError
        self.payload = data
        return PersistedClaim(
            response=ClaimCreatedResponse(
                id=uuid4(),
                numero=15,
                estado="Recibido",
                creado_en=datetime(2026, 9, 4, 13, tzinfo=UTC),
                fotos_adjuntas=len(data["photos"]),
            ),
            notification_id=self.notification_id,
        )


class FakeNotificationService:
    def __init__(self) -> None:
        self.delivered = []

    def deliver(self, notification_id):
        self.delivered.append(notification_id)
        return True


def build_client(creation_service, notification_service=None) -> TestClient:
    app.dependency_overrides[require_inquilino] = lambda: USER
    app.dependency_overrides[get_claim_creation_service] = lambda: creation_service
    if notification_service:
        app.dependency_overrides[get_claim_notification_service] = (
            lambda: notification_service
        )
    return TestClient(app)


def test_returns_authenticated_tenant_and_property_context():
    service = FakeCreationService()
    try:
        with build_client(service) as client:
            response = client.get("/reclamos/contexto")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["inquilino_nombre"] == "Lucía Pérez"
    assert response.json()["propiedad"]["numero"] == "B"


def test_creates_claim_with_photo_and_runs_mocked_background_notification():
    creation_service = FakeCreationService()
    notification_service = FakeNotificationService()
    try:
        with build_client(creation_service, notification_service) as client:
            response = client.post(
                "/reclamos",
                data={
                    "descripcion": "La canilla de la cocina pierde agua desde ayer.",
                    "urgencia": "media",
                },
                files={
                    "fotos": (
                        "cocina.png",
                        b"\x89PNG\r\n\x1a\ncontenido",
                        "image/png",
                    )
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["numero"] == 15
    assert response.json()["notificacion_estado"] == "pendiente"
    assert creation_service.payload["description"].startswith("La canilla")
    assert creation_service.payload["photos"][0].filename == "cocina.png"
    assert notification_service.delivered == [creation_service.notification_id]


def test_returns_conflict_for_a_second_active_claim():
    service = FakeCreationService(active_claim=True)
    try:
        with build_client(service, FakeNotificationService()) as client:
            response = client.post(
                "/reclamos",
                data={
                    "descripcion": "La canilla de la cocina pierde agua desde ayer.",
                    "urgencia": "media",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "active_claim_exists"
