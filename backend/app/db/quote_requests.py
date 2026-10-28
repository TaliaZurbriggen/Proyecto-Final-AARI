"""Outbox HU19. Nunca hace HTTP ni altera decisiones/estados del reclamo."""

from contextlib import contextmanager
import json
from uuid import uuid4

from sqlalchemy import bindparam, text

from app.core.whatsapp import canonical_recipient
from app.db.proveedores import SqlAlchemyProveedoresRepository
from app.schemas.proveedores import normalize_words
from app.schemas.quote_requests import QuotePreparation, QuoteReservation
from app.services.quote_requests import TEMPLATE_VERSION, quote_message, request_content


SOURCE = """ FROM public.reclamos r
    JOIN public.propiedades p ON p.id=r.propiedad_id
    JOIN public.inquilinos i ON i.id=r.inquilino_id
    JOIN public.propietarios pr ON pr.id=p.propietario_id
    JOIN public.reclamo_responsables rr ON rr.reclamo_id=r.id
    JOIN public.reclamo_elecciones_proveedor ep ON ep.reclamo_id=r.id
        AND ep.solicitud_responsable_en=rr.solicitado_en AND ep.actor_tipo=rr.actor_tipo
    LEFT JOIN public.usuarios u ON u.id=ep.usuario_id
    LEFT JOIN public.reclamo_autorizaciones a ON a.reclamo_id=r.id
        AND a.solicitado_en=rr.solicitado_en AND a.usuario_id=ep.usuario_id
"""
ELIGIBLE = """r.estado='Pendiente de asignación'
    AND r.proveedor_seleccionado_id IS NULL AND r.presupuesto_seleccionado_id IS NULL
    AND ep.estado='decidida' AND ep.tipo_proveedor='fidelizado'
    AND ep.siguiente_paso='solicitar_presupuestos' AND ep.decidido_en < ep.respuesta_vence_en
    AND u.activo AND NOT u.primer_ingreso
    AND i.estado='activo' AND i.propiedad_id=p.id
    AND ((r.tipo_gasto='ordinario' AND rr.actor_tipo='inquilino' AND u.rol='inquilino' AND i.usuario_id=u.id)
      OR (r.tipo_gasto='extraordinario' AND rr.actor_tipo='propietario' AND u.rol='propietario'
          AND pr.usuario_id=u.id AND a.decision='autorizar' AND a.estado='Autorizado'))"""
COLUMNS = """r.id,r.descripcion,r.tipo_id,r.tipo_gasto::text AS tipo_gasto,
    r.propiedad_id,r.inquilino_id,p.propietario_id,p.direccion,p.provincia,p.localidad,p.barrio,
    p.piso,p.numero AS unidad,ep.id AS eleccion_id,ep.usuario_id"""


