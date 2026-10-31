"""HU18: registro y derivación atómicos, auditados por elección vigente."""

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.db.quote_portal import SqlAlchemyQuotePortal
from app.db.quote_requests import COLUMNS as QUOTE_COLUMNS, SOURCE as QUOTE_SOURCE
from app.schemas.external_providers import ExternalProviderDetail, ExternalProviderRecord, ExternalProviderResult
from app.services.external_providers_service import ExternalProviderError, registration_reason
from app.services.quote_requests import request_content


SOURCE = """
    FROM reclamos r JOIN propiedades p ON p.id=r.propiedad_id
    JOIN inquilinos i ON i.id=r.inquilino_id JOIN propietarios pr ON pr.id=p.propietario_id
    JOIN usuarios u ON u.id=:user AND u.activo AND NOT u.primer_ingreso AND u.rol::text=:role
    LEFT JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
    LEFT JOIN reclamo_elecciones_proveedor ep ON ep.reclamo_id=r.id
        AND ep.solicitud_responsable_en=rr.solicitado_en AND ep.actor_tipo=rr.actor_tipo
    WHERE r.id=:id AND (:role='administrador' OR (ep.usuario_id=u.id AND (
        (:role='inquilino' AND i.usuario_id=u.id AND i.id=:profile AND i.estado='activo'
         AND i.propiedad_id=p.id AND r.tipo_gasto='ordinario' AND rr.actor_tipo='inquilino')
        OR (:role='propietario' AND pr.usuario_id=u.id AND pr.id=:profile
            AND r.tipo_gasto='extraordinario' AND rr.actor_tipo='propietario'
            AND EXISTS (SELECT 1 FROM reclamo_autorizaciones a WHERE a.reclamo_id=r.id
                AND a.solicitado_en=rr.solicitado_en AND a.usuario_id=u.id
                AND a.decision='autorizar' AND a.estado='Autorizado')))))
"""
COLUMNS = """r.id AS reclamo_id,r.numero,r.descripcion,r.estado,r.updated_at,
    r.proveedor_seleccionado_id,r.presupuesto_seleccionado_id,
    ep.id AS eleccion_id,ep.estado AS eleccion_estado,ep.tipo_proveedor,
    CASE WHEN ep.actor_tipo='inquilino' THEN i.nombre_completo ELSE pr.nombre_completo END AS actor_nombre,
    p.id AS propiedad_id,p.direccion,p.provincia,p.localidad,p.barrio,p.tipo::text AS propiedad_tipo,
    p.piso,p.numero AS propiedad_numero"""


class SqlAlchemyExternalProvidersRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    @staticmethod
    def _params(claim_id, user):
        if (user.rol not in {"administrador", "inquilino", "propietario"} or user.primer_ingreso
                or (user.rol != "administrador" and user.perfil_id is None)):
            raise ExternalProviderError("Tu cuenta no puede acceder a este registro.", status=403, code="forbidden")
        return {"id": str(claim_id), "user": str(user.id), "role": user.rol,
                "profile": str(user.perfil_id) if user.perfil_id else None}

    @staticmethod
    def _row(session, params):
        row = session.execute(text("SELECT " + COLUMNS + SOURCE), params).mappings().one_or_none()
        if row is None:
            raise ExternalProviderError("No encontramos ese reclamo para tu cuenta.", status=404, code="not_found")
        return dict(row)

    @staticmethod
    def _records(session, row, user):
        scope = "" if user.rol == "administrador" else " AND eleccion_id=:choice AND usuario_id=:user"
        return session.execute(text("SELECT * FROM proveedores_externos WHERE reclamo_id=:id" + scope
            + " ORDER BY created_at DESC,id DESC"),
            {"id": row["reclamo_id"], "choice": row["eleccion_id"], "user": user.id}).mappings().all()

    @staticmethod
    def _round(session, row):
        result = session.execute(text("""SELECT rp.id,rp.huella,rp.estado AS ronda_estado,
            (SELECT count(*) FROM presupuestos b JOIN aari_solicitudes_presupuesto q
                ON q.id=b.solicitud_aari_id WHERE q.ronda_id=rp.id) AS presupuestos_disponibles
            FROM aari_rondas_presupuesto rp WHERE rp.eleccion_id=:choice"""),
            {"choice": row["eleccion_id"]}).mappings().one_or_none()
        row.update(dict(result) if result else {"ronda_estado": None, "presupuestos_disponibles": 0})
        if result and row["tipo_proveedor"] == "fidelizado":
            current = session.execute(text("SELECT " + QUOTE_COLUMNS + QUOTE_SOURCE
                + " WHERE r.id=:id AND ep.id=:choice"),
                {"id": row["reclamo_id"], "choice": row["eleccion_id"]}).mappings().one_or_none()
            if current is None or request_content(current)[1] != result["huella"]:
                row.update(ronda_estado=None, presupuestos_disponibles=0)
        return result

    def get(self, claim_id, user):
        with self.session_factory.begin() as session:
            row = self._row(session, self._params(claim_id, user))
            self._round(session, row)
            records = [ExternalProviderRecord.model_validate(dict(record)) for record in self._records(session, row, user)]
            current = next((record for record in records if record.eleccion_id == row["eleccion_id"]), None)
            reason = ("La inmobiliaria consulta los datos. Sólo el responsable registra el contacto."
                      if user.rol == "administrador" else registration_reason(row, registered=current is not None))
            return ExternalProviderDetail(
                **{key: row[key] for key in ("reclamo_id", "numero", "descripcion", "estado", "eleccion_id", "updated_at")},
                propiedad={"id": row["propiedad_id"], "direccion": row["direccion"], "provincia": row["provincia"],
                    "localidad": row["localidad"], "barrio": row["barrio"], "tipo": row["propiedad_tipo"],
                    "piso": row["piso"], "numero": row["propiedad_numero"]},
                puede_registrar=reason is None, motivo_bloqueo=reason, registro=current, registros=records,
            )

    def register(self, claim_id, user, request):
        if user.rol == "administrador":
            raise ExternalProviderError("Sólo el responsable puede registrar el proveedor.", status=403, code="forbidden")
        try:
            return self._register(claim_id, user, request)
        except IntegrityError:
            raise ExternalProviderError("El registro cambió o el identificador ya fue utilizado. Actualizá la pantalla.") from None

    def _register(self, claim_id, user, request):
        params = self._params(claim_id, user)
        with self.session_factory.begin() as session:
            session.execute(text("SET LOCAL lock_timeout='5s'"))
            session.execute(text("SET LOCAL statement_timeout='15s'"))
            # Orden compartido con HU17: cuenta -> perfil -> propiedad -> reclamo -> elección.
            account = session.execute(text("""SELECT id FROM usuarios WHERE id=:user AND rol::text=:role
                AND activo AND NOT primer_ingreso FOR SHARE"""), params).scalar_one_or_none()
            if account is None:
                raise ExternalProviderError("Tu cuenta ya no está habilitada.", status=403, code="forbidden")
            table = "inquilinos" if user.rol == "inquilino" else "propietarios"
            session.execute(text(f"SELECT id FROM {table} WHERE id=:profile AND usuario_id=:user FOR SHARE"), params).all()
            session.execute(text("SELECT p.id FROM propiedades p JOIN reclamos r ON r.propiedad_id=p.id WHERE r.id=:id FOR SHARE OF p"), params).all()
            session.execute(text("SELECT id FROM reclamos WHERE id=:id FOR UPDATE"), params).all()
            row = self._row(session, params)
            session.execute(text("SELECT id FROM reclamo_elecciones_proveedor WHERE id=:choice FOR UPDATE"),
                            {"choice": row["eleccion_id"]}).all()
            if row["eleccion_id"] != request.eleccion_id:
                raise ExternalProviderError("La elección cambió. Actualizá la pantalla antes de continuar.")
            previous = session.execute(text("SELECT * FROM proveedores_externos WHERE request_id=:request"),
                                       {"request": request.request_id}).mappings().one_or_none()
            if previous:
                if any(previous[key] != value for key, value in {
                    "reclamo_id": claim_id, "eleccion_id": request.eleccion_id, "usuario_id": user.id,
                    "nombre": request.nombre, "telefono": request.telefono,
                    "expected_updated_at": request.expected_updated_at,
                }.items()):
                    raise ExternalProviderError("El identificador ya fue usado con otros datos.")
                return ExternalProviderResult(reclamo_id=claim_id, estado="Derivado a proveedor externo",
                    registro=ExternalProviderRecord.model_validate(dict(previous)), repetida=True)
            self._round(session, row)
            existing = self._records(session, row, user)
            reason = registration_reason(row, registered=bool(existing))
            if reason:
                raise ExternalProviderError(reason)
            if row["updated_at"] != request.expected_updated_at:
                raise ExternalProviderError("El reclamo cambió. Actualizá la pantalla antes de confirmar.")
            for key, value in (("app.origen_reclamo", user.rol), ("app.usuario_reclamo", str(user.id)),
                               ("app.omitir_notificacion_inquilino", "false")):
                session.execute(text("SELECT set_config(:key,:value,true)"), {"key": key, "value": value})
            session.execute(text("UPDATE reclamos SET estado='Derivado a proveedor externo' WHERE id=:id"), params)
            history = session.execute(text("""SELECT id FROM reclamo_historial_estados WHERE reclamo_id=:id
                AND estado_nuevo='Derivado a proveedor externo' AND usuario_id=:user
                ORDER BY timestamp DESC,id DESC LIMIT 1"""), params).scalar_one()
            saved = session.execute(text("""INSERT INTO proveedores_externos
                (reclamo_id,propiedad_id,nombre,telefono,eleccion_id,usuario_id,actor_nombre,
                 request_id,expected_updated_at,historial_estado_id,created_at)
                VALUES (:id,:property,:name,:phone,:choice,:user,:actor,:request,:expected,:history,clock_timestamp())
                RETURNING *"""), {**params, "property": row["propiedad_id"], "name": request.nombre,
                    "phone": request.telefono, "choice": request.eleccion_id, "actor": row["actor_nombre"],
                    "request": request.request_id, "expected": request.expected_updated_at, "history": history}).mappings().one()
            self._cancel_rounds(session, claim_id, request.eleccion_id)
            return ExternalProviderResult(reclamo_id=claim_id, estado="Derivado a proveedor externo",
                registro=ExternalProviderRecord.model_validate(dict(saved)))

    @staticmethod
    def _cancel_rounds(session, claim_id, choice_id):
        rounds = session.execute(text("""UPDATE aari_rondas_presupuesto SET estado='cancelada',
            cerrada_en=coalesce(cerrada_en,clock_timestamp())
            WHERE reclamo_id=:id AND eleccion_id=:choice AND estado<>'cancelada'
            RETURNING id"""), {"id": claim_id, "choice": choice_id}).scalars().all()
        for round_id in rounds:
            SqlAlchemyQuotePortal._event(session, round_id, "cancelada")
        session.execute(text("""UPDATE notificaciones SET estado_envio='fallido',proximo_intento_en=NULL,
            bloqueado_hasta=NULL,ultimo_error='Derivación a proveedor externo; aviso obsoleto.'
            WHERE reclamo_id=:id AND estado_envio IN ('pendiente','procesando') AND
              (id IN (SELECT q.aviso_id FROM aari_solicitudes_presupuesto q WHERE q.reclamo_id=:id)
               OR clave_idempotencia LIKE 'aari-quote:%')"""), {"id": claim_id})
