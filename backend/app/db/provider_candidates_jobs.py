"""Trabajos HU15. Cada cambio relevante habilita un intento, no cada updated_at."""

from uuid import uuid4

from sqlalchemy import text

from app.db.provider_candidates import COLUMNS, QUEUE, SOURCE, SqlAlchemyProviderCandidatesRepository
from app.schemas.provider_candidates import CandidateSearchRequest
from app.services.provider_candidates_service import ensure_search_stage

# Huella calculada en PostgreSQL: misma representación al descubrir y finalizar.
# Excluye estado/updated_at: nuestra propia persistencia no genera un bucle.
INPUT_HASH = """encode(digest(jsonb_build_array(
    r.descripcion, r.propiedad_id, r.tipo_id, p.provincia, p.localidad, p.barrio
)::text, 'sha256'), 'hex')"""


class SqlAlchemyProviderCandidatesJobs:
    def __init__(self, candidates=None, *, scope_claim_id=None):
        self.candidates = candidates or SqlAlchemyProviderCandidatesRepository()
        self.session_factory = self.candidates.session_factory
        # Puerto interno de QA: nunca se recibe desde una ruta pública. Permite
        # validar un reclamo ficticio sin reservar trabajos del entorno compartido.
        self.scope_sql = " AND r.id=:scope" if scope_claim_id is not None else ""
        self.scope_params = {"scope": str(scope_claim_id)} if scope_claim_id is not None else {}

    def discover(self, limit=50):
        """Descubre también altas mientras el servidor estaba apagado.

        No necesita que HU16/HU17 cambien el reclamo de etapa. Se bloquea
        reclamo -> tarea, el mismo orden de finalización, sin llamadas externas.
        """
        with self.session_factory.begin() as session:
            # Una reserva vencida NO vuelve a consumir cuota automáticamente.
            expired = session.execute(text("SELECT " + COLUMNS + SOURCE + """
                JOIN reclamo_tareas_proveedores t ON t.reclamo_id=r.id
                WHERE t.estado='procesando' AND t.reserva_hasta < clock_timestamp()
                """ + self.scope_sql + """
                ORDER BY t.actualizado_en LIMIT :limit FOR UPDATE OF r,t SKIP LOCKED
            """), {"limit": limit, **self.scope_params}).mappings().all()
            for row in expired:
                session.execute(text("""
                    UPDATE reclamo_tareas_proveedores SET estado='revision', reserva_token=null,
                        reserva_hasta=null, motivo='El intento se interrumpió; requiere revisión sin reintento automático.',
                        fuente='revision', actualizado_en=clock_timestamp() WHERE reclamo_id=:id
                """), {"id": str(row["id"])})
                location, _, _ = self.candidates._match(session, row, None)
                self.candidates._notify(session, row, location=location, specialty=row["tipo_id"], outcome="especialidad_pendiente")
            rows = session.execute(text("SELECT r.id, " + INPUT_HASH + " AS input_hash " + SOURCE + """
                LEFT JOIN reclamo_tareas_proveedores t ON t.reclamo_id=r.id
                WHERE """ + QUEUE + " AND (t.reclamo_id IS NULL OR t.input_hash <> " + INPUT_HASH + """ )
                """ + self.scope_sql + """
                ORDER BY r.creado_en,r.id LIMIT :limit FOR UPDATE OF r SKIP LOCKED
            """), {"limit": limit, **self.scope_params}).mappings().all()
            for row in rows:
                session.execute(text("""
                    INSERT INTO reclamo_tareas_proveedores (reclamo_id,input_hash)
                    VALUES (:id,:hash) ON CONFLICT (reclamo_id) DO UPDATE
                    SET input_hash=excluded.input_hash, request_id=gen_random_uuid(), estado='pendiente',
                        reserva_token=null,reserva_hasta=null,motivo=null,fuente=null,modelo=null,prompt_version=null,
                        actualizado_en=clock_timestamp()
                """), {"id": str(row["id"]), "hash": row["input_hash"]})
            return len(rows)

    def reserve_one(self):
        with self.session_factory.begin() as session:
            row = session.execute(text("SELECT " + COLUMNS + """, t.input_hash,t.request_id
                """ + SOURCE + """ JOIN reclamo_tareas_proveedores t ON t.reclamo_id=r.id
                WHERE t.estado='pendiente' AND """ + QUEUE + " AND t.input_hash=" + INPUT_HASH + """
                """ + self.scope_sql + """
                ORDER BY t.actualizado_en,r.id LIMIT 1 FOR UPDATE OF r,t SKIP LOCKED
            """), self.scope_params).mappings().one_or_none()
            if row is None:
                return None
            token = uuid4()
            session.execute(text("""
                UPDATE reclamo_tareas_proveedores SET estado='procesando',reserva_token=:token,
                    reserva_hasta=clock_timestamp()+interval '180 seconds',actualizado_en=clock_timestamp()
                WHERE reclamo_id=:id
            """), {"id": str(row["id"]), "token": str(token)})
            catalog = [dict(item) for item in session.execute(text("SELECT id,nombre FROM especialidades ORDER BY lower(nombre),id")).mappings()]
            return {**dict(row), "token": token, "catalogo": catalog}

    def renew(self, job):
        with self.session_factory.begin() as session:
            return session.execute(text("""
                UPDATE reclamo_tareas_proveedores
                SET reserva_hasta=clock_timestamp()+interval '180 seconds'
                WHERE reclamo_id=:id AND request_id=:request AND reserva_token=:token
                    AND estado='procesando' AND reserva_hasta > clock_timestamp()
                RETURNING reclamo_id
            """), self._identity(job)).scalar_one_or_none() is not None

    @staticmethod
    def _identity(job):
        return {"id": str(job["id"]), "request": str(job["request_id"]), "token": str(job["token"])}

    def finish(self, job, resolution):
        with self.session_factory.begin() as session:
            row = session.execute(text("SELECT " + COLUMNS + ", " + INPUT_HASH + " AS input_hash " + SOURCE
                + " WHERE r.id=:id FOR UPDATE OF r FOR SHARE OF p"), {"id": str(job["id"])}).mappings().one_or_none()
            if row is None:
                return None
            task = session.execute(text("""
                SELECT *, reserva_hasta > clock_timestamp() AS vigente FROM reclamo_tareas_proveedores
                WHERE reclamo_id=:id FOR UPDATE
            """), {"id": str(job["id"])}).mappings().one_or_none()
            if (task is None or task["estado"] != "procesando" or task["reserva_token"] != job["token"]
                    or task["request_id"] != job["request_id"] or not task["vigente"]):
                return None
            try:
                ensure_search_stage(row)
                valid = row["input_hash"] == job["input_hash"]
            except Exception:
                valid = False
            if not valid:
                session.execute(text("""
                    UPDATE reclamo_tareas_proveedores SET estado='cancelada', reserva_token=null,reserva_hasta=null,
                        motivo='El reclamo o la ubicación cambiaron; se descartó el resultado.',actualizado_en=clock_timestamp()
                    WHERE reclamo_id=:id
                """), {"id": str(job["id"])})
                return None
            specialty = resolution.get("especialidad_id")
            if specialty is not None and session.execute(text("SELECT id FROM especialidades WHERE id=:id FOR SHARE"),
                                                        {"id": str(specialty)}).scalar_one_or_none() is None:
                resolution = {**resolution, "especialidad_id": None, "fuente": "revision",
                              "motivo": "La especialidad dejó de existir durante la búsqueda; requiere revisión."}
            result = self.candidates.search(
                job["id"], CandidateSearchRequest(request_id=job["request_id"], expected_updated_at=row["updated_at"],
                    especialidad_id=resolution.get("especialidad_id")),
                origin="agente", user_id=None, session=session,
            )
            # Registrar la entrada posterior (tipo_id resuelto) evita otro intento
            # causado por la escritura del propio agente. Padrón se consulta vivo.
            after_hash = session.execute(text("SELECT " + INPUT_HASH + SOURCE + " WHERE r.id=:id"),
                                         {"id": str(job["id"])}).scalar_one()
            session.execute(text("""
                UPDATE reclamo_tareas_proveedores SET input_hash=:hash,estado=:state,reserva_token=null,reserva_hasta=null,
                    motivo=:reason,fuente=:source,modelo=:model,prompt_version=:prompt,actualizado_en=clock_timestamp()
                WHERE reclamo_id=:id
            """), {"id": str(job["id"]), "hash": after_hash,
                   "state": "completada" if result.resultado == "candidatos_encontrados" else "revision",
                   "reason": resolution["motivo"], "source": resolution["fuente"],
                   "model": resolution.get("modelo"), "prompt": resolution.get("prompt_version")})
            return result
