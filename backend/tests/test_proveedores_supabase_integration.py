"""Integración optativa de proveedores contra Supabase con rollback final."""

import os
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.proveedores import SqlAlchemyProveedoresRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SUPABASE_INTEGRATION") != "1",
    reason="Requiere habilitación explícita y una base Supabase disponible.",
)


def test_provider_management_against_real_schema_rolls_back_all_changes() -> None:
    """Recorre alta, filtros, edición y estado sin conservar datos de prueba."""

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        transaction = connection.begin()
        repository = SqlAlchemyProveedoresRepository(
            sessionmaker(bind=connection, expire_on_commit=False)
        )
        try:
            specialties = repository.list_specialties()
            assert specialties
            specialty_id = str(specialties[0]["id"])
            payload = {
                "nombre_razon_social": "Proveedor integración AARI",
                "matricula": "TEST 2026",
                "telefono": "+5491100000046",
                "activo": True,
                "hora_inicio": "08:00:00",
                "hora_fin": "17:00:00",
                "especialidad_ids": [specialty_id],
                "especialidades_personalizadas": ["integración técnica"],
                "coberturas": [
                    {
                        "provincia": "Córdoba",
                        "localidad": "San Francisco",
                        "cubre_toda_localidad": False,
                        "barrios": ["Centro"],
                    }
                ],
            }

            created = repository.create(payload)
            provider_id = UUID(str(created["id"]))
            items, total = repository.list(
                page=1,
                page_size=10,
                search="integración",
                especialidad_id=UUID(specialty_id),
                provincia="Córdoba",
                localidad="Francisco",
                barrio="Centro",
                activo=True,
            )
            updated = repository.update(
                provider_id,
                {
                    **payload,
                    "nombre_razon_social": "Proveedor integración actualizado",
                    "coberturas": [
                        {
                            "provincia": "Santa Fe",
                            "localidad": "Rafaela",
                            "cubre_toda_localidad": True,
                            "barrios": [],
                        }
                    ],
                },
            )
            deactivated = repository.update_status(provider_id, False)

            assert total == len(items) == 1
            assert updated is not None
            assert updated["coberturas"][0]["localidad"] == "Rafaela"
            assert deactivated is not None and deactivated["activo"] is False
        finally:
            transaction.rollback()
    engine.dispose()
