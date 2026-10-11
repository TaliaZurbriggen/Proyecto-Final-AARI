"""HU15: lecturas sin efectos; búsqueda, especialidad y outbox atómicas."""

import hashlib
import json
from contextlib import nullcontext
from uuid import uuid4

from sqlalchemy import text

from app.db.database import SessionLocal
from app.db.proveedores import SqlAlchemyProveedoresRepository
from app.schemas.provider_candidates import (
    CandidateClaimItem, CandidateClaimsPage, CandidateProvidersPage, CandidateSearchExecution,
)
from app.services.provider_candidates_service import (
    CandidateClaimNotFoundError, CandidateSearchConflictError, CandidateSearchPermissionError,
    CandidateSpecialtyNotFoundError, ensure_search_stage, request_fingerprint, search_inputs,
)


SOURCE = """
    FROM reclamos r JOIN propiedades p ON p.id = r.propiedad_id
    LEFT JOIN especialidades e ON e.id = r.tipo_id
"""
COLUMNS = """
    r.id, r.numero, r.descripcion, r.estado, r.creado_en, r.updated_at,
    r.tipo_gasto::text AS tipo_gasto, r.tipo_id, r.proveedor_seleccionado_id,
    r.operador_asignado_id, e.nombre AS especialidad_nombre,
    p.id AS propiedad_id, p.direccion, p.provincia, p.localidad, p.barrio,
    p.tipo::text AS propiedad_tipo, p.piso, p.numero AS propiedad_numero,
    EXISTS (SELECT 1 FROM reclamo_responsables rr WHERE rr.reclamo_id=r.id) AS has_responsible
"""
QUEUE = """r.estado NOT IN (
    'Resuelto', 'Resuelto (sin confirmación)', 'Rechazado por propietario',
    'Derivado a proveedor externo', 'Sesión expirada'
)"""
READABLE = "true"


def claim_data(row):
    return {
        **dict(row),
        "especialidad": {"id": row["tipo_id"], "nombre": row["especialidad_nombre"]}
        if row["tipo_id"] is not None else None,
        "propiedad": {
            "id": row["propiedad_id"], "direccion": row["direccion"],
            "provincia": row["provincia"] or "", "localidad": row["localidad"] or "",
            "barrio": row["barrio"], "tipo": row["propiedad_tipo"],
            "piso": row["piso"], "numero": row["propiedad_numero"],
        },
    }


class SqlAlchemyProviderCandidatesRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    @staticmethod
    def _row(session, claim_id, *, lock=False):
        row = session.execute(text(
            "SELECT " + COLUMNS + SOURCE + " WHERE r.id=:id AND " + READABLE
            + (" FOR UPDATE OF r" if lock else "")
        ), {"id": str(claim_id)}).mappings().one_or_none()
        if row is None:
            raise CandidateClaimNotFoundError
        return row

    @staticmethod
    def _match(session, row, specialty):
        location, missing = search_inputs(row, specialty)
        ids = [] if missing else SqlAlchemyProveedoresRepository.candidate_ids(
            session, specialty_id=specialty, **location,
        )
        return location, missing or ("candidatos_encontrados" if ids else "sin_candidatos"), ids

    def specialties(self):
        with self.session_factory() as session:
            return [dict(row) for row in session.execute(text(
                "SELECT id, nombre FROM especialidades ORDER BY lower(nombre), id"
            )).mappings()]

    def list(self, *, page=1, page_size=20, search=""):
        params = {}
        where = QUEUE
        if search.strip():
            clean = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where += """ AND (r.numero::text ILIKE :search OR r.descripcion ILIKE :search
                OR p.direccion ILIKE :search)"""
            params["search"] = "%" + clean + "%"
        with self.session_factory() as session:
            total = session.execute(text("SELECT COUNT(*) " + SOURCE + " WHERE " + where), params).scalar_one()
            rows = session.execute(text("SELECT " + COLUMNS + """,
                last.resultado AS ultimo_resultado, last.aviso_operador
            """ + SOURCE + """ LEFT JOIN LATERAL (
                SELECT resultado, aviso_operador FROM reclamo_busquedas_proveedores
                WHERE reclamo_id=r.id ORDER BY buscado_en DESC, id DESC LIMIT 1
            ) last ON true WHERE """ + where
                + " ORDER BY r.creado_en, r.id LIMIT :limit OFFSET :offset"),
                {**params, "limit": page_size, "offset": (page-1)*page_size}).mappings().all()
        return CandidateClaimsPage(
            items=[CandidateClaimItem.model_validate(claim_data(row)) for row in rows],
            total=total, page=page, page_size=page_size,
            total_pages=max(1, (total+page_size-1)//page_size),
        )

    def get(self, claim_id, *, page=1, page_size=20, audit_page=1):
        with self.session_factory.begin() as session:
            # El padrón puede editarse mientras se pagina. Mantener una única
            # vista MVCC también evita perder un proveedor entre IDs e hidratación.
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            # Sólo lectura MVCC: no bloquear una decisión concurrente del flujo,
            # escribir ni encolar notificaciones. El POST revalida la versión.
            row = session.execute(text("SELECT " + COLUMNS + SOURCE
                + " WHERE r.id=:id AND " + READABLE),
                {"id": str(claim_id)}).mappings().one_or_none()
            if row is None:
                raise CandidateClaimNotFoundError
            _, outcome, ids = self._match(session, row, row["tipo_id"])
            records = SqlAlchemyProveedoresRepository.candidate_records(
                session, ids[(page-1)*page_size:page*page_size],
            )
            audits = session.execute(text("""
                SELECT * FROM reclamo_busquedas_proveedores WHERE reclamo_id=:id
                ORDER BY buscado_en DESC, id DESC LIMIT 10 OFFSET :offset
            """), {"id": str(claim_id), "offset": (audit_page-1)*10}).mappings().all()
            total_audits = session.execute(text("""
                SELECT count(*) FROM reclamo_busquedas_proveedores WHERE reclamo_id=:id
            """), {"id": str(claim_id)}).scalar_one()
            latest = session.execute(text("""
                SELECT resultado, aviso_operador FROM reclamo_busquedas_proveedores WHERE reclamo_id=:id
                ORDER BY buscado_en DESC, id DESC LIMIT 1
            """), {"id": str(claim_id)}).mappings().one_or_none()
            # La migración de automatización es incremental. La pantalla sigue
            # disponible con la migración base ya aplicada mientras se despliega.
            task = None
            if session.execute(text("SELECT to_regclass('public.reclamo_tareas_proveedores')")).scalar_one():
                task = session.execute(text("""
                    SELECT estado, motivo FROM reclamo_tareas_proveedores WHERE reclamo_id=:id
                """), {"id": str(claim_id)}).mappings().one_or_none()
            try:
                ensure_search_stage(row)
                allowed = True
            except CandidateSearchConflictError:
                allowed = False
        return CandidateProvidersPage(
            **claim_data(row), puede_buscar=allowed, resultado=outcome,
            candidatos=records, total=len(ids), page=page, page_size=page_size,
            total_pages=max(1, (len(ids)+page_size-1)//page_size),
            historial_busquedas=[dict(audit) for audit in audits], historial_total=total_audits,
            ultimo_resultado=latest["resultado"] if latest else None,
            aviso_operador=latest["aviso_operador"] if latest else None,
            tarea_agente=task["estado"] if task else None,
            motivo_agente=task["motivo"] if task else None,
        )

    @staticmethod
    def _notify(session, row, *, location, specialty, outcome):
        # Sin hora/suposición de agenda ni datos del inquilino en el correo.
        identity = json.dumps([outcome, str(specialty), location], sort_keys=True)
        key = f"{row['id']}:candidatos:" + hashlib.sha256(identity.encode()).hexdigest()
        existing = session.execute(text("""
            SELECT id FROM notificaciones WHERE clave_idempotencia=:key
        """), {"key": key}).scalar_one_or_none()
        if existing:
            return "encolado"
        recipient = session.execute(text("""
            SELECT id, email, rol::text AS rol FROM usuarios
            WHERE activo AND NOT primer_ingreso AND rol IN ('operador', 'administrador')
            ORDER BY CASE WHEN id=:assigned AND rol='operador' THEN 0
                WHEN rol='operador' THEN 1 ELSE 2 END, created_at, id
            LIMIT 1 FOR SHARE
        """), {"assigned": row["operador_asignado_id"]}).mappings().one_or_none()
        if recipient is None:
            return "sin_destinatario"
        session.execute(text("""
            INSERT INTO notificaciones (
                reclamo_id, destinatario_tipo, destinatario_contacto, canal, asunto,
                mensaje, estado_reclamo, tipo_evento, clave_idempotencia,
                estado_envio, proximo_intento_en
            ) VALUES (:claim, :role, :email, 'email', :subject, :message,
                :state, 'alerta_operador', :key, 'pendiente', now())
            ON CONFLICT (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL DO NOTHING
        """), {"claim": str(row["id"]), "role": recipient["rol"], "email": recipient["email"],
               "subject": f"AARI - Reclamo #{row['numero']:06d} pendiente de proveedores",
               "state": row["estado"],
               "message": "Revisá Proveedores por reclamo en AARI. Motivo: " + {
                   "sin_candidatos": "no hay proveedores activos con especialidad y cobertura compatibles.",
                   "especialidad_pendiente": "falta indicar la especialidad requerida.",
                   "ubicacion_incompleta": "falta completar provincia o localidad de la propiedad.",
               }[outcome], "key": key})
        return "encolado"

    def search(self, claim_id, request, *, origin, user_id, session=None):
        fingerprint = request_fingerprint(request, origin=origin, user_id=user_id)
        with (nullcontext(session) if session is not None else self.session_factory.begin()) as session:
            # Orden de bloqueo usuario -> reclamo, compatible con HU7/HU13.
            if origin != "agente":
                actor = session.execute(text("""
                    SELECT rol::text AS rol FROM usuarios WHERE id=:id
                    AND activo AND NOT primer_ingreso AND rol IN ('operador', 'administrador')
                    FOR SHARE
                """), {"id": str(user_id)}).mappings().one_or_none()
                if actor is None or actor["rol"] != origin:
                    raise CandidateSearchPermissionError
            row = self._row(session, claim_id, lock=True)
            existing = session.execute(text("""
                SELECT * FROM reclamo_busquedas_proveedores WHERE reclamo_id=:id AND request_id=:request
            """), {"id": str(claim_id), "request": str(request.request_id)}).mappings().one_or_none()
            if existing is not None:
                if existing["request_hash"] != fingerprint:
                    raise CandidateSearchConflictError("Ese intento ya fue utilizado con otros datos.")
                return CandidateSearchExecution(
                    busqueda_id=existing["id"], resultado=existing["resultado"],
                    candidato_ids=existing["candidato_ids"], aviso_operador=existing["aviso_operador"],
                    repetida=True,
                )
            ensure_search_stage(row)
            if row["updated_at"] != request.expected_updated_at:
                raise CandidateSearchConflictError("El reclamo cambió. Actualizá la pantalla antes de buscar.")
            specialty = request.especialidad_id or row["tipo_id"]
            if specialty is not None:
                if session.execute(text("SELECT id FROM especialidades WHERE id=:id FOR SHARE"),
                                   {"id": str(specialty)}).scalar_one_or_none() is None:
                    raise CandidateSpecialtyNotFoundError
            location, outcome, ids = self._match(session, row, specialty)
            alert = self._notify(session, row, location=location, specialty=specialty, outcome=outcome) if not ids else "no_aplica"
            session.execute(text("SELECT set_config('app.origen_reclamo', :origin, true)"), {"origin": origin})
            if user_id:
                session.execute(text("SELECT set_config('app.usuario_reclamo', :id, true)"), {"id": str(user_id)})
            # La búsqueda nunca cambia estado, gasto, actor ni confianza.
            session.execute(text("UPDATE reclamos SET tipo_id=:specialty, updated_at=clock_timestamp() WHERE id=:id"),
                            {"specialty": str(specialty) if specialty else None, "id": str(claim_id)})
            audit_id = uuid4()
            session.execute(text("""
                INSERT INTO reclamo_busquedas_proveedores (
                    id, reclamo_id, request_id, request_hash, origen, usuario_id,
                    especialidad_id, especialidad_anterior_id, provincia, localidad, barrio,
                    resultado, candidato_ids, aviso_operador
                ) VALUES (
                    :audit, :claim, :request, :hash, :origin, :user,
                    :specialty, :previous, :provincia, :localidad, :barrio,
                    :outcome, CAST(:ids AS jsonb), :alert
                )
            """), {"audit": str(audit_id), "claim": str(claim_id), "request": str(request.request_id),
                   "hash": fingerprint, "origin": origin, "user": str(user_id) if user_id else None,
                   "specialty": str(specialty) if specialty else None,
                   "previous": str(row["tipo_id"]) if row["tipo_id"] else None,
                   **location, "outcome": outcome, "ids": json.dumps([str(value) for value in ids]), "alert": alert})
        return CandidateSearchExecution(
            busqueda_id=audit_id, resultado=outcome, candidato_ids=ids, aviso_operador=alert,
        )
