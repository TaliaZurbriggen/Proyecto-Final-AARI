"""Contrato HTTP de seguimiento de reclamos sin consultar Supabase."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.auth import require_inquilino
from app.api.reclamos import get_claims_query_service
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.reclamos import (
    ClaimHistoryItem,
    ClaimPropertyContext,
    TenantClaimDetail,
    TenantClaimListItem,
)
from app.services.claims_query_service import TenantClaimsQueryService


USER = AuthenticatedUser(
    id=uuid4(),
    email="lucia@example.com",
    rol="inquilino",
    primer_ingreso=False,
    perfil_id=uuid4(),
)
CLAIM_ID = uuid4()
PROPERTY = ClaimPropertyContext(
    id=uuid4(),
    direccion="Av. San Martín 120",
    provincia="Santa Fe",
    localidad="San Francisco",
    tipo="departamento",
    piso=0,
    numero="B",
)


def claim_summary() -> TenantClaimListItem:
    return TenantClaimListItem(
        id=CLAIM_ID,
        numero=12,
        descripcion="La canilla de la cocina pierde agua desde ayer.",
        urgencia="media",
        estado="Clasificado",
        creado_en=datetime(2026, 9, 10, 13, tzinfo=UTC),
        updated_at=datetime(2026, 9, 10, 14, tzinfo=UTC),
        propiedad=PROPERTY,
    )


class FakeRepository:
    def __init__(self, *, owns_claim: bool = True) -> None:
        self.owns_claim = owns_claim
        self.calls: list[dict[str, UUID]] = []

    def list_for_tenant(self, **data):
        self.calls.append(data)
        return [claim_summary()]

    def get_for_tenant(self, **data):
        self.calls.append(data)
        if not self.owns_claim or data["claim_id"] != CLAIM_ID:
            return None
        return TenantClaimDetail(
            **claim_summary().model_dump(),
            historial=[
                ClaimHistoryItem(
                    estado_anterior=None,
                    estado_nuevo="Recibido",
                    origen="inquilino",
                    timestamp=datetime(2026, 9, 10, 13, tzinfo=UTC),
                ),
                ClaimHistoryItem(
                    estado_anterior="Recibido",
                    estado_nuevo="Clasificado",
                    origen="agente",
                    timestamp=datetime(2026, 9, 10, 14, tzinfo=UTC),
                ),
            ],
        )


def build_client(repository: FakeRepository) -> TestClient:
    app.dependency_overrides[require_inquilino] = lambda: USER
    app.dependency_overrides[get_claims_query_service] = (
        lambda: TenantClaimsQueryService(repository)
    )
    return TestClient(app)


def test_lists_only_the_authenticated_tenant_claims():
    repository = FakeRepository()
    try:
        with build_client(repository) as client:
            response = client.get("/reclamos")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["numero"] == 12
    assert repository.calls == [{"user_id": USER.id, "profile_id": USER.perfil_id}]


def test_returns_status_history_for_an_owned_claim():
    repository = FakeRepository()
    try:
        with build_client(repository) as client:
            response = client.get(f"/reclamos/{CLAIM_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["estado"] == "Clasificado"
    assert [item["estado_nuevo"] for item in response.json()["historial"]] == [
        "Recibido",
        "Clasificado",
    ]


def test_hides_a_claim_that_does_not_belong_to_the_tenant():
    repository = FakeRepository(owns_claim=False)
    try:
        with build_client(repository) as client:
            response = client.get(f"/reclamos/{uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "claim_not_found"
