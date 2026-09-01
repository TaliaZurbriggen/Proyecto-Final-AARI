"""Pruebas del contrato HTTP de proveedores sin utilizar Supabase."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.proveedores import get_proveedores_service
from app.main import app
from app.schemas.proveedores import ProveedorCreate
from app.services.proveedores_service import (
    EspecialidadNotFoundError,
    ProveedorDuplicatePhoneError,
    ProveedoresService,
)


PLUMBING_ID = UUID("10000000-0000-0000-0000-000000000001")
ELECTRICITY_ID = UUID("10000000-0000-0000-0000-000000000002")


class FakeProveedoresRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, dict[str, object]] = {}
        self.duplicate_phone = False
        self.specialties = {
            PLUMBING_ID: "plomería",
            ELECTRICITY_ID: "electricidad",
        }

    def list_specialties(self) -> list[dict[str, object]]:
        return [
            {"id": specialty_id, "nombre": name}
            for specialty_id, name in self.specialties.items()
        ]

    def _validate(self, data: dict[str, object]) -> None:
        if self.duplicate_phone:
            raise ProveedorDuplicatePhoneError
        selected_ids = {UUID(str(value)) for value in data["especialidad_ids"]}
        if not selected_ids.issubset(self.specialties):
            raise EspecialidadNotFoundError

    def _record(
        self, provider_id: UUID, data: dict[str, object]
    ) -> dict[str, object]:
        timestamp = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
        specialties = [
            {"id": UUID(str(specialty_id)), "nombre": self.specialties[UUID(str(specialty_id))]}
            for specialty_id in data["especialidad_ids"]
        ]
        for index, name in enumerate(data["especialidades_personalizadas"]):
            specialties.append(
                {
                    "id": UUID(f"20000000-0000-0000-0000-{index + 1:012d}"),
                    "nombre": name,
                }
            )
        coverages = [
            {"id": uuid4(), **coverage} for coverage in data["coberturas"]
        ]
        return {
            "id": provider_id,
            "nombre_razon_social": data["nombre_razon_social"],
            "matricula": data["matricula"],
            "telefono": data["telefono"],
            "activo": data["activo"],
            "hora_inicio": data["hora_inicio"],
            "hora_fin": data["hora_fin"],
            "especialidades": specialties,
            "coberturas": coverages,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def create(self, data: dict[str, object]) -> dict[str, object]:
        self._validate(data)
        provider_id = uuid4()
        record = self._record(provider_id, data)
        self.records[provider_id] = record
        return record

    def list(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        especialidad_id: UUID | None,
        provincia: str | None,
        localidad: str | None,
        barrio: str | None,
        activo: bool | None,
    ) -> tuple[list[dict[str, object]], int]:
        records = list(self.records.values())
        if search:
            term = search.casefold()
            records = [
                record
                for record in records
                if term in str(record["nombre_razon_social"]).casefold()
                or term in str(record["matricula"] or "").casefold()
                or term in str(record["telefono"])
            ]
        if especialidad_id:
            records = [
                record
                for record in records
                if especialidad_id
                in {specialty["id"] for specialty in record["especialidades"]}
            ]
        if activo is not None:
            records = [record for record in records if record["activo"] is activo]
        if provincia or localidad or barrio:
            filtered: list[dict[str, object]] = []
            for record in records:
                for coverage in record["coberturas"]:
                    province_matches = not provincia or coverage["provincia"] == provincia
                    locality_matches = not localidad or localidad.casefold() in coverage[
                        "localidad"
                    ].casefold()
                    neighborhood_matches = (
                        not barrio
                        or coverage["cubre_toda_localidad"]
                        or any(
                            barrio.casefold() in value.casefold()
                            for value in coverage["barrios"]
                        )
                    )
                    if province_matches and locality_matches and neighborhood_matches:
                        filtered.append(record)
                        break
            records = filtered
        start = (page - 1) * page_size
        return records[start : start + page_size], len(records)

    def get_detail(self, proveedor_id: UUID) -> dict[str, object] | None:
        return self.records.get(proveedor_id)

    def update(
        self, proveedor_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None:
        if proveedor_id not in self.records:
            return None
        self._validate(data)
        record = self._record(proveedor_id, data)
        self.records[proveedor_id] = record
        return record

    def update_status(
        self, proveedor_id: UUID, activo: bool
    ) -> dict[str, object] | None:
        record = self.records.get(proveedor_id)
        if record is None:
            return None
        record["activo"] = activo
        return record


@pytest.fixture
def repository() -> FakeProveedoresRepository:
    repository = FakeProveedoresRepository()
    app.dependency_overrides[get_proveedores_service] = lambda: ProveedoresService(
        repository
    )
    yield repository
    app.dependency_overrides.clear()


@pytest.fixture
def client(repository: FakeProveedoresRepository) -> TestClient:
    del repository
    return TestClient(app)


def valid_payload(**changes: object) -> dict[str, object]:
    return {
        "nombre_razon_social": "  Servicios   del Centro  ",
        "matricula": "  mp 1234 ",
        "telefono": "+54 9 3564 555555",
        "activo": True,
        "hora_inicio": "08:00",
        "hora_fin": "17:30",
        "especialidad_ids": [str(PLUMBING_ID)],
        "especialidades_personalizadas": ["  reparación de bombas  "],
        "coberturas": [
            {
                "provincia": "córdoba",
                "localidad": "  San   Francisco ",
                "cubre_toda_localidad": False,
                "barrios": ["Centro", "  La   Milka  "],
            }
        ],
        **changes,
    }


def validated_payload(**changes: object) -> dict[str, object]:
    return ProveedorCreate.model_validate(valid_payload(**changes)).model_dump(
        mode="json"
    )


def test_create_provider_normalizes_fields_and_returns_201(
    client: TestClient,
) -> None:
    response = client.post("/proveedores", json=valid_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["nombre_razon_social"] == "Servicios del Centro"
    assert body["matricula"] == "MP 1234"
    assert body["telefono"] == "+5493564555555"
    assert body["hora_inicio"] == "08:00:00"
    assert body["especialidades"][1]["nombre"] == "reparación de bombas"
    assert body["coberturas"][0]["provincia"] == "Córdoba"
    assert body["coberturas"][0]["localidad"] == "San Francisco"
    assert body["coberturas"][0]["barrios"] == ["Centro", "La Milka"]


@pytest.mark.parametrize(
    ("change"),
    [
        {"nombre_razon_social": "1234"},
        {"telefono": "3564 555555"},
        {"telefono": "+54 abc"},
        {"especialidad_ids": [], "especialidades_personalizadas": []},
        {"hora_inicio": "08:00", "hora_fin": None},
        {"hora_inicio": "18:00", "hora_fin": "08:00"},
        {
            "coberturas": [
                {
                    "provincia": "Córdoba",
                    "localidad": "444",
                    "cubre_toda_localidad": True,
                    "barrios": [],
                }
            ]
        },
        {
            "coberturas": [
                {
                    "provincia": "Córdoba",
                    "localidad": "San Francisco",
                    "cubre_toda_localidad": False,
                    "barrios": [],
                }
            ]
        },
        {
            "coberturas": [
                {
                    "provincia": "Córdoba",
                    "localidad": "San Francisco",
                    "cubre_toda_localidad": True,
                    "barrios": ["Centro"],
                }
            ]
        },
    ],
)
def test_create_provider_rejects_invalid_business_data(
    client: TestClient, change: dict[str, object]
) -> None:
    response = client.post("/proveedores", json=valid_payload(**change))

    assert response.status_code == 422


def test_create_provider_reports_duplicate_phone(
    client: TestClient, repository: FakeProveedoresRepository
) -> None:
    repository.duplicate_phone = True

    response = client.post("/proveedores", json=valid_payload())

    assert response.status_code == 409
    assert response.json()["detail"]["field"] == "telefono"


def test_create_provider_reports_removed_specialty(client: TestClient) -> None:
    response = client.post(
        "/proveedores",
        json=valid_payload(especialidad_ids=[str(uuid4())]),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "especialidad_ids"


def test_list_specialties(client: TestClient) -> None:
    response = client.get("/especialidades")

    assert response.status_code == 200
    assert [item["nombre"] for item in response.json()] == [
        "plomería",
        "electricidad",
    ]


def test_list_provider_combines_search_and_coverage_filters(
    client: TestClient, repository: FakeProveedoresRepository
) -> None:
    repository.create(validated_payload())
    repository.create(
        validated_payload(
            nombre_razon_social="Electricidad Norte",
            telefono="+5493564555777",
            especialidad_ids=[str(ELECTRICITY_ID)],
            especialidades_personalizadas=[],
            coberturas=[
                {
                    "provincia": "Santa Fe",
                    "localidad": "Rafaela",
                    "cubre_toda_localidad": True,
                    "barrios": [],
                }
            ],
        )
    )

    response = client.get(
        f"/proveedores?search=centro&especialidad_id={PLUMBING_ID}"
        "&provincia=C%C3%B3rdoba&localidad=francisco&barrio=centro&activo=true"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["nombre_razon_social"] == (
        "Servicios del Centro"
    )


def test_get_update_and_status_change_provider(
    client: TestClient, repository: FakeProveedoresRepository
) -> None:
    created = repository.create(validated_payload())
    provider_id = created["id"]

    detail = client.get(f"/proveedores/{provider_id}")
    updated = client.put(
        f"/proveedores/{provider_id}",
        json=valid_payload(nombre_razon_social="Nuevo nombre"),
    )
    deactivated = client.patch(
        f"/proveedores/{provider_id}/estado", json={"activo": False}
    )

    assert detail.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["nombre_razon_social"] == "Nuevo nombre"
    assert deactivated.status_code == 200
    assert deactivated.json()["activo"] is False


def test_missing_provider_returns_404_for_detail_update_and_status(
    client: TestClient,
) -> None:
    provider_id = uuid4()

    assert client.get(f"/proveedores/{provider_id}").status_code == 404
    assert client.put(
        f"/proveedores/{provider_id}", json=valid_payload()
    ).status_code == 404
    assert client.patch(
        f"/proveedores/{provider_id}/estado", json={"activo": False}
    ).status_code == 404
