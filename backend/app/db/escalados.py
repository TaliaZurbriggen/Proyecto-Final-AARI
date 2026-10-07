"""Consultas privadas de la cola de clasificación humana (HU13)."""

from uuid import UUID

from sqlalchemy import text

from app.db.database import SessionLocal
from app.schemas.escalados import EscalatedClaimDetail, EscalatedClaimItem, EscalatedClaimsPage
from app.schemas.reclamos import ClaimPropertyContext
from app.services.escalated_claims_service import (
    EscalatedClaimNotFoundError, ManualClassificationConflictError,
    ensure_manual_classification_allowed,
)


CLAIM_COLUMNS = """
    r.id, r.numero, r.descripcion, r.urgencia::text AS urgencia, r.estado,
    r.creado_en, r.updated_at, r.motivo_escalado,
    r.tipo_gasto::text AS tipo_gasto, r.origen_clasificacion,
    r.fundamento_clasificacion, r.confianza_clasificacion,
    i.nombre_completo AS inquilino_nombre,
    p.id AS propiedad_id, p.direccion, p.provincia, p.localidad, p.barrio,
    p.tipo::text AS propiedad_tipo, p.piso, p.numero AS propiedad_numero,
    (SELECT MAX(h.timestamp) FROM reclamo_historial_estados h
     WHERE h.reclamo_id = r.id AND h.estado_nuevo = 'Escalado') AS escalado_en,
    EXISTS (SELECT 1 FROM reclamo_responsables rr WHERE rr.reclamo_id = r.id) AS has_responsible
"""
SOURCE = "FROM reclamos r JOIN propiedades p ON p.id = r.propiedad_id JOIN inquilinos i ON i.id = r.inquilino_id"
PENDING = """
    r.estado IN ('Escalado', 'Clasificación pendiente') AND r.tipo_gasto IS NULL
    AND COALESCE(r.origen_clasificacion, '') NOT IN ('operador', 'administrador')
    AND NOT EXISTS (SELECT 1 FROM reclamo_responsables rr WHERE rr.reclamo_id = r.id)
"""
QUEUE_MEMBER = """
    (r.estado IN ('Escalado', 'Clasificación pendiente')
     OR EXISTS (SELECT 1 FROM reclamo_historial_estados h
                WHERE h.reclamo_id = r.id
                  AND h.estado_nuevo IN ('Escalado', 'Clasificación pendiente'))
     OR EXISTS (SELECT 1 FROM reclamo_decisiones_clasificacion d
                WHERE d.reclamo_id = r.id))
"""


def claim_item(row):
    data = dict(row)
    data["propiedad"] = ClaimPropertyContext(
        id=row["propiedad_id"], direccion=row["direccion"], provincia=row["provincia"],
        localidad=row["localidad"], barrio=row["barrio"], tipo=row["propiedad_tipo"],
        piso=row["piso"], numero=row["propiedad_numero"],
    )
    return data


class SqlAlchemyEscalatedClaimsRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def list(self, *, page=1, page_size=20, search="") -> EscalatedClaimsPage:
        where = PENDING
        params = {}
        clean = search.strip()
        if clean:
            # Los comodines del usuario se interpretan como texto, no como patrones.
            pattern = clean.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where += """ AND (r.numero::text ILIKE :search OR r.descripcion ILIKE :search
                              OR p.direccion ILIKE :search) """
            params["search"] = "%" + pattern + "%"
        with self.session_factory() as session:
            total = session.execute(text("SELECT COUNT(*) " + SOURCE + " WHERE " + where), params).scalar_one()
            rows = session.execute(text(
                "SELECT " + CLAIM_COLUMNS + SOURCE + " WHERE " + where
                + " ORDER BY r.creado_en ASC, r.id ASC LIMIT :limit OFFSET :offset"
            ), {**params, "limit": page_size, "offset": (page - 1) * page_size}).mappings().all()
        return EscalatedClaimsPage(
            items=[EscalatedClaimItem.model_validate(claim_item(row)) for row in rows],
            total=total, page=page, page_size=page_size,
            total_pages=max(1, (total + page_size - 1) // page_size),
        )

    def get(self, claim_id: UUID) -> EscalatedClaimDetail:
        with self.session_factory() as session:
            row = session.execute(text("SELECT " + CLAIM_COLUMNS + SOURCE
                                       + " WHERE r.id = :id AND " + QUEUE_MEMBER),
                                  {"id": str(claim_id)}).mappings().one_or_none()
            if row is None:
                raise EscalatedClaimNotFoundError
            data = claim_item(row)
            try:
                ensure_manual_classification_allowed(
                    estado=row["estado"], tipo_gasto=row["tipo_gasto"],
                    has_responsible=row["has_responsible"], origen=row["origen_clasificacion"],
                )
                data["puede_resolver"] = True
            except ManualClassificationConflictError:
                data["puede_resolver"] = False
            data["historial"] = session.execute(text("""
                SELECT estado_anterior, estado_nuevo, origen, timestamp
                FROM reclamo_historial_estados WHERE reclamo_id = :id ORDER BY timestamp, id
            """), {"id": str(claim_id)}).mappings().all()
            data["fotos"] = session.execute(text("""
                SELECT id, formato FROM reclamo_fotos WHERE reclamo_id = :id ORDER BY created_at, id
            """), {"id": str(claim_id)}).mappings().all()
            data["decisiones"] = session.execute(text("""
                SELECT id, usuario_id, usuario_nombre, rol, decidido_en,
                       tipo_gasto::text AS tipo_gasto, fundamento, resultado_anterior
                FROM reclamo_decisiones_clasificacion
                WHERE reclamo_id = :id ORDER BY decidido_en, id
            """), {"id": str(claim_id)}).mappings().all()
        return EscalatedClaimDetail.model_validate(data)

    def photo(self, claim_id: UUID, photo_id: UUID):
        with self.session_factory() as session:
            row = session.execute(text("""
                SELECT f.url, f.formato FROM reclamo_fotos f
                JOIN reclamos r ON r.id = f.reclamo_id
                WHERE f.id = :photo_id AND r.id = :claim_id AND
            """ + QUEUE_MEMBER),
                {"photo_id": str(photo_id), "claim_id": str(claim_id)}).mappings().one_or_none()
        if row is None:
            raise EscalatedClaimNotFoundError
        return row
