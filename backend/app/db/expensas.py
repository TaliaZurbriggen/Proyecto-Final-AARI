"""HU14: snapshot transaccional, consultas privadas y notas append-only."""

from datetime import UTC, datetime, time, timedelta
import json
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.db.database import SessionLocal
from app.schemas.expensas import ExpenseDetail, ExpenseListItem, ExpenseNote, ExpensePage, ExpenseReport
from app.schemas.reclamos import ClaimPropertyContext
from app.services.expense_notifications import CONFIGURATION_ERROR, agency_email, expense_message, expense_subject


class ExpenseNotFoundError(Exception):
    pass


class ExpenseNotePermissionError(Exception):
    pass


def enqueue_expense_report(session, report: ExpenseReport, contact: object) -> UUID | None:
    """Debe ejecutarse dentro de la misma transacción que confirma clasificación."""
    claim_id = str(report.reclamo_id)
    existing = session.execute(text("""
        SELECT notificacion_id FROM reclamo_derivaciones_expensa WHERE reclamo_id=:id
    """), {"id": claim_id}).mappings().one_or_none()
    if existing is not None:
        return UUID(str(existing["notificacion_id"])) if existing["notificacion_id"] else None
    recipient = agency_email(contact)
    notification_id = None
    if recipient:
        notification_id = session.execute(text("""
            INSERT INTO notificaciones (reclamo_id, destinatario_tipo, destinatario_contacto,
                canal, asunto, mensaje, estado_reclamo, tipo_evento, clave_idempotencia,
                estado_envio, proximo_intento_en)
            VALUES (:id, 'inmobiliaria', :recipient, 'email', :subject, :message,
                'Pendiente de respuesta del responsable', 'expensa_reporte', :key,
                'pendiente', CURRENT_TIMESTAMP)
            RETURNING id
        """), {"id": claim_id, "recipient": recipient, "subject": expense_subject(report),
               "message": expense_message(report), "key": f"{claim_id}:expensa_reporte"}).scalar_one()
    session.execute(text("""
        INSERT INTO reclamo_derivaciones_expensa (reclamo_id, reporte, notificacion_id, error_configuracion)
        VALUES (:id, CAST(:report AS JSONB), :notification, :error)
    """), {"id": claim_id, "report": report.model_dump_json(), "notification": notification_id,
           "error": None if recipient else CONFIGURATION_ERROR})
    return UUID(str(notification_id)) if notification_id else None


PROPERTY_COLUMNS = """
    p.id AS propiedad_id, p.direccion, p.provincia, p.localidad, p.barrio,
    CAST(p.tipo AS TEXT) AS propiedad_tipo, p.piso, p.numero AS propiedad_numero
"""
SOURCE = """
    FROM reclamos r JOIN propiedades p ON p.id=r.propiedad_id
    LEFT JOIN reclamo_derivaciones_expensa d ON d.reclamo_id=r.id
    LEFT JOIN notificaciones n ON n.id=d.notificacion_id
"""
COLUMNS = """
    r.id, r.numero, r.descripcion, r.estado, r.creado_en,
    d.reporte, d.error_configuracion, d.reclamo_id AS derivacion_id,
    n.estado_envio, n.intentos, n.ultimo_error,
""" + PROPERTY_COLUMNS
TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def property_from_row(row):
    return ClaimPropertyContext(id=row["propiedad_id"], direccion=row["direccion"],
        provincia=row["provincia"], localidad=row["localidad"], barrio=row["barrio"],
        tipo=row["propiedad_tipo"], piso=row["piso"], numero=row["propiedad_numero"])


def list_item(row):
    status = ("historico" if not row["derivacion_id"] else
              "configuracion_pendiente" if row["error_configuracion"] else row["estado_envio"])
    return ExpenseListItem(id=row["id"], numero=row["numero"], descripcion=row["descripcion"],
        estado=row["estado"], creado_en=row["creado_en"], propiedad=property_from_row(row),
        entrega_estado=status, intentos=row["intentos"] or 0,
        error_entrega=row["error_configuracion"] or row["ultimo_error"])


class SqlAlchemyExpensesRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def list(self, filters) -> ExpensePage:
        clauses = ["r.tipo_gasto='expensa'"]
        params = {}
        if filters.propiedad_id:
            clauses.append("r.propiedad_id=:property_id")
            params["property_id"] = str(filters.propiedad_id)
        if filters.fecha_desde:
            clauses.append("r.creado_en>=:since")
            params["since"] = datetime.combine(filters.fecha_desde, time.min, TZ).astimezone(UTC)
        if filters.fecha_hasta:
            clauses.append("r.creado_en<:until")
            params["until"] = datetime.combine(filters.fecha_hasta + timedelta(days=1), time.min, TZ).astimezone(UTC)
        base_where = " AND ".join(clauses)
        scopes = {
            "derivados": "r.estado='Derivado a inmobiliaria (expensa)'",
            "pendientes": "n.estado_envio IN ('pendiente','procesando')",
            "fallidos": "(n.estado_envio='fallido' OR d.error_configuracion IS NOT NULL)",
            "historicos": "d.reclamo_id IS NULL",
        }
        if filters.situacion in scopes:
            clauses.append(scopes[filters.situacion])
        where = " AND ".join(clauses)
        with self.session_factory() as session:
            total = session.execute(text("SELECT COUNT(*) " + SOURCE + " WHERE " + where), params).scalar_one()
            rows = session.execute(text("SELECT " + COLUMNS + SOURCE + " WHERE " + where
                + " ORDER BY r.creado_en DESC, r.numero DESC LIMIT 20 OFFSET :offset"),
                {**params, "offset": (filters.page-1)*20}).mappings().all()
            counts = session.execute(text("""
                SELECT COALESCE(SUM(CASE WHEN n.estado_envio IN ('pendiente','procesando') THEN 1 ELSE 0 END),0) AS pendientes,
                       COALESCE(SUM(CASE WHEN n.estado_envio='fallido' THEN 1 ELSE 0 END),0) AS fallidos,
                       COALESCE(SUM(CASE WHEN d.error_configuracion IS NOT NULL THEN 1 ELSE 0 END),0) AS sin_configuracion
            """ + SOURCE + " WHERE " + base_where), params).mappings().one()
            properties = session.execute(text("SELECT DISTINCT " + PROPERTY_COLUMNS
                + " FROM reclamos r JOIN propiedades p ON p.id=r.propiedad_id"
                + " WHERE r.tipo_gasto='expensa' ORDER BY p.direccion, p.id")).mappings().all()
        return ExpensePage(items=[list_item(row) for row in rows], total=total,
            page=filters.page, total_pages=max(1,(total+19)//20),
            propiedades=[property_from_row(row) for row in properties], **dict(counts))

    @staticmethod
    def _row(session, claim_id):
        row = session.execute(text("SELECT " + COLUMNS + SOURCE
            + " WHERE r.id=:id AND r.tipo_gasto='expensa'"), {"id": str(claim_id)}).mappings().one_or_none()
        if row is None:
            raise ExpenseNotFoundError
        return row

    def get(self, claim_id) -> ExpenseDetail:
        with self.session_factory() as session:
            row = self._row(session, claim_id)
            deliveries = session.execute(text("""
                SELECT id, canal, destinatario_contacto AS destinatario, estado_envio AS estado,
                       intentos, enviado_en, created_at AS creado_en, ultimo_error AS error
                FROM notificaciones WHERE reclamo_id=:id AND destinatario_tipo='inmobiliaria'
                ORDER BY created_at DESC, id DESC
            """), {"id": str(claim_id)}).mappings().all()
            notes = session.execute(text("""
                SELECT ni.id, ni.contenido, ni.usuario_id, ni.created_at AS creado_en,
                       COALESCE(u.nombre_completo,u.email) AS autor
                FROM notas_internas ni JOIN usuarios u ON u.id=ni.usuario_id
                WHERE ni.reclamo_id=:id ORDER BY ni.created_at DESC, ni.id DESC
            """), {"id": str(claim_id)}).mappings().all()
        report = json.loads(row["reporte"]) if isinstance(row["reporte"], str) else row["reporte"]
        return ExpenseDetail(**list_item(row).model_dump(),
            reporte=ExpenseReport.model_validate(report) if report else None,
            envios=[dict(value) for value in deliveries], notas=[dict(value) for value in notes])

    def add_note(self, claim_id, content, user_id) -> ExpenseNote:
        with self.session_factory.begin() as session:
            # Usuario primero, compatible con las bajas de operadores de HU7/HU13.
            locking = " FOR SHARE" if session.bind.dialect.name == "postgresql" else ""
            author = session.execute(text("""
                SELECT id, COALESCE(nombre_completo,email) AS autor FROM usuarios
                WHERE id=:id AND activo AND NOT primer_ingreso
                    AND rol IN ('administrador','operador')
            """ + locking), {"id": str(user_id)}).mappings().one_or_none()
            if author is None:
                raise ExpenseNotePermissionError
            self._row(session, claim_id)
            row = session.execute(text("""
                INSERT INTO notas_internas (id, reclamo_id, usuario_id, contenido)
                VALUES (:id,:claim,:user,:content)
                RETURNING id, contenido, usuario_id, created_at AS creado_en
            """), {"id": str(uuid4()), "claim": str(claim_id), "user": str(user_id),
                   "content": content}).mappings().one()
        return ExpenseNote(**dict(row), autor=author["autor"])
