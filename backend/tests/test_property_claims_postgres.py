"""HU11 con migraciones reales y datos ficticios en PostgreSQL local descartable."""

from datetime import UTC, date, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.property_claims import SqlAlchemyPropertyClaimsRepository
from app.schemas.property_claims import PropertyClaimsFilters
from app.services.property_claims_service import PropertyHistoryClaimNotFoundError
# Reutiliza la fixture que aplica las migraciones en una base local creada por caso.
from tests.test_responsible_actor_postgres import local_engine


pytestmark = pytest.mark.skipif(
    not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Requiere PostgreSQL local dedicado.",
)


def test_real_postgres_history_filters_dates_and_tenant_scope(local_engine):
    user_id, tenant_id, owner_id, property_id = [uuid4() for _ in range(4)]
    start = datetime(2026, 10, 1, 3, tzinfo=UTC)
    with local_engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO usuarios (id, email, password_hash, rol, primer_ingreso)
            VALUES (:id, 'tenant@example.com', 'not-a-credential', 'inquilino', false)
        """), {"id": user_id})
        connection.execute(text("""
            INSERT INTO propietarios (id, nombre_completo, dni, email, telefono)
            VALUES (:id, 'Titular Sintetico', '10000001', 'owner@example.com', '00000000')
        """), {"id": owner_id})
        connection.execute(text("""
            INSERT INTO propiedades (id, direccion, provincia, localidad, tipo, propietario_id)
            VALUES (:id, 'Unidad de prueba 100', 'Córdoba', 'Localidad de prueba', 'casa', :owner)
        """), {"id": property_id, "owner": owner_id})
        connection.execute(text("""
            INSERT INTO inquilinos (id, nombre_completo, dni, email, telefono, propiedad_id, usuario_id)
            VALUES (:id, 'Inquilino Sintetico', '10000002', 'tenant@example.com', '00000000', :property, :user)
        """), {"id": tenant_id, "property": property_id, "user": user_id})
        other_id = connection.execute(text("""
            INSERT INTO inquilinos (nombre_completo, dni, email, telefono, estado)
            VALUES ('Otra Persona', '10000003', 'other@example.com', '00000000', 'sin_propiedad_asignada')
            RETURNING id
        """)).scalar_one()
        ids = []
        for n in range(25):
            instant = start + timedelta(hours=n)
            if n == 0:
                instant = start - timedelta(microseconds=1)
            claim_id = connection.execute(text("""
                INSERT INTO reclamos (descripcion, urgencia, inquilino_id, propiedad_id,
                                      estado, tipo_gasto, creado_en)
                VALUES ('Descripción sintética de un reclamo de prueba.', 'media', :tenant,
                        :property, 'Resuelto', 'ordinario', :created)
                RETURNING id
            """), {"tenant": tenant_id if n < 22 else other_id,
                   "property": property_id, "created": instant}).scalar_one()
            # El alta registra el estado inicial desde el repositorio; el trigger
            # existente registra únicamente transiciones posteriores por UPDATE.
            connection.execute(text("""
                INSERT INTO reclamo_historial_estados
                    (reclamo_id, estado_anterior, estado_nuevo, origen, timestamp)
                VALUES (:claim, NULL, 'Resuelto', 'inquilino', :created)
            """), {"claim": claim_id, "created": instant})
            ids.append(claim_id)
    repository = SqlAlchemyPropertyClaimsRepository(sessionmaker(bind=local_engine))
    whole = repository.list(property_id=property_id, user_id=None, tenant_id=None,
                            filters=PropertyClaimsFilters())
    assert whole.total == 25 and len(whole.items) == 20 and whole.total_pages == 2
    assert repository.list(property_id=property_id, user_id=None, tenant_id=None,
                           filters=PropertyClaimsFilters(page=2)).items[-1].id == ids[0]
    filters = PropertyClaimsFilters(estado="Resuelto", tipo_gasto="ordinario",
                                   fecha_desde=date(2026, 10, 1), fecha_hasta=date(2026, 10, 1))
    filtered = repository.list(property_id=property_id, user_id=None, tenant_id=None, filters=filters)
    assert filtered.total == 23  # Excluye el instante anterior y la medianoche siguiente.
    own = repository.list(property_id=property_id, user_id=user_id, tenant_id=tenant_id, filters=filters)
    assert own.total == 21
    with pytest.raises(PropertyHistoryClaimNotFoundError):
        repository.get(property_id=property_id, claim_id=ids[24], user_id=user_id, tenant_id=tenant_id)
    detail = repository.get(property_id=property_id, claim_id=ids[1], user_id=user_id, tenant_id=tenant_id)
    assert detail.tipo_gasto == "ordinario" and detail.historial[0].estado_nuevo == "Resuelto"
    assert detail.creado_en.tzinfo is not None
    with local_engine.begin() as connection:
        connection.execute(text("UPDATE reclamos SET estado='En proceso' WHERE id=:id"), {"id": ids[1]})
    updated = repository.get(property_id=property_id, claim_id=ids[1], user_id=user_id, tenant_id=tenant_id)
    assert updated.estado == "En proceso"
    assert [entry.estado_nuevo for entry in updated.historial] == ["Resuelto", "En proceso"]
    # El vínculo actual se elimina; los reclamos propios siguen consultables.
    with local_engine.begin() as connection:
        connection.execute(text("UPDATE inquilinos SET propiedad_id=NULL, estado='sin_propiedad_asignada' WHERE id=:id"), {"id": tenant_id})
    assert repository.list(property_id=property_id, user_id=user_id, tenant_id=tenant_id,
                           filters=PropertyClaimsFilters()).total == 22
