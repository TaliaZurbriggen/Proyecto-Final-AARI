"""Pruebas de las consultas reales del repositorio con SQLite en memoria."""

from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.propietarios import SqlAlchemyPropietariosRepository
from app.services.propietarios_service import (
    DuplicatePropietarioValueError,
    PropietarioHasPropertiesError,
)


@pytest.fixture
def repository() -> SqlAlchemyPropietariosRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE propietarios (
                    id TEXT PRIMARY KEY,
                    nombre_completo TEXT NOT NULL,
                    dni TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    telefono TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_propietarios_email_normalizado "
                "ON propietarios (lower(email))"
            )
        )
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
                    numero TEXT,
                    propietario_id TEXT NOT NULL REFERENCES propietarios(id)
                )
                """
            )
        )
    return SqlAlchemyPropietariosRepository(
        sessionmaker(bind=engine, expire_on_commit=False)
    )


def owner_data(**changes: str) -> dict[str, object]:
    return {
        "nombre_completo": "Ana Martínez",
        "dni": "30123456",
        "email": "ana@example.com",
        "telefono": "+54 3564 555555",
        **changes,
    }


def test_repository_runs_full_crud_and_pagination(
    repository: SqlAlchemyPropietariosRepository,
) -> None:
    created = repository.create(owner_data())
    propietario_id = UUID(str(created["id"]))

    items, total = repository.list(page=1, page_size=10, search="ana")
    detail = repository.get_detail(propietario_id)
    updated = repository.update(
        propietario_id,
        owner_data(telefono="+54 9 3564 111111"),
    )

    assert total == 1
    assert len(items) == 1
    assert detail is not None and detail["propiedades"] == []
    assert updated is not None and updated["telefono"] == "+54 9 3564 111111"
    assert repository.delete(propietario_id) is True
    assert repository.get_detail(propietario_id) is None


def test_repository_rejects_email_duplicates_ignoring_case(
    repository: SqlAlchemyPropietariosRepository,
) -> None:
    repository.create(owner_data())

    with pytest.raises(DuplicatePropietarioValueError) as error:
        repository.create(
            owner_data(
                dni="28987654",
                email="ANA@EXAMPLE.COM",
            )
        )

    assert error.value.field == "email"


def test_repository_detail_includes_property_location(
    repository: SqlAlchemyPropietariosRepository,
) -> None:
    created = repository.create(owner_data())
    propietario_id = UUID(str(created["id"]))
    with repository.session_factory.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO propiedades
                    (id, direccion, provincia, localidad, barrio, tipo, piso,
                     numero, propietario_id)
                VALUES
                    ('prop-detail', 'Av. Central 123', 'Santa Fe',
                     'San Francisco', 'Centro', 'departamento', 0, 'A', :owner)
                """
            ),
            {"owner": str(propietario_id)},
        )

    detail = repository.get_detail(propietario_id)

    assert detail is not None
    assert detail["propiedades"][0] == {
        "id": "prop-detail",
        "direccion": "Av. Central 123",
        "provincia": "Santa Fe",
        "localidad": "San Francisco",
        "barrio": "Centro",
        "tipo": "departamento",
        "piso": 0,
        "numero": "A",
    }


def test_repository_blocks_deletion_when_property_exists(
    repository: SqlAlchemyPropietariosRepository,
) -> None:
    created = repository.create(owner_data())
    propietario_id = UUID(str(created["id"]))
    with repository.session_factory.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO propiedades
                    (id, direccion, provincia, localidad, barrio, tipo,
                     propietario_id)
                VALUES
                    ('prop-1', 'Av. Central 123', 'Santa Fe', 'San Francisco',
                     'Centro', 'departamento', :owner)
                """
            ),
            {"owner": str(propietario_id)},
        )

    with pytest.raises(PropietarioHasPropertiesError):
        repository.delete(propietario_id)
