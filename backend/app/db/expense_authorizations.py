"""HU16: decisión, auditoría y avisos en una única transacción PostgreSQL."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.schemas.expense_authorizations import (
    ExpenseDecisionResult, OwnerExpenseClaim, OwnerExpenseClaimsPage,
)
from app.services.expense_authorizations_service import (
    ExpenseAuthorizationConflict, ExpenseAuthorizationForbidden,
    ExpenseAuthorizationNotFound, can_decide, ensure_decision_allowed,
)


SOURCE = """
    FROM reclamos r
    JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
    JOIN propiedades p ON p.id=r.propiedad_id
    JOIN propietarios pr ON pr.id=p.propietario_id
    JOIN usuarios u ON u.id=pr.usuario_id
    WHERE pr.id=:profile AND u.id=:user AND u.activo AND NOT u.primer_ingreso
      AND u.rol='propietario' AND r.tipo_gasto='extraordinario'
      AND rr.actor_tipo='propietario'
"""
COLUMNS = """r.id, r.numero, r.descripcion, r.estado, r.updated_at,
    r.tipo_gasto::text AS tipo_gasto, r.fundamento_clasificacion AS fundamento,
    r.operador_asignado_id, rr.actor_tipo, rr.solicitado_en, rr.respuesta_vence_en,
    p.id AS propiedad_id, p.direccion, p.provincia, p.localidad, p.barrio,
    p.tipo::text AS propiedad_tipo, p.piso, p.numero AS propiedad_numero,
    pr.nombre_completo AS propietario_nombre"""


def decision_result(row, *, repeated=False):
    return ExpenseDecisionResult(
        reclamo_id=row["reclamo_id"], decision=row["decision"], estado=row["estado"],
        decidido_en=row["decidido_en"], propietario_nombre=row["propietario_nombre"],
        repetida=repeated,
        siguiente_paso="eleccion_proveedor_pendiente" if row["decision"] == "autorizar" else "cerrado",
    )


class SqlAlchemyExpenseAuthorizationsRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    @staticmethod
    def _params(user):
        return {"user": str(user.id), "profile": str(user.perfil_id)}

    @staticmethod
    def _row(session, claim_id, params, *, lock=False):
        row = session.execute(text("SELECT " + COLUMNS + SOURCE + " AND r.id=:id"
                                  + (" FOR UPDATE OF r, rr" if lock else "")),
                              {**params, "id": str(claim_id)}).mappings().one_or_none()
        if row is None:
            raise ExpenseAuthorizationNotFound
        return row

    @staticmethod
    def _detail(session, row):
        now = session.execute(text("SELECT clock_timestamp()")).scalar_one()
        decision = session.execute(text("""
            SELECT * FROM reclamo_autorizaciones WHERE reclamo_id=:id
              AND solicitado_en=:requested ORDER BY decidido_en DESC LIMIT 1
        """), {"id": str(row["id"]), "requested": row["solicitado_en"]}).mappings().one_or_none()
        history = session.execute(text("""
            SELECT estado_anterior, estado_nuevo, origen, timestamp
            FROM reclamo_historial_estados WHERE reclamo_id=:id ORDER BY timestamp,id
        """), {"id": str(row["id"])}).mappings().all()
        return OwnerExpenseClaim(
            **{k: row[k] for k in ("id", "numero", "descripcion", "estado", "fundamento",
                                  "updated_at", "solicitado_en", "respuesta_vence_en")},
            propiedad={"id": row["propiedad_id"], "direccion": row["direccion"],
                       "provincia": row["provincia"], "localidad": row["localidad"],
                       "barrio": row["barrio"], "tipo": row["propiedad_tipo"],
                       "piso": row["piso"], "numero": row["propiedad_numero"]},
            puede_decidir=can_decide(state=row["estado"], expense=row["tipo_gasto"],
                                    actor=row["actor_tipo"], deadline=row["respuesta_vence_en"], now=now),
            decision=decision_result(decision) if decision else None,
            historial=[dict(h) for h in history],
        )

    def get(self, claim_id, user):
        with self.session_factory.begin() as session:
            return self._detail(session, self._row(session, claim_id, self._params(user)))

    def list(self, user, *, page=1):
        params = self._params(user)
        with self.session_factory.begin() as session:
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            total = session.execute(text("SELECT count(*) " + SOURCE), params).scalar_one()
            rows = session.execute(text("SELECT " + COLUMNS + SOURCE + """
                ORDER BY (r.estado='Pendiente de respuesta del responsable') DESC,
                         rr.solicitado_en DESC, r.id LIMIT 20 OFFSET :offset
            """), {**params, "offset": (page-1)*20}).mappings().all()
            return OwnerExpenseClaimsPage(items=[self._detail(session, r) for r in rows],
                                         page=page, total=total, total_pages=max(1, (total+19)//20))

    def decide(self, claim_id, user, request, *, decision):
        try:
            return self._decide(claim_id, user, request, decision=decision)
        except IntegrityError as error:
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint in {"reclamo_autorizaciones_pkey", "uq_autorizacion_solicitud"}:
                raise ExpenseAuthorizationConflict("Ya se registró una decisión para esta solicitud.") from error
            raise

    def _decide(self, claim_id, user, request, *, decision):
        if decision not in {"autorizar", "rechazar"}:
            raise ExpenseAuthorizationConflict("La decisión no es válida.")
        params = self._params(user)
        with self.session_factory.begin() as session:
            actor = session.execute(text("""
                SELECT id FROM usuarios WHERE id=:user AND rol='propietario'
                  AND activo AND NOT primer_ingreso FOR SHARE
            """), params).scalar_one_or_none()
            if actor is None:
                raise ExpenseAuthorizationForbidden
            profile = session.execute(text("""
                SELECT id FROM propietarios WHERE id=:profile AND usuario_id=:user FOR SHARE
            """), params).scalar_one_or_none()
            if profile is None:
                raise ExpenseAuthorizationNotFound
            # Mantener la titularidad estable hasta confirmar la decisión.
            property_id = session.execute(text("""
                SELECT p.id FROM propiedades p JOIN reclamos r ON r.propiedad_id=p.id
                WHERE r.id=:id AND p.propietario_id=:profile FOR SHARE OF p
            """), {**params, "id": str(claim_id)}).scalar_one_or_none()
            if property_id is None:
                raise ExpenseAuthorizationNotFound
            row = self._row(session, claim_id, params, lock=True)
            previous = session.execute(text("""
                SELECT * FROM reclamo_autorizaciones WHERE request_id=:request
            """), {"request": str(request.request_id)}).mappings().one_or_none()
            if previous:
                if (str(previous["reclamo_id"]) != str(claim_id)
                        or previous["decision"] != decision
                        or previous["expected_updated_at"] != request.expected_updated_at
                        or str(previous["usuario_id"]) != str(user.id)):
                    raise ExpenseAuthorizationConflict("El identificador ya se usó para otra decisión.")
                return decision_result(previous, repeated=True)
            now = session.execute(text("SELECT clock_timestamp()")).scalar_one()
            ensure_decision_allowed(row, request.expected_updated_at, now)
            state = "Autorizado" if decision == "autorizar" else "Rechazado por propietario"
            for setting, value in (("app.origen_reclamo", "propietario"),
                                   ("app.usuario_reclamo", str(user.id)),
                                   ("app.omitir_notificacion_inquilino", "false")):
                session.execute(text("SELECT set_config(:setting, :value, true)"),
                                {"setting": setting, "value": value})
            session.execute(text("UPDATE reclamos SET estado=:state WHERE id=:id"),
                            {"id": str(claim_id), "state": state})
            history = session.execute(text("""
                SELECT id FROM reclamo_historial_estados
                WHERE reclamo_id=:id AND estado_nuevo=:state AND usuario_id=:user
                ORDER BY timestamp DESC,id DESC LIMIT 1
            """), {"id": str(claim_id), "state": state, "user": str(user.id)}).scalar_one()
            saved = session.execute(text("""
                INSERT INTO reclamo_autorizaciones (reclamo_id,request_id,solicitado_en,
                    expected_updated_at,usuario_id,propietario_nombre,decision,estado,
                    historial_estado_id,decidido_en)
                VALUES (:id,:request,:requested,:expected,:user,:name,:decision,:state,:history,:now)
                RETURNING *
            """), {"id": str(claim_id), "request": str(request.request_id),
                   "requested": row["solicitado_en"], "expected": request.expected_updated_at,
                   "user": str(user.id), "name": row["propietario_nombre"],
                   "decision": decision, "state": state, "history": str(history), "now": now}).mappings().one()
            # No volver a pedir autorización/recordar después de una decisión.
            session.execute(text("""
                UPDATE notificaciones SET estado_envio='fallido',
                    ultimo_error='Pedido de autorización finalizado; aviso obsoleto.',
                    proximo_intento_en=NULL, bloqueado_hasta=NULL
                WHERE reclamo_id=:id AND tipo_evento IN
                    ('responsable_inicial','responsable_recordatorio','responsable_vencido')
                  AND estado_envio IN ('pendiente','procesando')
            """), {"id": str(claim_id)})
            operator = SqlAlchemyClaimsRepository._operator_recipient(
                session, assigned_operator_id=row["operador_asignado_id"])
            if operator:
                session.execute(text("""
                    INSERT INTO notificaciones (reclamo_id,destinatario_tipo,
                        destinatario_contacto,canal,asunto,mensaje,estado_reclamo,
                        historial_estado_id,tipo_evento,clave_idempotencia,
                        estado_envio,proximo_intento_en)
                    VALUES (:id,:role,:email,'email',:subject,:message,:state,
                            :history,'alerta_operador',:key,'pendiente',CURRENT_TIMESTAMP)
                    ON CONFLICT (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL DO NOTHING
                """), {"id": str(claim_id), "role": operator["rol"], "email": operator["email"],
                       "subject": f"AARI - Decisión en reclamo #{row['numero']:06d}",
                       "message": f"El propietario registró su decisión: {state}. Reclamo #{row['numero']:06d}.",
                       "state": state, "history": str(history), "key": f"{history}:decision:operador"})
            return decision_result(saved)
