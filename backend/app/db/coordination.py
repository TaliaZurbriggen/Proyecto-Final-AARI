"""PostgresSaver y proyección de dominio en la misma transacción PostgreSQL."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import UUID, uuid4

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.agents.coordination.graph import build_coordination_graph
from app.agents.coordination.state import (
    CoordinationResponse, CoordinationSnapshot, DomainContext, EXPIRABLE_STAGES,
    ResumeRequest, TERMINAL_STAGES, stage_for,
)
from app.schemas.auth import AuthenticatedUser
from app.services.coordination_service import CoordinationError


# Mismo alcance de etapa que HU17: no proteger decisiones de otro pedido/actor
# ni filas históricas. Constante SQL interna, nunca entrada del cliente.
_CURRENT_PROVIDER_CHOICE = """ep.reclamo_id=r.id AND ep.estado='pendiente'
    AND ep.solicitud_responsable_en=rr.solicitado_en AND ep.actor_tipo=rr.actor_tipo
    AND ((r.tipo_gasto='ordinario' AND ep.actor_tipo='inquilino'
          AND r.estado='Pendiente de respuesta del responsable')
      OR (r.tipo_gasto='extraordinario' AND ep.actor_tipo='propietario'
          AND r.estado='Autorizado'))"""


class PostgresCoordinationRepository:
    """No hace setup/DDL al iniciar, ni toma decisiones por las otras HU."""

    def __init__(self, connection_factory=None, *, clock=None):
        self.connection_factory = connection_factory or self._connect
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _connect():
        from app.db.database import engine
        url = engine.url
        if url.get_backend_name() != "postgresql":
            raise RuntimeError("HU21 requiere PostgreSQL.")
        # Pasar parámetros, no imprimir ni reinterpretar una URL con credenciales.
        return psycopg.connect(
            host=url.host, port=url.port or 5432, dbname=url.database,
            user=url.username, password=url.password, row_factory=dict_row,
            prepare_threshold=None, connect_timeout=10, **dict(url.query),
        )

    @contextmanager
    def _transaction(self):
        with self.connection_factory() as conn:
            with conn.transaction():
                conn.execute("SET LOCAL search_path = aari_coordinacion, pg_catalog")
                conn.execute("SET LOCAL lock_timeout = '5s'")
                conn.execute("SET LOCAL statement_timeout = '15s'")
                yield conn

    @staticmethod
    def _has_provider_choices(conn):
        # HU21 sigue siendo desplegable antes de la migración/implementación HU17.
        return conn.execute("""
            SELECT to_regclass('public.reclamo_elecciones_proveedor') IS NOT NULL AS available
        """).fetchone()["available"]

    @staticmethod
    def _claim(conn, claim_id, user=None, *, lock=False):
        if user is not None:
            # Mismo orden que HU13: usuario -> reclamo -> sesión.
            account = conn.execute("""
                SELECT rol FROM public.usuarios
                WHERE id=%s AND activo AND NOT primer_ingreso FOR SHARE
            """, (user.id,)).fetchone()
            if not account or account["rol"] != user.rol:
                raise CoordinationError("La cuenta no está habilitada.", code="forbidden", status=403)
        choices = PostgresCoordinationRepository._has_provider_choices(conn)
        choice_deadline = "ep.respuesta_vence_en" if choices else "NULL::timestamptz"
        choice_join = ("LEFT JOIN public.reclamo_elecciones_proveedor ep ON "
                       + _CURRENT_PROVIDER_CHOICE) if choices else ""
        row = conn.execute(f"""
            SELECT r.id, r.numero, r.estado, r.tipo_gasto::text, r.propiedad_id,
                   r.inquilino_id, p.propietario_id, r.proveedor_seleccionado_id,
                   r.presupuesto_seleccionado_id, r.monto_seleccionado, r.fecha_visita,
                   r.operador_asignado_id, i.usuario_id AS tenant_user,
                   pr.usuario_id AS owner_user, rr.actor_tipo, rr.respuesta_vence_en,
                   {choice_deadline} AS eleccion_vence_en,
                   (SELECT c.id FROM public.cancelaciones c WHERE c.reclamo_id=r.id
                    ORDER BY c.timestamp DESC, c.id DESC LIMIT 1) AS cancelacion_id
            FROM public.reclamos r
            JOIN public.propiedades p ON p.id=r.propiedad_id
            JOIN public.inquilinos i ON i.id=r.inquilino_id
            JOIN public.propietarios pr ON pr.id=p.propietario_id
            LEFT JOIN public.reclamo_responsables rr ON rr.reclamo_id=r.id
            {choice_join}
            WHERE r.id=%s
        """ + (" FOR UPDATE OF r" if lock else ""), (claim_id,)).fetchone()
        if row is None or (user is not None and not (
            user.rol in {"administrador", "operador"}
            or user.rol == "inquilino" and row["tenant_user"] == user.id
            or user.rol == "propietario" and row["owner_user"] == user.id
        )):
            raise CoordinationError("El reclamo no está disponible.", code="not_found", status=404)
        return row

    @staticmethod
    def _domain(row):
        if row["tipo_gasto"] is None or row["actor_tipo"] is None:
            raise CoordinationError("El reclamo todavía no tiene una clasificación confirmada.")
        return DomainContext(
            reclamo_id=row["id"], estado=row["estado"], tipo_gasto=row["tipo_gasto"],
            actor_responsable=row["actor_tipo"], propiedad_id=row["propiedad_id"],
            inquilino_id=row["inquilino_id"], propietario_id=row["propietario_id"],
            proveedor_id=row["proveedor_seleccionado_id"],
            presupuesto_id=row["presupuesto_seleccionado_id"],
            monto=str(row["monto_seleccionado"]) if row["monto_seleccionado"] is not None else None,
            fecha_visita=row["fecha_visita"], cancelacion_id=row["cancelacion_id"],
            vencimiento_especifico=(row.get("eleccion_vence_en")
                                   or (row["respuesta_vence_en"]
                                       if row["estado"] == "Pendiente de respuesta del responsable" else None)),
        )

    @staticmethod
    def _session(conn, claim_id):
        return conn.execute("""
            SELECT * FROM public.sesiones_agente WHERE reclamo_id=%s FOR UPDATE
        """, (claim_id,)).fetchone()

    @staticmethod
    def _response(session, *, duplicate=False, domain=None):
        snapshot = CoordinationSnapshot.model_validate(session["estado_grafo"])
        if (snapshot.version != session["version"]
                or snapshot.intento_id != session["intento_id"]
                or snapshot.reclamo_id != session["reclamo_id"]):
            raise CoordinationError("El contexto requiere revisión por inconsistencia.")
        return CoordinationResponse(
            contexto=snapshot,
            ultima_actividad=session["ultima_actividad"], duplicado=duplicate,
            requiere_sincronizacion=domain is not None and domain != snapshot.dominio,
            estado_reclamo_actual=domain.estado if domain is not None else snapshot.dominio.estado,
        )

    def get(self, claim_id: UUID, user: AuthenticatedUser):
        with self._transaction() as conn:
            domain = self._domain(self._claim(conn, claim_id, user))
            row = conn.execute("SELECT * FROM public.sesiones_agente WHERE reclamo_id=%s",
                               (claim_id,)).fetchone()
            if not row or not row["estado_grafo"]:
                raise CoordinationError("Todavía no existe contexto de coordinación.",
                                        code="session_not_found", status=404)
            return self._response(row, domain=domain)  # GET/polling no renueva el plazo.

    def resume(self, claim_id: UUID, request: ResumeRequest, user: AuthenticatedUser):
        with self._transaction() as conn:
            claim = self._claim(conn, claim_id, user, lock=True)
            domain = self._domain(claim)
            if domain.tipo_gasto == "expensa":
                raise CoordinationError("Las expensas conservan el circuito de HU14.")
            session = self._session(conn, claim_id)
            fingerprint = hashlib.sha256(json.dumps({
                "reclamo": str(claim_id), "usuario": str(user.id),
                "request": request.model_dump(mode="json"),
            }, sort_keys=True).encode()).hexdigest()
            previous = conn.execute("""
                SELECT fingerprint FROM aari_coordinacion.eventos
                WHERE reclamo_id=%s AND evento_id=%s
            """, (claim_id, request.evento_id)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise CoordinationError("El identificador ya se usó para otra interacción.")
                return self._response(session, duplicate=True, domain=domain)
            version = session["version"] if session else 0
            if request.version_esperada != version:
                raise CoordinationError("El contexto cambió. Consultalo antes de continuar.")
            initialized = session is not None and bool(session["estado_grafo"])
            if initialized and request.intento_id != session["intento_id"]:
                raise CoordinationError("La respuesta pertenece a otro intento.")
            if not initialized and request.intento_id is not None:
                raise CoordinationError("No existe ese intento de coordinación.")
            stage = stage_for(domain)
            if stage in TERMINAL_STAGES | {"expirada", "intervencion_manual"}:
                raise CoordinationError("Esta etapa no permite retomar la coordinación.")
            # Reiniciar deliberadamente no borra cancelaciones ni decisiones.
            attempt = session["intento_id"] if session else uuid4()
            if initialized:
                old = CoordinationSnapshot.model_validate(session["estado_grafo"])
                recent = old.eventos_recientes
                if (old.dominio.cancelacion_id != domain.cancelacion_id
                        or session["estado_sesion"] != "activa"):
                    attempt = uuid4()
            else:
                recent = []
                if session is None:
                    conn.execute("""
                        INSERT INTO public.sesiones_agente (reclamo_id, intento_id)
                        VALUES (%s, %s)
                    """, (claim_id, attempt))
            snapshot = CoordinationSnapshot(
                reclamo_id=claim_id, intento_id=attempt, version=version+1,
                etapa=stage, dominio=domain, eventos_recientes=recent,
            )
            result = self._checkpoint(conn, snapshot, request.evento_id)
            conn.execute("""
                INSERT INTO aari_coordinacion.eventos
                    (reclamo_id, evento_id, usuario_id, fingerprint, version, intento_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (claim_id, request.evento_id, user.id, fingerprint, version+1, attempt))
            row = conn.execute("""
                UPDATE public.sesiones_agente
                SET estado_grafo=%s, version=%s, intento_id=%s,
                    ultima_actividad=%s, estado_sesion='activa'
                WHERE reclamo_id=%s RETURNING *
            """, (Jsonb(result), version+1, attempt, self.clock(), claim_id)).fetchone()
            return self._response(row)

    @staticmethod
    def _checkpoint(conn, snapshot, event_id):
        saver = PostgresSaver(conn)
        graph = build_coordination_graph(saver)
        config = {"configurable": {"thread_id": str(snapshot.reclamo_id)}}
        result = graph.invoke({
            "dominio": snapshot.dominio.model_dump(mode="json"),
            "contexto": snapshot.model_dump(mode="json"), "evento_id": str(event_id),
        }, config, durability="sync")
        return CoordinationSnapshot.model_validate(result["contexto"]).model_dump(mode="json")

    def expire_due(self, *, limit=20):
        now = self.clock()
        count = 0
        with self._transaction() as conn:
            # Dejar todo vencimiento de la etapa HU17 (también si ya pasó) a su
            # job específico. Excluir antes de LIMIT evita bloquear otros casos.
            choice_filter = ""
            if self._has_provider_choices(conn):
                choice_filter = f"""AND NOT EXISTS (
                    SELECT 1 FROM public.reclamo_elecciones_proveedor ep
                    JOIN public.reclamo_responsables rr ON rr.reclamo_id=ep.reclamo_id
                    WHERE {_CURRENT_PROVIDER_CHOICE}
                )"""
            # Bloquear primero el reclamo, igual que retomar y el outbox.
            candidates = conn.execute(f"""
                SELECT r.id FROM public.reclamos r
                JOIN public.sesiones_agente s ON s.reclamo_id=r.id
                WHERE s.estado_sesion='activa' AND s.ultima_actividad <= %s
                  AND s.version > 0 AND s.estado_grafo <> '{{}}'::jsonb
                  AND r.estado IN ('Clasificado','Autorizado')
                  {choice_filter}
                ORDER BY s.ultima_actividad, r.id
                LIMIT %s FOR UPDATE OF r SKIP LOCKED
            """, (now-timedelta(hours=72), max(1, min(limit, 100)))).fetchall()
            for candidate in candidates:
                claim = self._claim(conn, candidate["id"])
                session = self._session(conn, claim["id"])
                # Las filas legadas vacías se inicializan sólo mediante resume().
                if (not session or not session["estado_grafo"] or session["version"] <= 0
                        or session["estado_sesion"] != "activa"
                        or session["ultima_actividad"] > now-timedelta(hours=72)):
                    continue
                domain = self._domain(claim)
                if (domain.tipo_gasto == "expensa"
                        or domain.vencimiento_especifico is not None
                        or stage_for(domain) not in EXPIRABLE_STAGES):
                    continue
                snapshot = CoordinationSnapshot.model_validate(session["estado_grafo"])
                operator = conn.execute("""
                    SELECT id, rol, email FROM public.usuarios
                    WHERE activo AND NOT primer_ingreso
                      AND rol IN ('operador','administrador')
                    ORDER BY (id=%s) DESC NULLS LAST, (rol='operador') DESC, id
                    LIMIT 1 FOR SHARE SKIP LOCKED
                """, (claim["operador_asignado_id"],)).fetchone()
                # Sin receptor habilitado no declarar un escalado atendido.
                if not operator:
                    continue
                conn.execute("SELECT set_config('app.origen_reclamo', 'sistema', true)")
                conn.execute("SELECT set_config('app.usuario_reclamo', '', true)")
                conn.execute("UPDATE public.reclamos SET estado='Sesión expirada' WHERE id=%s",
                             (claim["id"],))
                expired = domain.model_copy(update={"estado": "Sesión expirada"})
                snapshot = snapshot.model_copy(update={
                    "version": session["version"]+1, "dominio": expired, "etapa": "expirada",
                })
                result = self._checkpoint(conn, snapshot, uuid4())
                conn.execute("""
                    UPDATE public.sesiones_agente SET estado_grafo=%s, version=%s,
                        estado_sesion='expirada' WHERE reclamo_id=%s
                """, (Jsonb(result), snapshot.version, claim["id"]))
                conn.execute("""
                    INSERT INTO public.notificaciones (
                        reclamo_id, destinatario_tipo, destinatario_contacto, canal,
                        asunto, mensaje, estado_reclamo, tipo_evento, clave_idempotencia,
                        estado_envio, proximo_intento_en
                    ) VALUES (%s,%s,%s,'email',%s,%s,'Sesión expirada',
                              'alerta_operador',%s,'pendiente',%s)
                    ON CONFLICT (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL
                    DO NOTHING
                """, (
                    claim["id"], operator["rol"], operator["email"],
                    f"AARI - Sesión expirada #{claim['numero']:06d}",
                    "La coordinación agotó 72 horas sin interacción válida. Requiere revisión manual.",
                    f"hu21:{session['id']}:{session['intento_id']}:expiracion", now,
                ))
                count += 1
        return count
