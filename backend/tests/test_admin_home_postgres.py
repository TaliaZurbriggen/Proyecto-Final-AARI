"""Contadores HU31 contra migraciones reales en PostgreSQL local descartable."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.admin_home import SqlAlchemyAdminHomeRepository
from tests.test_responsible_actor_postgres import local_engine


pytestmark = pytest.mark.skipif(
    not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Requiere PostgreSQL local dedicado.",
)


def test_postgres_summary_is_fresh_private_and_does_not_multiply_relations(local_engine):
    repo = SqlAlchemyAdminHomeRepository(sessionmaker(bind=local_engine))
    empty = repo.get_summary()
    assert empty.propietarios.total == empty.reclamos.activos == 0
    assert empty.consultado_en.tzinfo is not None
    with local_engine.begin() as connection:
        owner = connection.execute(text("""
            INSERT INTO propietarios (nombre_completo, dni, email, telefono)
            VALUES ('Titular Sintetico', '10000001', 'owner@example.com', '00000000')
            RETURNING id
        """)).scalar_one()
        for n, active in enumerate((True, True, False), 1):
            provider = connection.execute(text("""
                INSERT INTO proveedores (nombre_razon_social, telefono, activo)
                VALUES ('Proveedor Sintetico', :phone, :active) RETURNING id
            """), {"phone": f"+54356400010{n}", "active": active}).scalar_one()
            for location in ("Localidad Alfa", "Localidad Beta"):
                connection.execute(text("""
                    INSERT INTO proveedor_coberturas (proveedor_id, provincia, localidad, cubre_toda_localidad)
                    VALUES (:provider, 'Córdoba', :location, true)
                """), {"provider": provider, "location": location})
        for n, (role, active) in enumerate((("operador", True), ("operador", False),
                                          ("administrador", True)), 1):
            connection.execute(text("""
                INSERT INTO usuarios (email, password_hash, rol, activo, nombre_completo)
                VALUES (:email, 'not-a-credential', :role, :active, 'Persona Sintetica')
            """), {"email": f"person{n}@example.com", "role": role, "active": active})
        claim_ids = []
        cases = [
            ("Recibido", None, None, False),
            ("Escalado", None, "agente", False),
            ("Clasificación pendiente", None, None, False),
            ("Escalado", "extraordinario", "agente", False),
            ("Escalado", None, "agente", True),
            ("Escalado", None, "operador", False),
            ("Resuelto", "ordinario", "agente", False),
            ("Reabierto por disconformidad", "ordinario", "agente", False),
        ]
        for n, (state, expense, origin, responsible) in enumerate(cases):
            property_id = connection.execute(text("""
                INSERT INTO propiedades (direccion, provincia, localidad, tipo, propietario_id)
                VALUES (:address, 'Córdoba', 'Localidad de prueba', 'casa', :owner) RETURNING id
            """), {"address": f"Unidad Sintetica {100 + n}", "owner": owner}).scalar_one()
            tenant = connection.execute(text("""
                INSERT INTO inquilinos (nombre_completo, dni, email, telefono, propiedad_id)
                VALUES ('Inquilino Sintetico', :dni, :email, '00000000', :property) RETURNING id
            """), {"dni": str(20000000 + n), "email": f"tenant{n}@example.com",
                   "property": property_id}).scalar_one()
            claim = connection.execute(text("""
                INSERT INTO reclamos (descripcion, urgencia, inquilino_id, propiedad_id,
                                      estado, tipo_gasto, origen_clasificacion)
                VALUES ('Descripción ficticia para contadores de prueba.', 'media', :tenant,
                        :property, :state, :expense, :origin) RETURNING id
            """), {"tenant": tenant, "property": property_id, "state": state,
                   "expense": expense, "origin": origin}).scalar_one()
            claim_ids.append(claim)
            if responsible:
                connection.execute(text("""
                    INSERT INTO reclamo_responsables (reclamo_id, actor_tipo, contacto_error,
                        recordatorio_programado_en, respuesta_vence_en)
                    VALUES (:claim, 'inquilino', 'Contacto sintético no disponible',
                        now() + interval '48 hours', now() + interval '72 hours')
                """), {"claim": claim})
    summary = repo.get_summary()
    assert summary.propietarios.total == 1
    assert summary.propiedades.total == summary.inquilinos.total == 8
    assert summary.proveedores.model_dump() == {"total": 3, "activos": 2}
    assert summary.operadores.model_dump() == {"total": 2, "activos": 1}
    assert summary.reclamos.model_dump() == {"activos": 7, "pendientes_clasificacion": 2}
    with local_engine.begin() as connection:
        connection.execute(text("""
            UPDATE reclamos SET tipo_gasto='ordinario', origen_clasificacion='operador'
            WHERE id=:id
        """), {"id": claim_ids[1]})
        connection.execute(text("UPDATE reclamos SET estado='Resuelto' WHERE id=:id"),
                           {"id": claim_ids[0]})
    updated = repo.get_summary()
    assert updated.reclamos.model_dump() == {"activos": 6, "pendientes_clasificacion": 1}
