"""Pruebas del contrato HTTP de propiedades sin utilizar Supabase."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.propiedades import get_propiedades_service
from app.main import app
from app.services.propiedades_service import (
    DuplicatePropertyAddressError,
    PropertyHasActiveTenantError,
    PropertyHasClaimsError,
    PropietarioNotFoundError,
    PropiedadesService,
)


class FakePropiedadesRepository:
    def __init__(self, owner_id: UUID) -> None:
        self.owner_id = owner_id
        self.records: dict[UUID, dict[str, object]] = {}
        self.duplicate = False
        self.claims_blocked_ids: set[UUID] = set()
        self.tenant_blocked_ids: set[UUID] = set()

    def create(self, data: dict[str, object]) -> dict[str, object]:
        self._validate(data)
        propiedad_id = uuid4()
        record = self._record(propiedad_id, data)
        self.records[propiedad_id] = record
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
                if term in str(record["direccion"]).lower()
                or term in str(record["provincia"]).lower()
                or term in str(record["localidad"]).lower()
                or term in str(record["barrio"] or "").lower()
                or term in str(record["propietario"]["nombre_completo"]).lower()
            ]
        start = (page - 1) * page_size
        return records[start : start + page_size], len(records)

    def get_detail(self, propiedad_id: UUID) -> dict[str, object] | None:
        return self.records.get(propiedad_id)

    def update(
        self, propiedad_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None:
        if propiedad_id not in self.records:
            return None
        self._validate(data)
        record = self._record(propiedad_id, data)
        self.records[propiedad_id] = record
        return record

    def delete(self, propiedad_id: UUID) -> bool:
        if propiedad_id in self.claims_blocked_ids:
            raise PropertyHasClaimsError
        if propiedad_id in self.tenant_blocked_ids:
            raise PropertyHasActiveTenantError
        return self.records.pop(propiedad_id, None) is not None

    def _validate(self, data: dict[str, object]) -> None:
        if self.duplicate:
            raise DuplicatePropertyAddressError
        if str(data["propietario_id"]) != str(self.owner_id):
            raise PropietarioNotFoundError

    def _record(
        self, propiedad_id: UUID, data: dict[str, object]
    ) -> dict[str, object]:
        timestamp = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        return {
            "id": propiedad_id,
            "direccion": data["direccion"],
            "provincia": data["provincia"],
            "localidad": data["localidad"],
            "barrio": data["barrio"],
            "tipo": data["tipo"],
            "piso": data["piso"],
            "numero": data["numero"],
            "propietario": {
                "id": self.owner_id,
                "nombre_completo": "Ana Martínez",
            },
            "cantidad_reclamos": 0,
            "tiene_inquilino_activo": False,
            "created_at": timestamp,
            "updated_at": timestamp,
        }


@pytest.fixture
def owner_id() -> UUID:
    return uuid4()


@pytest.fixture
def repository(owner_id: UUID) -> FakePropiedadesRepository:
    repository = FakePropiedadesRepository(owner_id)
    app.dependency_overrides[get_propiedades_service] = lambda: PropiedadesService(
        repository
    )
    yield repository
    app.dependency_overrides.clear()


@pytest.fixture
def client(repository: FakePropiedadesRepository) -> TestClient:
    del repository
    return TestClient(app)


def valid_payload(owner_id: UUID, **changes: object) -> dict[str, object]:
    return {
        "direccion": "  Av. San Martín   120  ",
        "provincia": "Santa Fe",
        "localidad": "  San   Francisco  ",
        "barrio": "  Centro  ",
        "tipo": "departamento",
        "piso": 0,
        "numero": " B ",
        "propietario_id": str(owner_id),
        **changes,
    }


def test_create_propiedad_normalizes_text_and_returns_201(
    client: TestClient, owner_id: UUID
) -> None:
    response = client.post(
        "/propiedades",
        json=valid_payload(owner_id, provincia="  santa fe  "),
    )

    assert response.status_code == 201
    assert response.json()["direccion"] == "Av. San Martín 120"
    assert response.json()["provincia"] == "Santa Fe"
    assert response.json()["localidad"] == "San Francisco"
    assert response.json()["barrio"] == "Centro"
    assert response.json()["piso"] == 0
    assert response.json()["propietario"]["id"] == str(owner_id)


def test_non_apartment_discards_floor_and_unit(
    client: TestClient, owner_id: UUID
) -> None:
    response = client.post(
        "/propiedades",
        json=valid_payload(owner_id, tipo="casa", piso=2, numero="B"),
    )

    assert response.status_code == 201
    assert response.json()["piso"] is None
    assert response.json()["numero"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("direccion", " "),
        ("direccion", "444"),
        ("provincia", "Atlantis"),
        ("localidad", "x"),
        ("localidad", "444"),
        ("barrio", "x"),
        ("barrio", "444"),
        ("piso", "PB"),
        ("tipo", "galpón"),
        ("propietario_id", "no-es-un-uuid"),
    ],
)
def test_create_propiedad_rejects_invalid_fields(
    client: TestClient, owner_id: UUID, field: str, value: str
) -> None:
    response = client.post(
        "/propiedades", json=valid_payload(owner_id, **{field: value})
    )

    assert response.status_code == 422


def test_create_propiedad_accepts_location_names_with_numbers(
    client: TestClient, owner_id: UUID
) -> None:
    response = client.post(
        "/propiedades",
        json=valid_payload(
            owner_id,
            direccion="Ruta 9 km 72",
            localidad="9 de Julio",
            barrio="Barrio 300 Viviendas",
        ),
    )

    assert response.status_code == 201
    assert response.json()["direccion"] == "Ruta 9 km 72"
    assert response.json()["localidad"] == "9 de Julio"
    assert response.json()["barrio"] == "Barrio 300 Viviendas"


def test_create_propiedad_reports_duplicate_address(
    client: TestClient,
    repository: FakePropiedadesRepository,
    owner_id: UUID,
) -> None:
    repository.duplicate = True

    response = client.post("/propiedades", json=valid_payload(owner_id))

    assert response.status_code == 409
    assert response.json()["detail"]["field"] == "direccion"


def test_create_propiedad_reports_missing_owner(
    client: TestClient, owner_id: UUID
) -> None:
    response = client.post(
        "/propiedades",
        json=valid_payload(owner_id, propietario_id=str(uuid4())),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "propietario_id"


def test_list_propiedades_is_paginated_and_searchable(
    client: TestClient,
    repository: FakePropiedadesRepository,
    owner_id: UUID,
) -> None:
    repository.create(valid_payload(owner_id))
    repository.create(
        valid_payload(
            owner_id,
            direccion="Belgrano 450",
            barrio=None,
            tipo="local",
            piso=None,
            numero=None,
        )
    )

    response = client.get("/propiedades?page=1&page_size=10&search=belgrano")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["direccion"] == "Belgrano 450"


def test_list_propiedades_searches_by_location_and_owner(
    client: TestClient,
    repository: FakePropiedadesRepository,
    owner_id: UUID,
) -> None:
    repository.create(valid_payload(owner_id))

    by_neighborhood = client.get(
        "/propiedades?page=1&page_size=10&search=centro"
    )
    by_owner = client.get(
        "/propiedades?page=1&page_size=10&search=ana"
    )

    assert by_neighborhood.json()["total"] == 1
    assert by_owner.json()["total"] == 1


def test_get_propiedad_returns_404_when_missing(client: TestClient) -> None:
    response = client.get(f"/propiedades/{uuid4()}")

    assert response.status_code == 404


def test_update_propiedad_replaces_data(
    client: TestClient,
    repository: FakePropiedadesRepository,
    owner_id: UUID,
) -> None:
    record = repository.create(valid_payload(owner_id))

    response = client.put(
        f"/propiedades/{record['id']}",
        json=valid_payload(owner_id, barrio="Nueva Córdoba"),
    )

    assert response.status_code == 200
    assert response.json()["barrio"] == "Nueva Córdoba"


def test_delete_propiedad_returns_204(
    client: TestClient,
    repository: FakePropiedadesRepository,
    owner_id: UUID,
) -> None:
    record = repository.create(valid_payload(owner_id))

    response = client.delete(f"/propiedades/{record['id']}")

    assert response.status_code == 204


@pytest.mark.parametrize(
    ("blocked_set", "expected_code"),
    [
        ("claims_blocked_ids", "property_has_claims"),
        ("tenant_blocked_ids", "property_has_active_tenant"),
    ],
)
def test_delete_propiedad_preserves_related_history(
    client: TestClient,
    repository: FakePropiedadesRepository,
    owner_id: UUID,
    blocked_set: str,
    expected_code: str,
) -> None:
    record = repository.create(valid_payload(owner_id))
    getattr(repository, blocked_set).add(record["id"])

    response = client.delete(f"/propiedades/{record['id']}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == expected_code
