"""Filtros y totales paginados contra PostgreSQL local y migraciones reales."""

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.inquilinos import SqlAlchemyInquilinosRepository
from app.db.propiedades import SqlAlchemyPropiedadesRepository
from app.db.propietarios import SqlAlchemyPropietariosRepository
from app.schemas.list_filters import PropertiesListFilters, OwnersListFilters, TenantsListFilters
from tests.test_responsible_actor_postgres import local_engine


pytestmark = pytest.mark.skipif(
    not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Requiere PostgreSQL local dedicado.",
)


def test_filters_and_pagination_on_real_postgres_enums(local_engine):
    # El fixture de reclamos no necesita las entregas de credenciales de HU6;
    # estos listados sí. Completamos ese esquema antes de cargar datos ficticios.
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with local_engine.connect() as connection:
        cursor = connection.connection.cursor()
        try:
            for number in (13, 14):
                cursor.execute(next(migrations.glob(f"{number:02d}_*.sql")).read_text(encoding="utf-8"))
            connection.commit()
        finally:
            cursor.close()
    factory = sessionmaker(bind=local_engine)
    properties = SqlAlchemyPropiedadesRepository(factory)
    owners = SqlAlchemyPropietariosRepository(factory)
    tenants = SqlAlchemyInquilinosRepository(factory)
    with local_engine.begin() as connection:
        owner_ids = []
        for n, name in enumerate(("Ana Sintetica", "Bruno Sintetico", "Carla Sintetica"), 1):
            owner_ids.append(connection.execute(text("""
                INSERT INTO propietarios (nombre_completo, dni, email, telefono)
                VALUES (:name, :dni, :email, '00000000') RETURNING id
            """), {"name": name, "dni": str(10000000 + n),
                   "email": f"owner{n}@example.com"}).scalar_one())
        property_ids = []
        for n, (province, city, kind, owner_index) in enumerate((
            ("Córdoba", "San Francisco", "departamento", 0),
            ("Córdoba", "San Francisco", "departamento", 0),
            ("Santa Fe", "San Francisco", "casa", 1),
            ("Córdoba", "Otra Localidad", "casa", 1),
        ), 1):
            property_ids.append(connection.execute(text("""
                INSERT INTO propiedades (direccion, provincia, localidad, barrio, tipo, propietario_id)
                VALUES (:address, :province, :city, 'Centro', :kind, :owner) RETURNING id
            """), {"address": f"Calle Ficticia {n}", "province": province,
                   "city": city, "kind": kind, "owner": owner_ids[owner_index]}).scalar_one())
        for n, property_id in enumerate((property_ids[0], property_ids[2], None), 1):
            connection.execute(text("""
                INSERT INTO inquilinos (nombre_completo, dni, email, telefono, propiedad_id, estado)
                VALUES ('Persona Sintetica', :dni, :email, '00000000', :property, :state)
            """), {"dni": str(20000000 + n), "email": f"tenant{n}@example.com",
                   "property": property_id, "state": "activo" if property_id else "sin_propiedad_asignada"})

    filters = PropertiesListFilters(tipo="departamento", provincia="Córdoba",
        localidad="  SAN   FRANCISCO ", barrio="CENTRO", propietario="10000001")
    first, total = properties.list(page=1, page_size=1, search="Ana", filters=filters)
    second, second_total = properties.list(page=2, page_size=1, search="Ana", filters=filters)
    beyond, beyond_total = properties.list(page=3, page_size=1, search="Ana", filters=filters)
    assert total == second_total == beyond_total == 2
    assert len(first) == len(second) == 1 and beyond == []
    assert first[0]["id"] != second[0]["id"]
    assert first[0]["tipo"] == second[0]["tipo"] == "departamento"
    filters.tiene_inquilino_activo = False
    rows, total = properties.list(page=1, page_size=10, search=None, filters=filters)
    assert total == 1 and str(rows[0]["id"]) == str(property_ids[1])
    filters.tiene_inquilino_activo = True
    rows, total = properties.list(page=1, page_size=10, search=None, filters=filters)
    assert total == 1 and str(rows[0]["id"]) == str(property_ids[0])

    for with_properties, expected in ((True, 2), (False, 1)):
        rows, total = owners.list(page=1, page_size=1, search="Sintetic",
                                 filters=OwnersListFilters(con_inmuebles=with_properties))
        assert total == expected and len(rows) == 1
    rows, total = owners.list(page=1, page_size=10, search="Carla",
                             filters=OwnersListFilters(con_inmuebles=True))
    assert total == 0 and rows == []
    rows, total = tenants.list(page=1, page_size=1, search="Persona",
        filters=TenantsListFilters(estado="activo", provincia="Córdoba", localidad="SAN FRANCISCO"))
    assert total == 1 and str(rows[0]["propiedad"]["id"]) == str(property_ids[0])
    rows, total = tenants.list(page=1, page_size=1, search=None,
        filters=TenantsListFilters(estado="sin_propiedad_asignada", provincia="Córdoba"))
    assert total == 0 and rows == []
