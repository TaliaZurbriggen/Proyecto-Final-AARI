"""Consultas paginadas: el alcance del usuario se aplica también al total y detalle."""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.db.database import SessionLocal
from app.schemas.property_claims import (
    PropertyClaimDetail,
    PropertyClaimsFilters,
    PropertyClaimsPage,
    PropertyClaimSummary,
)
from app.schemas.reclamos import ClaimHistoryItem, ClaimPropertyContext
from app.services.property_claims_service import (
    PropertyHistoryClaimNotFoundError,
    PropertyHistoryForbiddenError,
    PropertyHistoryNotFoundError,
)


CLAIM_COLUMNS = """
    r.id, r.numero, r.descripcion, r.estado, CAST(r.tipo_gasto AS TEXT) AS tipo_gasto,
    CAST(r.urgencia AS TEXT) AS urgencia, r.creado_en, r.updated_at
"""
PAGE_SIZE = 20
LOCAL_TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")


class SqlAlchemyPropertyClaimsRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    @staticmethod
    def _property(session, *, property_id, user_id, tenant_id):
        params = {"property_id": str(property_id)}
        permission = ""
        if user_id is not None:
            params.update(user_id=str(user_id), tenant_id=str(tenant_id))
            permission = """
                AND EXISTS (
                    SELECT 1 FROM inquilinos i
                    WHERE i.id = :tenant_id AND i.usuario_id = :user_id
                      AND (i.propiedad_id = p.id OR EXISTS (
                          SELECT 1 FROM reclamos own
                          WHERE own.inquilino_id = i.id AND own.propiedad_id = p.id
                      ))
                )
            """
        row = session.execute(text("""
            SELECT p.id, p.direccion, p.provincia, p.localidad, p.barrio,
                   CAST(p.tipo AS TEXT) AS tipo, p.piso, p.numero
            FROM propiedades p WHERE p.id = :property_id
        """ + permission), params).mappings().one_or_none()
        if row is None:
            if user_id is not None:
                raise PropertyHistoryForbiddenError
            raise PropertyHistoryNotFoundError
        return ClaimPropertyContext.model_validate(dict(row))

    @staticmethod
    def _where(*, property_id, user_id, tenant_id, filters):
        clauses = ["r.propiedad_id = :property_id"]
        params = {"property_id": str(property_id)}
        if user_id is not None:
            clauses.extend(["i.usuario_id = :user_id", "i.id = :tenant_id"])
            params.update(user_id=str(user_id), tenant_id=str(tenant_id))
        if filters.estado:
            clauses.append("r.estado = :estado")
            params["estado"] = filters.estado
        if filters.tipo_gasto == "sin_clasificar":
            clauses.append("r.tipo_gasto IS NULL")
        elif filters.tipo_gasto:
            clauses.append("r.tipo_gasto = :tipo_gasto")
            params["tipo_gasto"] = filters.tipo_gasto
        if filters.fecha_desde:
            clauses.append("r.creado_en >= :date_start")
            params["date_start"] = datetime.combine(
                filters.fecha_desde, time.min, LOCAL_TIMEZONE
            ).astimezone(UTC)
        if filters.fecha_hasta:
            clauses.append("r.creado_en < :date_end")
            params["date_end"] = datetime.combine(
                filters.fecha_hasta + timedelta(days=1), time.min, LOCAL_TIMEZONE
            ).astimezone(UTC)
        return " AND ".join(clauses), params

    def list(self, *, property_id: UUID, user_id: UUID | None,
             tenant_id: UUID | None, filters: PropertyClaimsFilters) -> PropertyClaimsPage:
        where, params = self._where(
            property_id=property_id, user_id=user_id, tenant_id=tenant_id, filters=filters
        )
        source = "FROM reclamos r JOIN inquilinos i ON i.id = r.inquilino_id WHERE " + where
        with self.session_factory() as session:
            property_context = self._property(
                session, property_id=property_id, user_id=user_id, tenant_id=tenant_id
            )
            total = session.execute(text("SELECT COUNT(*) " + source), params).scalar_one()
            rows = session.execute(text(
                "SELECT " + CLAIM_COLUMNS + source
                + " ORDER BY r.creado_en DESC, r.numero DESC LIMIT :limit OFFSET :offset"
            ), {**params, "limit": PAGE_SIZE, "offset": (filters.page - 1) * PAGE_SIZE}).mappings().all()
        return PropertyClaimsPage(
            propiedad=property_context,
            items=[PropertyClaimSummary.model_validate(dict(row)) for row in rows],
            total=total, page=filters.page, total_pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        )

    def get(self, *, property_id: UUID, claim_id: UUID,
            user_id: UUID | None, tenant_id: UUID | None) -> PropertyClaimDetail:
        where, params = self._where(
            property_id=property_id, user_id=user_id, tenant_id=tenant_id,
            filters=PropertyClaimsFilters(),
        )
        params["claim_id"] = str(claim_id)
        with self.session_factory() as session:
            property_context = self._property(
                session, property_id=property_id, user_id=user_id, tenant_id=tenant_id
            )
            row = session.execute(text(
                "SELECT " + CLAIM_COLUMNS
                + " FROM reclamos r JOIN inquilinos i ON i.id = r.inquilino_id WHERE "
                + where + " AND r.id = :claim_id"
            ), params).mappings().one_or_none()
            if row is None:
                raise PropertyHistoryClaimNotFoundError
            history = session.execute(text("""
                SELECT estado_anterior, estado_nuevo, origen, timestamp
                FROM reclamo_historial_estados WHERE reclamo_id = :claim_id
                ORDER BY timestamp ASC, id ASC
            """), {"claim_id": str(claim_id)}).mappings().all()
        return PropertyClaimDetail(
            **dict(row), propiedad=property_context,
            historial=[ClaimHistoryItem.model_validate(dict(item)) for item in history],
        )
