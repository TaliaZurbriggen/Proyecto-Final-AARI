"""Consumo transaccional HU19: inbox, presupuesto y aviso se confirman juntos."""

from datetime import timedelta

from sqlalchemy import bindparam, text

from app.core.whatsapp import canonical_recipient
from app.db.quote_requests import SqlAlchemyQuoteRequests
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.services.quote_requests import request_content
from app.services.quote_response_parser import QuoteNeedsReview, parse_quote, references


class SqlAlchemyQuoteResponses(SqlAlchemyQuoteRequests):
    @staticmethod
    def _record(session, event_id, result, reason, *, request_id=None, quote_id=None):
        session.execute(text("""INSERT INTO public.presupuesto_respuestas
            (mensaje_entrada_id,solicitud_id,presupuesto_id,resultado,motivo)
            VALUES (:event,:request,:quote,:result,:reason)"""),
            {"event": event_id, "request": request_id, "quote": quote_id, "result": result, "reason": reason})

    @staticmethod
    def _notify(session, row, *, operator=False, reason="presupuestos_disponibles"):
        if operator:
            recipient = SqlAlchemyClaimsRepository._operator_recipient(session, assigned_operator_id=row["operador_asignado_id"])
            if not recipient:
                return False
            role, contact, channel = recipient["rol"], recipient["email"], "email"
        else:
            recipient = session.execute(text("""SELECT ep.actor_tipo,
                CASE WHEN ep.actor_tipo='inquilino' THEN i.email ELSE pr.email END AS email,
                CASE WHEN ep.actor_tipo='inquilino' THEN i.telefono ELSE pr.telefono END AS telefono,
                CASE WHEN ep.actor_tipo='inquilino' THEN i.canal_notificacion ELSE pr.canal_notificacion END AS canal
                FROM public.reclamo_elecciones_proveedor ep
                JOIN public.reclamos r ON r.id=ep.reclamo_id
                JOIN public.inquilinos i ON i.id=r.inquilino_id
                JOIN public.propiedades p ON p.id=r.propiedad_id
                JOIN public.propietarios pr ON pr.id=p.propietario_id WHERE ep.id=:choice"""),
                {"choice": row["eleccion_id"]}).mappings().one()
            role, channel = recipient["actor_tipo"], recipient["canal"]
            contact = recipient["email"]
            if channel == "whatsapp":
                try:
                    contact = canonical_recipient(recipient["telefono"])
                except ValueError:
                    return False
        if not contact:
            return False
        message = ("Hay al menos un presupuesto disponible para revisar. No se seleccionó ni contrató un proveedor."
                   if not operator else "La ronda de presupuestos requiere intervención de la inmobiliaria: " + reason + ".")
        category = ("cierre" if reason in {"sin_presupuestos_recibidos", "envios_incompletos_o_fallidos"} else "revision") if operator else "disponibles"
        result = session.execute(text("""INSERT INTO public.notificaciones
            (reclamo_id,destinatario_tipo,destinatario_contacto,canal,asunto,mensaje,
             estado_reclamo,tipo_evento,clave_idempotencia,estado_envio,proximo_intento_en)
            VALUES (:claim,:role,:contact,:channel,:subject,:message,:state,:kind,:key,'pendiente',clock_timestamp())
            ON CONFLICT (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL DO NOTHING"""),
            {"claim": row["reclamo_id"], "role": role, "contact": contact, "channel": channel,
             "subject": f"AARI - Reclamo #{row['numero']:06d}: presupuestos", "message": message,
             "state": row["estado_reclamo"], "kind": "alerta_operador" if operator else "estado_reclamo",
             "key": f"hu19:{row['ronda_id']}:{category}"})
        return result.rowcount > 0

    @staticmethod
    def _valid_round(session, request):
        row = SqlAlchemyQuoteRequests._eligible(session, request["reclamo_id"])
        if row is None or row["eleccion_id"] != request["eleccion_id"]:
            return False
        return request_content(row)[1] == request["huella"]

    @staticmethod
    def _valid_context(session, request):
        if not SqlAlchemyQuoteResponses._valid_round(session, request):
            return False
        provider = session.execute(text("SELECT activo,telefono FROM public.proveedores WHERE id=:id"),
                                   {"id": request["proveedor_id"]}).mappings().one_or_none()
        try:
            return bool(provider and provider["activo"] and canonical_recipient(provider["telefono"]) == request["destinatario"])
        except ValueError:
            return False

    @staticmethod
    def _request(session, request_id):
        return session.execute(text("""SELECT q.*,rp.eleccion_id,rp.huella,rp.cerrada_en,
            r.numero,r.estado AS estado_reclamo,r.operador_asignado_id
            FROM public.proveedor_solicitudes_presupuesto q
            JOIN public.reclamo_rondas_presupuesto rp ON rp.id=q.ronda_id
            JOIN public.reclamos r ON r.id=q.reclamo_id WHERE q.id=:id FOR UPDATE OF q"""),
            {"id": request_id}).mappings().one()

    def process_one(self, event_id):
        with self.transaction() as session:
            event = session.execute(text("SELECT * FROM public.whatsapp_eventos_entrada WHERE id=:id"),
                                    {"id": event_id}).mappings().one_or_none()
            if event is None:
                return False
            # Referencia explícita o respuesta al mensaje original; nunca sólo el teléfono.
            data = event["datos"]
            refs = references(data.get("text", "")) if event["tipo_evento"] == "mensaje" else set()
            context = data.get("context_message_id") if event["tipo_evento"] == "mensaje" else event["mensaje_externo_id"]
            filters = []
            params = {"waba": event["waba_id"], "phone": event["telefono_id"], "sender": event["participante"], "context": context}
            if context:
                filters.append("q.mensaje_externo_id=:context")
            if refs:
                filters.append("q.id IN :references")
                params["references"] = list(refs)
            candidates = []
            if filters:
                statement = text("""SELECT q.id,q.reclamo_id,q.mensaje_externo_id
                    FROM public.proveedor_solicitudes_presupuesto q WHERE q.waba_id=:waba
                    AND q.telefono_id=:phone AND q.destinatario=:sender AND (""" + " OR ".join(filters) + ")")
                if refs:
                    statement = statement.bindparams(bindparam("references", expanding=True))
                candidates = session.execute(statement, params).mappings().all()
            candidate = candidates[0] if len(candidates) == 1 else None
            # Reclamo -> solicitud -> inbox, igual que despacho y vencimiento. No locks de red.
            if candidate:
                session.execute(text("SELECT id FROM public.reclamos WHERE id=:id FOR UPDATE"), {"id": candidate["reclamo_id"]})
                request = self._request(session, candidate["id"])
            else:
                request = None
            event = session.execute(text("SELECT * FROM public.whatsapp_eventos_entrada WHERE id=:id FOR UPDATE"),
                                    {"id": event_id}).mappings().one()
            if session.execute(text("SELECT 1 FROM public.presupuesto_respuestas WHERE mensaje_entrada_id=:id"),
                               {"id": event_id}).scalar_one_or_none():
                return False
            # El webhook puede adelantarse al commit del ID de Meta. Esperar el
            # intento en curso no equivale a inferir una asociación por teléfono.
            if request is None or request["estado"] == "enviando":
                sending = session.execute(text("""SELECT 1 FROM public.proveedor_solicitudes_presupuesto
                    WHERE waba_id=:waba AND telefono_id=:phone AND destinatario=:sender
                    AND estado='enviando' AND reserva_hasta>clock_timestamp() LIMIT 1"""), params).scalar_one_or_none()
                if sending:
                    return False
            def record(result, reason, *, quote_id=None):
                self._record(session, event_id, result, reason,
                             request_id=request["id"] if request else None, quote_id=quote_id)
                if result == "revision" and request and self._valid_round(session, request):
                    self._notify(session, request, operator=True, reason=reason)
                return True
            if not request:
                return record("revision", "sin_correlacion_univoca")
            if refs and (len(refs) != 1 or request["id"] not in refs):
                return record("revision", "referencias_contradictorias")
            if context and request["mensaje_externo_id"] != context:
                return record("revision", "referencias_contradictorias")
            if event["tipo_evento"] == "estado":
                if event["subtipo"] == "failed":
                    session.execute(text("""UPDATE public.proveedor_solicitudes_presupuesto
                        SET entrega_fallida_en=coalesce(entrega_fallida_en,:when) WHERE id=:id"""),
                        {"id": request["id"], "when": event["ocurrido_en"]})
                    if self._valid_round(session, request):
                        self._notify(session, request, operator=True, reason="fallo_entrega_whatsapp")
                return record("ignorada", "estado_de_transporte_no_es_presupuesto")
            if event["estado"] == "no_soportado" or event["subtipo"] != "text":
                return record("revision", "mensaje_no_textual")
            if request["estado"] != "aceptada" or request["respuesta_vence_en"] is None:
                return record("revision", "envio_no_confirmado")
            if request["cerrada_en"] is not None or event["recibido_en"] > request["respuesta_vence_en"] or event["ocurrido_en"] > request["respuesta_vence_en"]:
                return record("tardia", "fuera_del_plazo")
            if (event["ocurrido_en"] < request["intento_en"] - timedelta(minutes=5)
                    or event["ocurrido_en"] > event["recibido_en"] + timedelta(minutes=5)):
                return record("revision", "fecha_inconsistente")
            if not self._valid_context(session, request):
                return record("revision", "contexto_del_reclamo_cambio")
            if session.execute(text("SELECT 1 FROM public.presupuestos WHERE solicitud_presupuesto_id=:id"),
                               {"id": request["id"]}).scalar_one_or_none():
                return record("revision", "presupuesto_ya_registrado_no_sobrescribir")
            try:
                quote = parse_quote(data["text"])
            except QuoteNeedsReview as error:
                return record("revision", str(error))
            quote_id = session.execute(text("""INSERT INTO public.presupuestos
                (reclamo_id,proveedor_id,monto,moneda,descripcion,recibido_en,solicitud_presupuesto_id,mensaje_entrada_id)
                VALUES (:claim,:provider,:amount,:currency,:description,:received,:request,:event) RETURNING id"""),
                {"claim": request["reclamo_id"], "provider": request["proveedor_id"], "amount": quote.amount,
                 "currency": quote.currency, "description": quote.description, "received": event["recibido_en"],
                 "request": request["id"], "event": event_id}).scalar_one()
            record("aceptada", "presupuesto_valido", quote_id=quote_id)
            if not self._notify(session, request):
                # El aviso puede existir ya; una clave distinta sólo se usa si falta contacto.
                exists = session.execute(text("SELECT 1 FROM public.notificaciones WHERE clave_idempotencia=:key"),
                    {"key": f"hu19:{request['ronda_id']}:disponibles"}).scalar_one_or_none()
                if not exists:
                    self._notify(session, request, operator=True, reason="contacto_responsable_no_disponible")
            return True

    def process_pending(self, *, limit=100):
        with self.transaction() as session:
            ids = session.execute(text("""SELECT e.id FROM public.whatsapp_eventos_entrada e
                WHERE NOT EXISTS (SELECT 1 FROM public.presupuesto_respuestas pr WHERE pr.mensaje_entrada_id=e.id)
                ORDER BY e.recibido_en,e.id LIMIT :limit"""), {"limit": max(1, min(int(limit), 100))}).scalars().all()
        return sum(self.process_one(event_id) for event_id in ids)

    def finalize_due(self, *, limit=20):
        with self.transaction() as session:
            scope = " AND rp.reclamo_id=:scope" if self.scope_claim_id else ""
            rows = session.execute(text("""SELECT rp.id,rp.reclamo_id FROM public.reclamo_rondas_presupuesto rp
                WHERE rp.cerrada_en IS NULL AND (rp.respuesta_vence_en <= clock_timestamp()
                    OR (rp.respuesta_vence_en IS NULL AND EXISTS (
                        SELECT 1 FROM public.proveedor_solicitudes_presupuesto q WHERE q.ronda_id=rp.id AND q.intentos=1)
                    AND NOT EXISTS (SELECT 1 FROM public.proveedor_solicitudes_presupuesto q
                        WHERE q.ronda_id=rp.id AND q.estado IN ('pendiente','reservada','enviando'))))""" + scope + """
                ORDER BY rp.respuesta_vence_en,rp.id LIMIT :limit"""),
                {"limit": max(1, min(int(limit), 100)), "scope": self.scope_claim_id}).mappings().all()
        return sum(self.finalize_one(row["id"], row["reclamo_id"]) for row in rows)

    def finalize_one(self, round_id, claim_id):
        with self.transaction() as session:
            session.execute(text("SELECT id FROM public.reclamos WHERE id=:id FOR UPDATE"), {"id": claim_id})
            row = session.execute(text("""SELECT rp.*,rp.id AS ronda_id,r.numero,r.estado AS estado_reclamo,r.operador_asignado_id
                FROM public.reclamo_rondas_presupuesto rp JOIN public.reclamos r ON r.id=rp.reclamo_id
                WHERE rp.id=:id AND rp.reclamo_id=:claim FOR UPDATE OF rp"""),
                {"id": round_id, "claim": claim_id}).mappings().one_or_none()
            now = session.execute(text("SELECT clock_timestamp()")).scalar_one()
            if not row or row["cerrada_en"] or (row["respuesta_vence_en"] and now < row["respuesta_vence_en"]):
                return False
            if row["respuesta_vence_en"] is None:
                ready = session.execute(text("""SELECT count(*) FILTER (WHERE intentos=1)>0
                    AND count(*) FILTER (WHERE estado IN ('pendiente','reservada','enviando'))=0
                    FROM public.proveedor_solicitudes_presupuesto WHERE ronda_id=:id"""),
                    {"id": round_id}).scalar_one()
                if not ready:
                    return False
            # No cerrar antes de consumir mensajes ya confirmados en la bandeja.
            pending = session.execute(text("""SELECT 1 FROM public.whatsapp_eventos_entrada e
                JOIN public.proveedor_solicitudes_presupuesto q ON q.ronda_id=:id AND q.waba_id=e.waba_id
                    AND q.telefono_id=e.telefono_id AND q.destinatario=e.participante
                WHERE e.recibido_en<=q.respuesta_vence_en
                AND NOT EXISTS (SELECT 1 FROM public.presupuesto_respuestas pr WHERE pr.mensaje_entrada_id=e.id)
                LIMIT 1"""), {"id": round_id}).scalar_one_or_none()
            if pending:
                return False
            if not self._valid_round(session, row):
                state = "cancelada"
            else:
                counts = session.execute(text("""SELECT count(p.id) AS quotes,
                    count(*) FILTER (WHERE q.estado<>'aceptada' OR q.entrega_fallida_en IS NOT NULL) AS uncertain
                    FROM public.proveedor_solicitudes_presupuesto q
                    LEFT JOIN public.presupuestos p ON p.solicitud_presupuesto_id=q.id WHERE q.ronda_id=:id"""),
                    {"id": round_id}).mappings().one()
                state = "disponibles" if counts["quotes"] else ("revision" if counts["uncertain"] else "sin_presupuestos")
                if state == "disponibles":
                    self._notify(session, row)
                else:
                    if state == "sin_presupuestos":
                        session.execute(text("SELECT set_config('app.origen_reclamo','agente',true)"))
                        session.execute(text("UPDATE public.reclamos SET estado='Sin presupuestos recibidos' WHERE id=:id"), {"id": claim_id})
                    self._notify(session, {**dict(row), "estado_reclamo": "Sin presupuestos recibidos" if state == "sin_presupuestos" else row["estado_reclamo"]},
                                 operator=True, reason="sin_presupuestos_recibidos" if state == "sin_presupuestos" else "envios_incompletos_o_fallidos")
            session.execute(text("UPDATE public.reclamo_rondas_presupuesto SET recepcion_estado=:state,cerrada_en=:now WHERE id=:id"),
                            {"id": round_id, "state": state, "now": now})
            return True
