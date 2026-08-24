"""Pruebas de las consultas de inquilinos con SQLite en memoria."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.inquilinos import SqlAlchemyInquilinosRepository
from app.services.inquilinos_service import (
    InquilinoDuplicateDniError,
    InquilinoDuplicateEmailError,
    InquilinoHasClaimsError,
    InquilinoPropertyNotFoundError,
    InquilinoPropertyOccupiedError,
)


@pytest.fixture
def repository() -> SqlAlchemyInquilinosRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE propiedades (
                    id TEXT PRIMARY KEY,
                    direccion TEXT NOT NULL,
                    provincia TEXT NOT NULL,
                    localidad TEXT NOT NULL,
                    barrio TEXT,
                    tipo TEXT NOT NULL,
                    piso INTEGER,
                    numero TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE inquilinos (
                    id TEXT PRIMARY KEY,
                    nombre_completo TEXT NOT NULL,
                    dni TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    telefono TEXT NOT NULL,
                    propiedad_id TEXT,
                    estado TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_inquilinos_email_normalizado
                ON inquilinos (lower(email))
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_inquilinos_propiedad_activa
                ON inquilinos (propiedad_id)
                WHERE estado = 'activo'
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE reclamos (
                    id TEXT PRIMARY KEY,
                    inquilino_id TEXT NOT NULL
                )
                """
            )
        )
    return SqlAlchemyInquilinosRepository(
        sessionmaker(bind=engine, expire_on_commit=False)
    )


@pytest.fixture
def property_ids(repository: SqlAlchemyInquilinosRepository) -> tuple[UUID, UUID]:
    first, second = uuid4(), uuid4()
    with repository.session_factory.begin() as session:
        for property_id, address in ((first, "San Martín 120"), (second, "Belgrano 450")):
            session.execute(
                text(
                    """
                    INSERT INTO propiedades
                        (id, direccion, provincia, localidad, barrio, tipo, piso, numero)
                    VALUES
                        (:id, :direccion, 'Santa Fe', 'San Francisco', 'Centro',
                         'departamento', 0, 'B')
                    """
                ),
                {"id": str(property_id), "direccion": address},
            )
    return first, second


def tenant_data(property_id: UUID | None, **changes: object) -> dict[str, object]:
    return {
        "nombre_completo": "Lucía Pérez",
        "dni": "30123456",
        "email": "lucia@example.com",
        "telefono": "+54 9 3564 555555",
        "propiedad_id": str(property_id) if property_id else None,
        **changes,
    }


def test_repository_runs_full_crud_and_property_lookup(
    repository: SqlAlchemyInquilinosRepository,
    property_ids: tuple[UUID, UUID],
) -> None:
    first_property, second_property = property_ids
    created = repository.create(tenant_data(first_property))
    tenant_id = UUID(str(created["id"]))

    items, total = repository.list(page=1, page_size=10, search="lucía")
    by_property = repository.get_active_by_property(first_property)
    updated = repository.update(tenant_id, tenant_data(second_property))
    disassociated = repository.disassociate(tenant_id)

    assert len(items) == total == 1
    assert by_property is not None and by_property["id"] == created["id"]
    assert updated is not None
    assert str(updated["propiedad"]["id"]) == str(second_property)
    assert repository.get_active_by_property(first_property) is None
    assert disassociated is not None
    assert disassociated["estado"] == "sin_propiedad_asignada"
    assert disassociated["propiedad"] is None
    assert repository.delete(tenant_id) is True
    assert repository.get_detail(tenant_id) is None


def test_repository_rejects_missing_or_occupied_property(
    repository: SqlAlchemyInquilinosRepository,
    property_ids: tuple[UUID, UUID],
) -> None:
    first_property, _ = property_ids
    repository.create(tenant_data(first_property))

    with pytest.raises(InquilinoPropertyOccupiedError):
        repository.create(
            tenant_data(
                first_property,
                dni="32123456",
                email="otra@example.com",
            )
        )
    with pytest.raises(InquilinoPropertyNotFoundError):
        repository.create(
            tenant_data(uuid4(), dni="33123456", email="tercera@example.com")
        )


def test_repository_rejects_duplicate_dni_and_normalized_email(
    repository: SqlAlchemyInquilinosRepository,
    property_ids: tuple[UUID, UUID],
) -> None:
    first_property, second_property = property_ids
    repository.create(tenant_data(first_property))

    with pytest.raises(InquilinoDuplicateDniError):
        repository.create(
            tenant_data(second_property, email="otra@example.com")
        )
    with pytest.raises(InquilinoDuplicateEmailError):
        repository.create(
            tenant_data(
                second_property,
                dni="32123456",
                email="LUCIA@EXAMPLE.COM",
            )
        )


def test_repository_preserves_tenant_with_claims(
    repository: SqlAlchemyInquilinosRepository,
    property_ids: tuple[UUID, UUID],
) -> None:
    first_property, _ = property_ids
    created = repository.create(tenant_data(first_property))
    with repository.session_factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO reclamos (id, inquilino_id) "
                "VALUES ('claim-1', :inquilino_id)"
            ),
            {"inquilino_id": str(created["id"])},
        )

    with pytest.raises(InquilinoHasClaimsError):
        repository.delete(UUID(str(created["id"])))
