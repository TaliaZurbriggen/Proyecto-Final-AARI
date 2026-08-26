"""Pruebas del contrato HTTP de inquilinos sin utilizar Supabase."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.inquilinos import get_inquilinos_service
from app.main import app
from app.services.inquilinos_service import (
    InquilinoDuplicateDniError,
    InquilinoDuplicateEmailError,
    InquilinoHasClaimsError,
    InquilinoPropertyNotFoundError,
    InquilinoPropertyOccupiedError,
    InquilinosService,
)


class FakeInquilinosRepository:
    def __init__(self, property_id: UUID) -> None:
        self.properties = {property_id: self._property(property_id)}
        self.records: dict[UUID, dict[str, object]] = {}
        self.duplicate_dni = False
        self.duplicate_email = False
        self.claims_blocked_ids: set[UUID] = set()

    @staticmethod
    def _property(property_id: UUID) -> dict[str, object]:
        return {
            "id": property_id,
            "direccion": "Av. San Martín 120",
            "provincia": "Santa Fe",
            "localidad": "San Francisco",
            "barrio": "Centro",
            "tipo": "departamento",
            "piso": 0,
            "numero": "B",
        }

    def _validate_property(
        self, property_id: object | None, excluding: UUID | None = None
    ) -> None:
        if property_id is None:
            return
        parsed = UUID(str(property_id))
        if parsed not in self.properties:
            raise InquilinoPropertyNotFoundError
        if any(
            record["propiedad"]
            and record["propiedad"]["id"] == parsed
            and record["estado"] == "activo"
            and tenant_id != excluding
            for tenant_id, record in self.records.items()
        ):
            raise InquilinoPropertyOccupiedError

    def _validate_unique(self) -> None:
        if self.duplicate_dni:
            raise InquilinoDuplicateDniError
        if self.duplicate_email:
            raise InquilinoDuplicateEmailError

    def _record(
        self, tenant_id: UUID, data: dict[str, object]
    ) -> dict[str, object]:
        timestamp = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        property_id = data.get("propiedad_id")
        parsed_property_id = UUID(str(property_id)) if property_id else None
        return {
            "id": tenant_id,
            "nombre_completo": data["nombre_completo"],
            "dni": data["dni"],
            "email": data["email"],
            "telefono": data["telefono"],
            "propiedad": (
                self.properties[parsed_property_id] if parsed_property_id else None
            ),
            "estado": "activo" if parsed_property_id else "sin_propiedad_asignada",
            "cantidad_reclamos": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def create(self, data: dict[str, object]) -> dict[str, object]:
        self._validate_unique()
        self._validate_property(data["propiedad_id"])
        tenant_id = uuid4()
        record = self._record(tenant_id, data)
        self.records[tenant_id] = record
        return record

    def list(
        self, *, page: int, page_size: int, search: str | None
    ) -> tuple[list[dict[str, object]], int]:
        records = list(self.records.values())
        if search:
            term = search.lower()
            records = [
                record
                for record in records
                if term in str(record["nombre_completo"]).lower()
                or term in str(record["dni"])
                or term in str(record["email"]).lower()
                or term
                in str((record["propiedad"] or {}).get("direccion", "")).lower()
            ]
        start = (page - 1) * page_size
        return records[start : start + page_size], len(records)

    def get_detail(self, inquilino_id: UUID) -> dict[str, object] | None:
        return self.records.get(inquilino_id)

    def property_exists(self, propiedad_id: UUID) -> bool:
        return propiedad_id in self.properties

    def get_active_by_property(
        self, propiedad_id: UUID
    ) -> dict[str, object] | None:
        return next(
            (
                record
                for record in self.records.values()
                if record["propiedad"]
                and record["propiedad"]["id"] == propiedad_id
                and record["estado"] == "activo"
            ),
            None,
        )

    def update(
        self, inquilino_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None:
        if inquilino_id not in self.records:
            return None
        self._validate_unique()
        self._validate_property(data.get("propiedad_id"), excluding=inquilino_id)
        record = self._record(inquilino_id, data)
        self.records[inquilino_id] = record
        return record

    def disassociate(self, inquilino_id: UUID) -> dict[str, object] | None:
        current = self.records.get(inquilino_id)
        if current is None:
            return None
        data = {**current, "propiedad_id": None}
        record = self._record(inquilino_id, data)
        self.records[inquilino_id] = record
        return record

    def delete(self, inquilino_id: UUID) -> bool:
        if inquilino_id in self.claims_blocked_ids:
            raise InquilinoHasClaimsError
        return self.records.pop(inquilino_id, None) is not None


@pytest.fixture
def property_id() -> UUID:
    return uuid4()


@pytest.fixture
def repository(property_id: UUID) -> FakeInquilinosRepository:
    repository = FakeInquilinosRepository(property_id)
    app.dependency_overrides[get_inquilinos_service] = lambda: InquilinosService(
        repository
    )
    yield repository
    app.dependency_overrides.clear()


@pytest.fixture
def client(repository: FakeInquilinosRepository) -> TestClient:
    del repository
    return TestClient(app)


def valid_payload(property_id: UUID, **changes: object) -> dict[str, object]:
    return {
        "nombre_completo": "  Lucía   Pérez  ",
        "dni": "30123456",
        "email": "LUCIA@EXAMPLE.COM",
        "telefono": "  +54 9 3564 555555  ",
        "propiedad_id": str(property_id),
        **changes,
    }


def test_create_tenant_normalizes_and_associates_property(
    client: TestClient, property_id: UUID
) -> None:
    response = client.post("/inquilinos", json=valid_payload(property_id))

    assert response.status_code == 201
    assert response.json()["nombre_completo"] == "Lucía Pérez"
    assert response.json()["email"] == "lucia@example.com"
    assert response.json()["propiedad"]["id"] == str(property_id)
    assert response.json()["estado"] == "activo"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("nombre_completo", "x"),
        ("nombre_completo", "43428013"),
        ("nombre_completo", "Juan123"),
        ("dni", "30.123.456"),
        ("dni", "123456"),
        ("email", "email-invalido"),
        ("telefono", "123"),
        ("propiedad_id", "no-es-un-uuid"),
    ],
)
def test_create_tenant_rejects_invalid_fields(
    client: TestClient,
    property_id: UUID,
    field: str,
    value: str,
) -> None:
    response = client.post(
        "/inquilinos", json=valid_payload(property_id, **{field: value})
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("flag", "field"),
    [
        ("duplicate_dni", "dni"),
        ("duplicate_email", "email"),
    ],
)
def test_create_tenant_reports_duplicate_identity(
    client: TestClient,
    repository: FakeInquilinosRepository,
    property_id: UUID,
    flag: str,
    field: str,
) -> None:
    setattr(repository, flag, True)

    response = client.post("/inquilinos", json=valid_payload(property_id))

    assert response.status_code == 409
    assert response.json()["detail"]["field"] == field


def test_create_tenant_requires_existing_available_property(
    client: TestClient,
    repository: FakeInquilinosRepository,
    property_id: UUID,
) -> None:
    repository.create(valid_payload(property_id))

    occupied = client.post(
        "/inquilinos",
        json=valid_payload(
            property_id,
            dni="32123456",
            email="otra@example.com",
        ),
    )
    missing = client.post(
        "/inquilinos",
        json=valid_payload(uuid4(), dni="33123456", email="tercera@example.com"),
    )

    assert occupied.status_code == 409
    assert occupied.json()["detail"]["field"] == "propiedad_id"
    assert missing.status_code == 422
    assert missing.json()["detail"]["field"] == "propiedad_id"


def test_full_flow_lists_edits_disassociates_and_frees_property(
    client: TestClient,
    repository: FakeInquilinosRepository,
    property_id: UUID,
) -> None:
    created = client.post("/inquilinos", json=valid_payload(property_id)).json()
    tenant_id = created["id"]

    listing = client.get("/inquilinos?search=lucía")
    by_property = client.get(f"/propiedades/{property_id}/inquilino")
    updated = client.put(
        f"/inquilinos/{tenant_id}",
        json=valid_payload(property_id, telefono="+54 9 3564 444444"),
    )
    disassociated = client.patch(f"/inquilinos/{tenant_id}/desasociar")
    property_without_tenant = client.get(f"/propiedades/{property_id}/inquilino")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert by_property.json()["id"] == tenant_id
    assert updated.json()["telefono"] == "+54 9 3564 444444"
    assert disassociated.json()["propiedad"] is None
    assert disassociated.json()["estado"] == "sin_propiedad_asignada"
    assert property_without_tenant.json() is None
    assert repository.get_active_by_property(property_id) is None


def test_property_tenant_returns_404_for_missing_property(client: TestClient) -> None:
    response = client.get(f"/propiedades/{uuid4()}/inquilino")

    assert response.status_code == 404


def test_delete_tenant_preserves_claim_history(
    client: TestClient,
    repository: FakeInquilinosRepository,
    property_id: UUID,
) -> None:
    created = repository.create(valid_payload(property_id))
    repository.claims_blocked_ids.add(created["id"])

    response = client.delete(f"/inquilinos/{created['id']}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "tenant_has_claims"


def test_delete_tenant_without_claims_returns_204(
    client: TestClient,
    repository: FakeInquilinosRepository,
    property_id: UUID,
) -> None:
    created = repository.create(valid_payload(property_id))

    response = client.delete(f"/inquilinos/{created['id']}")

    assert response.status_code == 204
