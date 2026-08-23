"""Pruebas del contrato HTTP de propietarios sin utilizar Supabase."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.propietarios import get_propietarios_service
from app.main import app
from app.services.propietarios_service import (
    DuplicatePropietarioValueError,
    PropietarioHasPropertiesError,
    PropietariosService,
)


class FakePropietariosRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, dict[str, object]] = {}
        self.blocked_ids: set[UUID] = set()
        self.duplicate_field: str | None = None

    def create(self, data: dict[str, object]) -> dict[str, object]:
        if self.duplicate_field:
            raise DuplicatePropietarioValueError(self.duplicate_field)
        propietario_id = uuid4()
        record = self._record(propietario_id, data)
        self.records[propietario_id] = record
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
            ]
        start = (page - 1) * page_size
        return records[start : start + page_size], len(records)

    def get_detail(self, propietario_id: UUID) -> dict[str, object] | None:
        record = self.records.get(propietario_id)
        return {**record, "propiedades": []} if record else None

    def update(
        self, propietario_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None:
        if self.duplicate_field:
            raise DuplicatePropietarioValueError(self.duplicate_field)
        if propietario_id not in self.records:
            return None
        record = self._record(propietario_id, data)
        self.records[propietario_id] = record
        return record

    def delete(self, propietario_id: UUID) -> bool:
        if propietario_id in self.blocked_ids:
            raise PropietarioHasPropertiesError
        return self.records.pop(propietario_id, None) is not None

    @staticmethod
    def _record(propietario_id: UUID, data: dict[str, object]) -> dict[str, object]:
        timestamp = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        return {
            "id": propietario_id,
            **data,
            "cantidad_inmuebles": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }


@pytest.fixture
def repository() -> FakePropietariosRepository:
    repository = FakePropietariosRepository()
    app.dependency_overrides[get_propietarios_service] = lambda: PropietariosService(
        repository
    )
    yield repository
    app.dependency_overrides.clear()


@pytest.fixture
def client(repository: FakePropietariosRepository) -> TestClient:
    del repository
    return TestClient(app)


def valid_payload(**changes: str) -> dict[str, str]:
    return {
        "nombre_completo": "Ana Martínez",
        "dni": "30123456",
        "email": "ANA.MARTINEZ@EXAMPLE.COM",
        "telefono": "+54 3564 555555",
        **changes,
    }


def test_create_propietario_normalizes_email_and_returns_201(
    client: TestClient,
) -> None:
    response = client.post("/propietarios", json=valid_payload())

    assert response.status_code == 201
    assert response.json()["email"] == "ana.martinez@example.com"
    assert response.json()["cantidad_inmuebles"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [("dni", "123"), ("dni", "30.123.456"), ("email", "correo-invalido")],
)
def test_create_propietario_rejects_invalid_fields(
    client: TestClient, field: str, value: str
) -> None:
    response = client.post("/propietarios", json=valid_payload(**{field: value}))

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["dni", "email"])
def test_create_propietario_reports_duplicate_field(
    client: TestClient,
    repository: FakePropietariosRepository,
    field: str,
) -> None:
    repository.duplicate_field = field

    response = client.post("/propietarios", json=valid_payload())

    assert response.status_code == 409
    assert response.json()["detail"]["field"] == field


def test_list_propietarios_is_paginated_and_searchable(
    client: TestClient, repository: FakePropietariosRepository
) -> None:
    repository.create(valid_payload())
    repository.create(
        valid_payload(
            nombre_completo="Bruno López",
            dni="28987654",
            email="bruno@example.com",
        )
    )

    response = client.get("/propietarios?page=1&page_size=10&search=bruno")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["total_pages"] == 1
    assert response.json()["items"][0]["nombre_completo"] == "Bruno López"


def test_get_propietario_returns_404_when_missing(client: TestClient) -> None:
    response = client.get(f"/propietarios/{uuid4()}")

    assert response.status_code == 404


def test_update_propietario_replaces_contact_data(
    client: TestClient, repository: FakePropietariosRepository
) -> None:
    record = repository.create(valid_payload())

    response = client.put(
        f"/propietarios/{record['id']}",
        json=valid_payload(telefono="+54 9 3564 111111"),
    )

    assert response.status_code == 200
    assert response.json()["telefono"] == "+54 9 3564 111111"


def test_delete_propietario_returns_204(
    client: TestClient, repository: FakePropietariosRepository
) -> None:
    record = repository.create(valid_payload())

    response = client.delete(f"/propietarios/{record['id']}")

    assert response.status_code == 204


def test_delete_propietario_is_blocked_when_it_has_properties(
    client: TestClient, repository: FakePropietariosRepository
) -> None:
    record = repository.create(valid_payload())
    repository.blocked_ids.add(record["id"])

    response = client.delete(f"/propietarios/{record['id']}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "owner_has_properties"
