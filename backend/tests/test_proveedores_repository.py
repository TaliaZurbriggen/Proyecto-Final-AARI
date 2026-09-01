"""Pruebas de persistencia de proveedores con SQLite en memoria."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.proveedores import SqlAlchemyProveedoresRepository
from app.services.proveedores_service import (
    EspecialidadNotFoundError,
    ProveedorDuplicatePhoneError,
)


PLUMBING_ID = UUID("10000000-0000-0000-0000-000000000001")
ELECTRICITY_ID = UUID("10000000-0000-0000-0000-000000000002")


@pytest.fixture
def repository() -> SqlAlchemyProveedoresRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE proveedores (
                    id TEXT PRIMARY KEY,
                    nombre_razon_social TEXT NOT NULL,
                    matricula TEXT,
                    telefono TEXT NOT NULL UNIQUE,
                    activo BOOLEAN NOT NULL DEFAULT true,
                    hora_inicio TEXT,
                    hora_fin TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE especialidades (
                    id TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_especialidades_nombre_normalizado
                ON especialidades (lower(trim(nombre)))
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE proveedor_especialidades (
                    proveedor_id TEXT NOT NULL,
                    especialidad_id TEXT NOT NULL,
                    PRIMARY KEY (proveedor_id, especialidad_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE proveedor_coberturas (
                    id TEXT PRIMARY KEY,
                    proveedor_id TEXT NOT NULL,
                    provincia TEXT NOT NULL,
                    localidad TEXT NOT NULL,
                    cubre_toda_localidad BOOLEAN NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE proveedor_cobertura_barrios (
                    id TEXT PRIMARY KEY,
                    cobertura_id TEXT NOT NULL,
                    barrio TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO especialidades (id, nombre)
                VALUES (:plumbing_id, 'plomería'),
                       (:electricity_id, 'electricidad')
                """
            ),
            {
                "plumbing_id": str(PLUMBING_ID),
                "electricity_id": str(ELECTRICITY_ID),
            },
        )
    return SqlAlchemyProveedoresRepository(
        sessionmaker(bind=engine, expire_on_commit=False)
    )


def provider_data(**changes: object) -> dict[str, object]:
    return {
        "nombre_razon_social": "Servicios del Centro",
        "matricula": "MP 1234",
        "telefono": "+5493564555555",
        "activo": True,
        "hora_inicio": "08:00:00",
        "hora_fin": "17:30:00",
        "especialidad_ids": [str(PLUMBING_ID)],
        "especialidades_personalizadas": ["reparación de bombas"],
        "coberturas": [
            {
                "provincia": "Córdoba",
                "localidad": "San Francisco",
                "cubre_toda_localidad": False,
                "barrios": ["Centro", "La Milka"],
            }
        ],
        **changes,
    }


def test_repository_runs_full_management_flow(
    repository: SqlAlchemyProveedoresRepository,
) -> None:
    created = repository.create(provider_data())
    provider_id = UUID(str(created["id"]))

    items, total = repository.list(
        page=1,
        page_size=10,
        search="3564",
        especialidad_id=PLUMBING_ID,
        provincia="Córdoba",
        localidad="francisco",
        barrio="centro",
        activo=True,
    )
    detail = repository.get_detail(provider_id)
    updated = repository.update(
        provider_id,
        provider_data(
            nombre_razon_social="Servicios Regionales",
            especialidades_personalizadas=[],
            coberturas=[
                {
                    "provincia": "Santa Fe",
                    "localidad": "Rafaela",
                    "cubre_toda_localidad": True,
                    "barrios": [],
                }
            ],
        ),
    )
    deactivated = repository.update_status(provider_id, False)

    assert total == len(items) == 1
    assert detail is not None
    assert {item["nombre"] for item in detail["especialidades"]} == {
        "plomería",
        "reparación de bombas",
    }
    assert detail["coberturas"][0]["barrios"] == ["Centro", "La Milka"]
    assert updated is not None
    assert updated["nombre_razon_social"] == "Servicios Regionales"
    assert updated["coberturas"][0]["localidad"] == "Rafaela"
    assert updated["coberturas"][0]["barrios"] == []
    assert deactivated is not None and bool(deactivated["activo"]) is False


def test_whole_locality_matches_any_neighborhood_filter(
    repository: SqlAlchemyProveedoresRepository,
) -> None:
    repository.create(
        provider_data(
            coberturas=[
                {
                    "provincia": "Córdoba",
                    "localidad": "San Francisco",
                    "cubre_toda_localidad": True,
                    "barrios": [],
                }
            ]
        )
    )

    items, total = repository.list(
        page=1,
        page_size=10,
        search=None,
        especialidad_id=None,
        provincia="Córdoba",
        localidad="San Francisco",
        barrio="Barrio inexistente",
        activo=True,
    )

    assert total == len(items) == 1


def test_repository_reuses_custom_specialty_case_insensitively(
    repository: SqlAlchemyProveedoresRepository,
) -> None:
    repository.create(provider_data(especialidades_personalizadas=["domótica"]))
    repository.create(
        provider_data(
            nombre_razon_social="Segundo proveedor",
            telefono="+5493564555777",
            especialidad_ids=[str(ELECTRICITY_ID)],
            especialidades_personalizadas=["domótica"],
        )
    )

    specialties = repository.list_specialties()

    assert sum(item["nombre"].casefold() == "domótica" for item in specialties) == 1


def test_repository_rejects_duplicate_normalized_phone(
    repository: SqlAlchemyProveedoresRepository,
) -> None:
    repository.create(provider_data())

    with pytest.raises(ProveedorDuplicatePhoneError):
        repository.create(provider_data(nombre_razon_social="Otro proveedor"))


def test_repository_rejects_removed_specialty(
    repository: SqlAlchemyProveedoresRepository,
) -> None:
    with pytest.raises(EspecialidadNotFoundError):
        repository.create(provider_data(especialidad_ids=[str(uuid4())]))


def test_repository_returns_none_for_missing_provider(
    repository: SqlAlchemyProveedoresRepository,
) -> None:
    provider_id = uuid4()

    assert repository.get_detail(provider_id) is None
    assert repository.update(provider_id, provider_data()) is None
    assert repository.update_status(provider_id, False) is None
