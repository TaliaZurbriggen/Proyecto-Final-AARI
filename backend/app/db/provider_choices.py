"""HU17: elección y enrutamiento auditados dentro de una transacción."""

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.agents.provider_choice import provider_choice_graph
from app.db.database import SessionLocal
from app.schemas.provider_choices import ProviderChoiceDetail, ProviderChoiceResult
from app.services.provider_choices_service import (
    ProviderChoiceConflict, ProviderChoiceForbidden, ProviderChoiceNotFound,
    can_choose, ensure_choice_allowed,
)


SOURCE = """
    FROM reclamos r
    JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
    JOIN reclamo_elecciones_proveedor ep ON ep.reclamo_id=r.id
        AND ep.solicitud_responsable_en=rr.solicitado_en AND ep.actor_tipo=rr.actor_tipo
    JOIN propiedades p ON p.id=r.propiedad_id
    JOIN inquilinos i ON i.id=r.inquilino_id
    JOIN propietarios pr ON pr.id=p.propietario_id
    JOIN usuarios u ON u.id=:user AND u.activo AND NOT u.primer_ingreso
    WHERE r.id=:id AND (
        (:role='inquilino' AND u.rol='inquilino' AND i.usuario_id=u.id AND i.id=:profile
         AND i.estado='activo' AND i.propiedad_id=p.id
         AND r.tipo_gasto='ordinario' AND rr.actor_tipo='inquilino')
        OR (:role='propietario' AND u.rol='propietario' AND pr.usuario_id=u.id AND pr.id=:profile
            AND r.tipo_gasto='extraordinario' AND rr.actor_tipo='propietario')
    )
"""
COLUMNS = """r.id AS reclamo_id,r.numero,r.descripcion,r.estado,r.updated_at,
    r.tipo_gasto::text AS tipo_gasto,ep.id AS solicitud_id,ep.actor_tipo,
    ep.estado AS solicitud_estado,ep.solicitado_en,ep.respuesta_vence_en,
    ep.tipo_proveedor,ep.estado_resultante,ep.siguiente_paso,ep.decidido_en,
    ep.actor_nombre,ep.request_id,ep.usuario_id,ep.expected_updated_at,
    CASE WHEN ep.actor_tipo='inquilino' THEN i.nombre_completo ELSE pr.nombre_completo END AS nombre_actual,
    p.id AS propiedad_id,p.direccion,p.provincia,p.localidad,p.barrio,
    p.tipo::text AS propiedad_tipo,p.piso,p.numero AS propiedad_numero"""


def choice_result(row, *, repeated=False):
    return ProviderChoiceResult(
        reclamo_id=row["reclamo_id"], solicitud_id=row["solicitud_id"],
        tipo_proveedor=row["tipo_proveedor"], estado=row["estado_resultante"],
        siguiente_paso=row["siguiente_paso"], decidido_en=row["decidido_en"],
        actor_nombre=row["actor_nombre"], repetida=repeated,
    )


class SqlAlchemyProviderChoicesRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    @staticmethod
    def _params(claim_id, user):
        if user.rol not in {"inquilino", "propietario"} or user.primer_ingreso:
            raise ProviderChoiceForbidden
        return {"id": str(claim_id), "user": str(user.id), "profile": str(user.perfil_id), "role": user.rol}

    @staticmethod
    def _row(session, params, *, lock=False):
        row = session.execute(text("SELECT " + COLUMNS + SOURCE
            + (" FOR UPDATE OF rr,ep" if lock else "")), params).mappings().one_or_none()
        if row is None:
            raise ProviderChoiceNotFound
        return row

    def get(self, claim_id, user):
        with self.session_factory.begin() as session:
            row = self._row(session, self._params(claim_id, user))
            now = session.execute(text("SELECT clock_timestamp()")).scalar_one()
            return ProviderChoiceDetail(
                **{k: row[k] for k in ("reclamo_id", "numero", "descripcion", "estado", "updated_at",
                    "actor_tipo", "solicitud_id", "solicitado_en", "respuesta_vence_en")},
                propiedad={"id": row["propiedad_id"], "direccion": row["direccion"],
                    "provincia": row["provincia"], "localidad": row["localidad"], "barrio": row["barrio"],
                    "tipo": row["propiedad_tipo"], "piso": row["piso"], "numero": row["propiedad_numero"]},
                puede_elegir=can_choose(row, now),
                decision=choice_result(row) if row["solicitud_estado"] == "decidida" else None,
            )

    def choose(self, claim_id, user, request):
        try:
            return self._choose(claim_id, user, request)
        except IntegrityError as error:
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint == "reclamo_elecciones_proveedor_request_id_key":
                raise ProviderChoiceConflict("El identificador ya se usó para otra elección.") from error
            raise

    def _choose(self, claim_id, user, request):
        params = self._params(claim_id, user)
        with self.session_factory.begin() as session:
            actor = session.execute(text("""
                SELECT id FROM usuarios WHERE id=:user AND rol::text=:role
                  AND activo AND NOT primer_ingreso FOR SHARE
            """), params).scalar_one_or_none()
            if actor is None:
                raise ProviderChoiceForbidden
            table = "inquilinos" if user.rol == "inquilino" else "propietarios"
            profile = session.execute(text(f"SELECT id FROM {table} WHERE id=:profile AND usuario_id=:user FOR SHARE"),
                                      params).scalar_one_or_none()
            if profile is None:
                raise ProviderChoiceNotFound
            # Orden común: cuenta -> perfil -> propiedad -> reclamo -> solicitud.
            session.execute(text("SELECT p.id FROM propiedades p JOIN reclamos r ON r.propiedad_id=p.id "
                                 "WHERE r.id=:id FOR SHARE OF p"), params).all()
            session.execute(text("SELECT id FROM reclamos WHERE id=:id FOR UPDATE"), params).all()
            row = self._row(session, params, lock=True)
            previous = session.execute(text("""
                SELECT *,id AS solicitud_id FROM reclamo_elecciones_proveedor WHERE request_id=:request
            """), {"request": str(request.request_id)}).mappings().one_or_none()
            if previous:
                if (str(previous["reclamo_id"]) != str(claim_id)
                        or str(previous["solicitud_id"]) != str(request.solicitud_id)
                        or previous["tipo_proveedor"] != request.tipo_proveedor
                        or previous["expected_updated_at"] != request.expected_updated_at
                        or str(previous["usuario_id"]) != str(user.id)):
                    raise ProviderChoiceConflict("El identificador ya se usó para otra elección.")
                return choice_result(previous, repeated=True)
            now = session.execute(text("SELECT clock_timestamp()")).scalar_one()
            ensure_choice_allowed(row, request, now)
            routed = provider_choice_graph.invoke({"tipo_proveedor": request.tipo_proveedor})
            state = routed["estado_resultante"]
            for setting, value in (("app.origen_reclamo", user.rol), ("app.usuario_reclamo", str(user.id)),
                                   ("app.omitir_notificacion_inquilino", "false")):
                session.execute(text("SELECT set_config(:setting,:value,true)"), {"setting": setting, "value": value})
            session.execute(text("UPDATE reclamos SET estado=:state WHERE id=:id"), {**params, "state": state})
            history = session.execute(text("""
                SELECT id FROM reclamo_historial_estados WHERE reclamo_id=:id AND estado_nuevo=:state
                  AND usuario_id=:user ORDER BY timestamp DESC,id DESC LIMIT 1
            """), {**params, "state": state}).scalar_one()
            saved = session.execute(text("""
                UPDATE reclamo_elecciones_proveedor SET estado='decidida',request_id=:request,
                    expected_updated_at=:expected,usuario_id=:user,actor_nombre=:name,
                    tipo_proveedor=:choice,decidido_en=:now,estado_resultante=:state,
                    siguiente_paso=:next,historial_estado_id=:history
                WHERE id=:solicitud RETURNING *,id AS solicitud_id
            """), {**params, "request": str(request.request_id), "expected": request.expected_updated_at,
                   "name": row["nombre_actual"], "choice": request.tipo_proveedor, "now": now,
                   "state": state, "next": routed["siguiente_paso"], "history": str(history),
                   "solicitud": str(request.solicitud_id)}).mappings().one()
            session.execute(text("""
                UPDATE notificaciones SET estado_envio='fallido',proximo_intento_en=NULL,bloqueado_hasta=NULL,
                    ultimo_error='Elección finalizada; aviso obsoleto.'
                WHERE reclamo_id=:id AND estado_envio IN ('pendiente','procesando')
                  AND (solicitud_tipo_proveedor_id=:solicitud
                    OR (destinatario_tipo='inquilino' AND tipo_evento IN
                        ('responsable_inicial','responsable_recordatorio')))
            """), {**params, "solicitud": str(request.solicitud_id)})
            return choice_result(saved)
