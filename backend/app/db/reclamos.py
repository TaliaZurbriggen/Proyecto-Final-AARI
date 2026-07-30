"""Acceso a datos de reclamos para el flujo de clasificación."""

from uuid import UUID

from sqlalchemy import text

from app.db.database import SessionLocal
from app.schemas.reclamos import AgentClassificationResult, ClaimClassificationResponse
from app.services.classification_service import ClaimForClassification


class SqlAlchemyClaimsRepository:
    """Implementación PostgreSQL del puerto de reclamos."""

    def get_for_classification(self, reclamo_id: UUID) -> ClaimForClassification | None:
        statement = text(
            """
            SELECT r.id, r.descripcion, r.urgencia::text AS urgencia,
                   e.nombre AS rubro_declarado
            FROM reclamos r
            JOIN especialidades e ON e.id = r.tipo_id
            WHERE r.id = :reclamo_id
            """
        )
        with SessionLocal() as session:
            row = session.execute(statement, {"reclamo_id": str(reclamo_id)}).mappings().one_or_none()

        if row is None:
            return None
        return ClaimForClassification(
            reclamo_id=row["id"],
            descripcion=row["descripcion"],
            urgencia=row["urgencia"],
            rubro_declarado=row["rubro_declarado"],
            clausulas_contrato=[],
        )

    def persist_classification(
        self,
        reclamo_id: UUID,
        result: AgentClassificationResult,
    ) -> ClaimClassificationResponse:
        estado = "Escalado" if result.debe_escalar else "Clasificado"
        statement = text(
            """
            UPDATE reclamos
            SET estado = :estado,
                tipo_gasto = CAST(:tipo_gasto AS tipo_gasto_reclamo),
                confianza_clasificacion = :confianza,
                fundamento_clasificacion = :fundamento,
                motivo_escalado = :motivo_escalado,
                origen_clasificacion = 'agente',
                clasificado_en = now()
            WHERE id = :reclamo_id
            RETURNING id, estado, tipo_gasto::text AS tipo_gasto,
                      confianza_clasificacion, fundamento_clasificacion,
                      motivo_escalado
            """
        )
        params = {
            "estado": estado,
            "tipo_gasto": result.tipo_gasto,
            "confianza": result.confianza,
            "fundamento": result.fundamento,
            "motivo_escalado": result.motivo_escalado,
            "reclamo_id": str(reclamo_id),
        }
        with SessionLocal.begin() as session:
            session.execute(
                text("SELECT set_config('app.origen_reclamo', 'agente', true)")
            )
            row = session.execute(statement, params).mappings().one_or_none()

        if row is None:
            raise RuntimeError("El reclamo desapareció antes de persistir su clasificación.")
        return ClaimClassificationResponse(
            reclamo_id=row["id"],
            estado=row["estado"],
            tipo_gasto=row["tipo_gasto"],
            confianza=float(row["confianza_clasificacion"])
            if row["confianza_clasificacion"] is not None
            else None,
            fundamento=row["fundamento_clasificacion"],
            debe_escalar=result.debe_escalar,
            motivo_escalado=row["motivo_escalado"],
        )
