"""Contadores de HU31 en una única instantánea, sin cargar listados."""

from datetime import UTC

from sqlalchemy import DateTime, text

from app.db.database import SessionLocal
from app.schemas.admin_home import AdminHomeSummary


SUMMARY_QUERY = text("""
    WITH providers AS (
        SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE activo) AS activos
        FROM proveedores
    ), operators AS (
        SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE activo) AS activos
        FROM usuarios WHERE rol = 'operador'
    ), claims AS (
        SELECT
            COUNT(*) FILTER (
                WHERE r.estado NOT IN ('Resuelto', 'Resuelto (sin confirmación)')
            ) AS activos,
            COUNT(*) FILTER (
                WHERE r.estado IN ('Escalado', 'Clasificación pendiente')
                  AND r.tipo_gasto IS NULL
                  AND COALESCE(r.origen_clasificacion, '') NOT IN ('operador', 'administrador')
                  AND NOT EXISTS (
                      SELECT 1 FROM reclamo_responsables rr WHERE rr.reclamo_id = r.id
                  )
            ) AS pendientes_clasificacion
        FROM reclamos r
    )
    SELECT CURRENT_TIMESTAMP AS consultado_en,
           (SELECT COUNT(*) FROM propietarios) AS propietarios,
           (SELECT COUNT(*) FROM propiedades) AS propiedades,
           (SELECT COUNT(*) FROM inquilinos) AS inquilinos,
           p.total AS proveedores, p.activos AS proveedores_activos,
           o.total AS operadores, o.activos AS operadores_activos,
           r.activos AS reclamos_activos, r.pendientes_clasificacion
    FROM providers p CROSS JOIN operators o CROSS JOIN claims r
""").columns(consultado_en=DateTime(timezone=True))


class SqlAlchemyAdminHomeRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def get_summary(self) -> AdminHomeSummary:
        # Cada agregado produce una sola fila: no multiplica registros por
        # fotos, especialidades, coberturas u otras relaciones 1:N.
        # La regla de pendientes coincide con la cola de clasificación de HU13;
        # no cuenta escalados posteriores que ya tienen tipo o responsable.
        with self.session_factory() as session:
            row = session.execute(SUMMARY_QUERY).mappings().one()
        consulted = row["consultado_en"]
        if consulted.tzinfo is None:
            consulted = consulted.replace(tzinfo=UTC)
        return AdminHomeSummary(
            consultado_en=consulted,
            propietarios={"total": row["propietarios"]},
            propiedades={"total": row["propiedades"]},
            inquilinos={"total": row["inquilinos"]},
            proveedores={"total": row["proveedores"], "activos": row["proveedores_activos"]},
            operadores={"total": row["operadores"], "activos": row["operadores_activos"]},
            reclamos={"activos": row["reclamos_activos"],
                      "pendientes_clasificacion": row["pendientes_clasificacion"]},
        )