class SqlAlchemyQuoteRequests:
    def __init__(self, session_factory=None, *, scope_claim_id=None):
        if session_factory is None:
            from app.db.database import SessionLocal
            session_factory = SessionLocal
        self.session_factory = session_factory
        # Puerto de QA interno, no parámetro de una ruta pública.
        self.scope_claim_id = scope_claim_id

    @contextmanager
    def transaction(self):
        with self.session_factory.begin() as session:
            session.execute(text("SET LOCAL lock_timeout='5s'"))
            session.execute(text("SET LOCAL statement_timeout='15s'"))
            yield session

    @staticmethod
    def _eligible(session, claim_id):
        return session.execute(text("SELECT " + COLUMNS + SOURCE + " WHERE r.id=:id AND " + ELIGIBLE),
                               {"id": str(claim_id)}).mappings().one_or_none()

    @staticmethod
    def _candidates(session, row):
        if not row["tipo_id"] or not row["provincia"] or not row["localidad"]:
            return []
        return SqlAlchemyProveedoresRepository.candidate_ids(session, specialty_id=row["tipo_id"],
            **{key: normalize_words(row[key]) if row[key] else None for key in ("provincia", "localidad", "barrio")})

    @staticmethod
    def _event(session, request_id, kind, *, token=None, reason=None):
        session.execute(text("""INSERT INTO public.solicitud_presupuesto_eventos
            (solicitud_id,tipo,intento_id,motivo) VALUES (:id,:kind,:token,:reason)"""),
            {"id": str(request_id), "kind": kind, "token": str(token) if token else None, "reason": reason})

    def prepare(self, claim_id):
        with self.transaction() as session:
            # Mismo orden para preparar, reservar y despachar: reclamo -> outbox.
            session.execute(text("SELECT id FROM public.reclamos WHERE id=:id FOR UPDATE"), {"id": str(claim_id)})
            row = self._eligible(session, claim_id)
            if row is None:
                return QuotePreparation(None, 0, reason="reclamo_no_habilitado")
            existing = session.execute(text("""SELECT id FROM public.reclamo_rondas_presupuesto
                WHERE eleccion_id=:choice"""), {"choice": row["eleccion_id"]}).scalar_one_or_none()
            if existing:
                count = session.execute(text("SELECT count(*) FROM public.proveedor_solicitudes_presupuesto WHERE ronda_id=:id"),
                                        {"id": existing}).scalar_one()
                return QuotePreparation(existing, count, repeated=True)
            content, digest = request_content(row)
            candidates = self._candidates(session, row)
            round_id = uuid4()
            reason = None if candidates else "sin_candidatos_vigentes"
            result = "preparada" if candidates else "sin_candidatos"
            session.execute(text("""INSERT INTO public.reclamo_rondas_presupuesto
                (id,reclamo_id,eleccion_id,huella,contexto,resultado,motivo)
                VALUES (:id,:claim,:choice,:digest,CAST(:content AS jsonb),:result,:reason)"""),
                {"id": round_id, "claim": claim_id, "choice": row["eleccion_id"], "digest": digest,
                 "content": json.dumps(content, ensure_ascii=False), "result": result, "reason": reason})
            if not candidates:
                return QuotePreparation(round_id, 0, reason=reason)
            providers = session.execute(text("SELECT id,telefono FROM public.proveedores WHERE id IN :ids ORDER BY id")
                .bindparams(bindparam("ids", expanding=True)), {"ids": candidates}).mappings().all()
            requests, events = [], []
            for provider in providers:
                request_id = uuid4()
                parameters, message = quote_message(request_id, content)
                try:
                    recipient = canonical_recipient(provider["telefono"])
                except ValueError:
                    # No inventar un prefijo internacional para datos históricos.
                    continue
                requests.append({"id": request_id, "round": round_id, "claim": claim_id,
                    "provider": provider["id"], "recipient": recipient, "parameters": json.dumps(parameters, ensure_ascii=False),
                    "message": message, "version": TEMPLATE_VERSION})
                events.append({"id": request_id})
            if requests:
                session.execute(text("""INSERT INTO public.proveedor_solicitudes_presupuesto
                    (id,ronda_id,reclamo_id,proveedor_id,destinatario,parametros,mensaje,version_plantilla)
                    VALUES (:id,:round,:claim,:provider,:recipient,CAST(:parameters AS jsonb),:message,:version)"""), requests)
                session.execute(text("INSERT INTO public.solicitud_presupuesto_eventos (solicitud_id,tipo) VALUES (:id,'preparada')"), events)
            else:
                session.execute(text("UPDATE public.reclamo_rondas_presupuesto SET resultado='revision',motivo='contactos_invalidos' WHERE id=:id"),
                                {"id": round_id})
            return QuotePreparation(round_id, len(requests), reason="contactos_invalidos" if not requests else None)

    def discover(self, limit=20):
        limit = max(1, min(int(limit), 100))
        with self.transaction() as session:
            scope = " AND r.id=:scope" if self.scope_claim_id else ""
            rows = session.execute(text("SELECT r.id " + SOURCE + " WHERE " + ELIGIBLE + """
                AND NOT EXISTS (SELECT 1 FROM public.reclamo_rondas_presupuesto rp WHERE rp.eleccion_id=ep.id)
                """ + scope + " ORDER BY ep.decidido_en,r.id LIMIT :limit"),
                {"limit": limit, "scope": self.scope_claim_id}).scalars().all()
        results = [self.prepare(claim_id) for claim_id in rows]
        return sum(1 for result in results if result.round_id is not None and not result.repeated)

    def reserve_one(self, *, recipients):
        if not recipients:
            return None
        with self.transaction() as session:
            scope = " AND r.id=:scope" if self.scope_claim_id else ""
            row = session.execute(text("""SELECT q.* FROM public.proveedor_solicitudes_presupuesto q
                JOIN public.reclamos r ON r.id=q.reclamo_id
                JOIN public.reclamo_rondas_presupuesto rp ON rp.id=q.ronda_id
                WHERE q.estado='pendiente' AND q.destinatario IN :recipients
                AND rp.cerrada_en IS NULL
                AND (rp.respuesta_vence_en IS NULL OR rp.respuesta_vence_en > clock_timestamp())
                """ + scope + " ORDER BY q.creado_en,q.id LIMIT 1 FOR UPDATE OF r,q SKIP LOCKED")
                .bindparams(bindparam("recipients", expanding=True)),
                {"recipients": recipients, "scope": self.scope_claim_id}).mappings().one_or_none()
            if row is None:
                return None
            token = uuid4()
            session.execute(text("""UPDATE public.proveedor_solicitudes_presupuesto SET estado='reservada',
                reserva_token=:token,reserva_hasta=clock_timestamp()+interval '60 seconds',actualizado_en=clock_timestamp()
                WHERE id=:id"""), {"id": row["id"], "token": token})
            self._event(session, row["id"], "reservada", token=token)
            return QuoteReservation(row["id"], row["reclamo_id"], token, row["destinatario"], tuple(row["parametros"]))

    @staticmethod
    def _job(session, job):
        session.execute(text("SELECT id FROM public.reclamos WHERE id=:id FOR UPDATE"), {"id": job.claim_id})
        return session.execute(text("""SELECT q.*,rp.huella,rp.eleccion_id,rp.cerrada_en,
            (rp.respuesta_vence_en IS NULL OR rp.respuesta_vence_en>clock_timestamp()) AS ronda_vigente,
            q.reserva_hasta > clock_timestamp() AS vigente FROM public.proveedor_solicitudes_presupuesto q
            JOIN public.reclamo_rondas_presupuesto rp ON rp.id=q.ronda_id
            WHERE q.id=:id AND q.reclamo_id=:claim FOR UPDATE OF q"""),
            {"id": job.id, "claim": job.claim_id}).mappings().one_or_none()

    def begin_send(self, job, *, template_name, language, waba_id, phone_id):
        with self.transaction() as session:
            current = self._job(session, job)
            if (not current or current["estado"] != "reservada" or current["reserva_token"] != job.token
                    or not current["vigente"] or not current["ronda_vigente"] or current["cerrada_en"] is not None):
                return False
            row = self._eligible(session, job.claim_id)
            valid = row is not None and row["eleccion_id"] == current["eleccion_id"]
            if valid:
                _, digest = request_content(row)
                valid = digest == current["huella"] and current["proveedor_id"] in self._candidates(session, row)
            phone = session.execute(text("SELECT telefono FROM public.proveedores WHERE id=:id"),
                                    {"id": current["proveedor_id"]}).scalar_one_or_none()
            try:
                valid = valid and canonical_recipient(phone) == current["destinatario"]
            except ValueError:
                valid = False
            # El payload sale de la copia durable, no de un dato modificado por el llamador.
            valid = valid and job.recipient == current["destinatario"] and job.parameters == tuple(current["parametros"])
            if not valid:
                session.execute(text("""UPDATE public.proveedor_solicitudes_presupuesto SET estado='omitida',
                    motivo='datos_o_habilitacion_cambiaron',reserva_hasta=null,actualizado_en=clock_timestamp()
                    WHERE id=:id"""), {"id": job.id})
                self._event(session, job.id, "omitida", token=job.token, reason="datos_o_habilitacion_cambiaron")
                return False
            session.execute(text("""UPDATE public.proveedor_solicitudes_presupuesto SET estado='enviando',
                intentos=1,intento_en=clock_timestamp(),reserva_hasta=clock_timestamp()+interval '60 seconds',
                plantilla_meta=:template,idioma=:language,waba_id=:waba,telefono_id=:phone,actualizado_en=clock_timestamp()
                WHERE id=:id"""), {"id": job.id, "template": template_name, "language": language, "waba": waba_id, "phone": phone_id})
            self._event(session, job.id, "enviando", token=job.token)
            return True

    def finish(self, job, *, outcome, message_id=None):
        if outcome not in {"aceptada", "rechazada", "desconocida"}:
            raise ValueError("Resultado no soportado.")
        if outcome == "aceptada" and (not isinstance(message_id, str) or not 1 <= len(message_id) <= 512):
            raise ValueError("Falta el identificador de Meta.")
        with self.transaction() as session:
            current = self._job(session, job)
            if (not current or current["reserva_token"] != job.token
                    or current["estado"] not in {"enviando", "desconocida"}):
                return False
            if current["estado"] == outcome:  # repetir una finalización no duplica eventos.
                return True
            session.execute(text("""UPDATE public.proveedor_solicitudes_presupuesto SET estado=:outcome,
                mensaje_externo_id=:external,aceptado_en=CASE WHEN :outcome='aceptada' THEN clock_timestamp() ELSE NULL END,
                reserva_hasta=NULL,motivo=:reason,actualizado_en=clock_timestamp() WHERE id=:id"""),
                {"id": job.id, "outcome": outcome, "external": message_id,
                 "reason": None if outcome == "aceptada" else "requiere_revision_sin_reenvio_automatico"})
            self._event(session, job.id, outcome, token=job.token)
            if outcome == "aceptada":
                session.execute(text("""UPDATE public.proveedor_solicitudes_presupuesto
                    SET respuesta_vence_en=aceptado_en+interval '24 hours' WHERE id=:id"""), {"id": job.id})
                # Cada proveedor conserva sus 24 h completas desde la aceptación de Meta.
                # El cierre de la ronda no vence antes que la última solicitud aceptada.
                session.execute(text("""UPDATE public.reclamo_rondas_presupuesto SET
                    iniciada_en=coalesce(iniciada_en,clock_timestamp()),
                    respuesta_vence_en=greatest(respuesta_vence_en,
                        (SELECT respuesta_vence_en FROM public.proveedor_solicitudes_presupuesto WHERE id=:id)),
                    recepcion_estado=CASE WHEN cerrada_en IS NULL THEN 'esperando' ELSE recepcion_estado END
                    WHERE id=:round AND cerrada_en IS NULL"""), {"id": job.id, "round": current["ronda_id"]})
            return True

    def recover_expired(self, limit=20):
        with self.transaction() as session:
            scope = " AND r.id=:scope" if self.scope_claim_id else ""
            rows = session.execute(text("""SELECT q.id,q.estado,q.reserva_token FROM public.proveedor_solicitudes_presupuesto q
                JOIN public.reclamos r ON r.id=q.reclamo_id WHERE q.estado IN ('reservada','enviando')
                AND q.reserva_hasta <= clock_timestamp() """ + scope + """
                ORDER BY q.reserva_hasta,q.id LIMIT :limit FOR UPDATE OF r,q SKIP LOCKED"""),
                {"limit": max(1, min(int(limit), 100)), "scope": self.scope_claim_id}).mappings().all()
            for row in rows:
                started = row["estado"] == "enviando"
                state = "desconocida" if started else "pendiente"
                session.execute(text("""UPDATE public.proveedor_solicitudes_presupuesto SET estado=:state,
                    reserva_hasta=NULL,reserva_token=CASE WHEN :state='pendiente' THEN NULL ELSE reserva_token END,
                    motivo=:reason,actualizado_en=clock_timestamp() WHERE id=:id"""),
                    {"id": row["id"], "state": state, "reason": "intento_interrumpido" if started else "reserva_sin_envio"})
                self._event(session, row["id"], "desconocida" if started else "reserva_liberada",
                            token=row["reserva_token"], reason="intento_interrumpido" if started else "reserva_sin_envio")
            return len(rows)
