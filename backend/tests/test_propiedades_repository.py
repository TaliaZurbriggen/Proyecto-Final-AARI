"""Pruebas de las consultas de propiedades con SQLite en memoria."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.propiedades import SqlAlchemyPropiedadesRepository
from app.services.propiedades_service import (
    DuplicatePropertyAddressError,
    PropertyHasActiveTenantError,
    PropertyHasClaimsError,
    PropietarioNotFoundError,
)


@pytest.fixture
def repository() -> SqlAlchemyPropiedadesRepository:
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
                    nombre_completo TEXT NOT NULL
                )
                """
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
                    propietario_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_propiedades_direccion_depto_normalizada
                ON propiedades (
                    lower(trim(provincia)),
                    lower(trim(localidad)),
                    lower(trim(direccion)),
                    COALESCE(piso, -2147483648),
                    lower(COALESCE(trim(numero), ''))
                )
                WHERE tipo = 'departamento'
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_propiedades_direccion_no_depto_normalizada
                ON propiedades (
                    lower(trim(provincia)),
                    lower(trim(localidad)),
                    lower(trim(direccion))
                )
                WHERE tipo <> 'departamento'
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE reclamos (
                    id TEXT PRIMARY KEY,
                    propiedad_id TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE inquilinos (
                    id TEXT PRIMARY KEY,
                    propiedad_id TEXT,
                    estado TEXT NOT NULL
                )
                """
            )
        )
    return SqlAlchemyPropiedadesRepository(
        sessionmaker(bind=engine, expire_on_commit=False)
    )


@pytest.fixture
def owner_id(repository: SqlAlchemyPropiedadesRepository) -> UUID:
    owner_id = uuid4()
    with repository.session_factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO propietarios (id, nombre_completo) "
                "VALUES (:id, 'Ana Martínez')"
            ),
            {"id": str(owner_id)},
        )
    return owner_id


def property_data(owner_id: UUID, **changes: object) -> dict[str, object]:
    return {
        "direccion": "Av. San Martín 120",
        "provincia": "Santa Fe",
        "localidad": "San Francisco",
        "barrio": "Centro",
        "tipo": "departamento",
        "piso": 0,
        "numero": "B",
        "propietario_id": str(owner_id),
        **changes,
    }


def test_repository_runs_full_crud_search_and_pagination(
    repository: SqlAlchemyPropiedadesRepository, owner_id: UUID
) -> None:
    created = repository.create(property_data(owner_id))
    propiedad_id = UUID(str(created["id"]))

    items, total = repository.list(page=1, page_size=10, search="martín")
    detail = repository.get_detail(propiedad_id)
    updated = repository.update(
        propiedad_id, property_data(owner_id, barrio="Zona Norte")
    )

    assert total == 1
    assert len(items) == 1
    assert detail is not None
    assert detail["propietario"]["nombre_completo"] == "Ana Martínez"
    assert updated is not None and updated["barrio"] == "Zona Norte"
    assert repository.delete(propiedad_id) is True
    assert repository.get_detail(propiedad_id) is None


def test_repository_rejects_normalized_duplicate_address(
    repository: SqlAlchemyPropiedadesRepository, owner_id: UUID
) -> None:
    repository.create(
        property_data(owner_id, tipo="casa", piso=None, numero=None)
    )

    with pytest.raises(DuplicatePropertyAddressError):
        repository.create(
            property_data(
                owner_id,
                # SQLite solo aplica lower() a ASCII; PostgreSQL también
                # normaliza la Í. Conservamos el acento en minúscula para que
                # esta prueba portátil mida mayúsculas y espacios.
                direccion="  AV. SAN martín 120  ",
                tipo="casa",
                piso=None,
                numero=None,
            )
        )


def test_repository_allows_apartments_with_different_units(
    repository: SqlAlchemyPropiedadesRepository, owner_id: UUID
) -> None:
    repository.create(property_data(owner_id, piso=2, numero="B"))

    second = repository.create(property_data(owner_id, piso=2, numero="C"))

    assert second["numero"] == "C"


def test_repository_allows_same_address_in_different_cities(
    repository: SqlAlchemyPropiedadesRepository, owner_id: UUID
) -> None:
    repository.create(
        property_data(owner_id, tipo="casa", piso=None, numero=None)
    )

    second = repository.create(
        property_data(
            owner_id,
            localidad="Córdoba",
            tipo="casa",
            piso=None,
            numero=None,
        )
    )

    assert second["localidad"] == "Córdoba"


def test_repository_searches_location_and_owner(
    repository: SqlAlchemyPropiedadesRepository, owner_id: UUID
) -> None:
    repository.create(property_data(owner_id))

    by_city, city_total = repository.list(
        page=1, page_size=10, search="francisco"
    )
    by_neighborhood, neighborhood_total = repository.list(
        page=1, page_size=10, search="centro"
    )
    by_owner, owner_total = repository.list(
        page=1, page_size=10, search="ana"
    )

    assert len(by_city) == city_total == 1
    assert len(by_neighborhood) == neighborhood_total == 1
    assert len(by_owner) == owner_total == 1


def test_repository_rejects_missing_owner(
    repository: SqlAlchemyPropiedadesRepository,
) -> None:
    with pytest.raises(PropietarioNotFoundError):
        repository.create(property_data(uuid4()))


def test_repository_blocks_deletion_when_claim_exists(
    repository: SqlAlchemyPropiedadesRepository, owner_id: UUID
) -> None:
    created = repository.create(property_data(owner_id))
    with repository.session_factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO reclamos (id, propiedad_id) VALUES ('claim-1', :property)"
            ),
            {"property": str(created["id"])},
        )

    with pytest.raises(PropertyHasClaimsError):
        repository.delete(UUID(str(created["id"])))


def test_repository_blocks_deletion_when_active_tenant_exists(
    repository: SqlAlchemyPropiedadesRepository, owner_id: UUID
) -> None:
    created = repository.create(property_data(owner_id))
    with repository.session_factory.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO inquilinos (id, propiedad_id, estado)
                VALUES ('tenant-1', :property, 'activo')
                """
            ),
            {"property": str(created["id"])},
        )

    with pytest.raises(PropertyHasActiveTenantError):
        repository.delete(UUID(str(created["id"])))
