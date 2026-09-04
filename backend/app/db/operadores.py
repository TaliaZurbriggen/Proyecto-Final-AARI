"""Transacciones de operadores sobre usuarios y entregas de credenciales."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.access import _is_postgresql, access_from_row
from app.db.database import SessionLocal
from app.services.operadores_service import (
    DuplicateOperadorEmailError, OperadorAccessConflictError, OperadorNotFoundError,
)

OPERATOR_SELECT = """
    SELECT u.id, u.nombre_completo, u.email, u.activo, u.created_at,
           ec.estado AS acceso_estado, ec.intentos AS acceso_intentos,
           ec.ultimo_error AS acceso_ultimo_error, ec.enviado_en AS acceso_enviado_en,
           u.primer_ingreso AS acceso_primer_ingreso
    FROM usuarios u
    LEFT JOIN entregas_credenciales ec ON ec.usuario_id = u.id
"""


def public_record(row) -> dict:
    record = dict(row)
    return {**record, "acceso": access_from_row(record)}


class SqlAlchemyOperadoresRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def create(self, data: dict, temporary_password: str) -> dict:
        user_id, delivery_id = str(uuid4()), str(uuid4())
        params = {**data, "id": user_id, "delivery_id": delivery_id,
                  "password": temporary_password}
        try:
            with self.session_factory.begin() as session:
                expression = (
                    "crypt(:password, gen_salt('bf'))"
                    if _is_postgresql(session) else ":password"
                )
                session.execute(text(f"""
                    INSERT INTO usuarios
                        (id, nombre_completo, email, password_hash, rol,
                         primer_ingreso, activo)
                    VALUES (:id, :nombre_completo, :email, {expression},
                            'operador', true, true)
                """), params)
                session.execute(text("""
                    INSERT INTO entregas_credenciales
                        (id, usuario_id, destinatario_email, estado, intentos)
                    VALUES (:delivery_id, :id, :email, 'pendiente', 0)
                """), params)
        except IntegrityError as error:
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", "")
            if constraint in {"usuarios_email_key", "uq_usuarios_email_normalizado"} or any(
                name in str(error.orig).lower()
                for name in ("usuarios.email", "uq_usuarios_email_normalizado")
            ):
                raise DuplicateOperadorEmailError from error
            raise
        return {**data, "id": user_id, "delivery_id": delivery_id}

    def get(self, user_id: UUID) -> dict | None:
        with self.session_factory() as session:
            row = session.execute(text(OPERATOR_SELECT + """
                WHERE u.id = :id AND u.rol = 'operador'
            """), {"id": str(user_id)}).mappings().one_or_none()
        return public_record(row) if row else None

    def list(self, *, page: int, page_size: int, search: str | None) -> tuple[list, int]:
        where = " WHERE u.rol = 'operador'"
        params = {"limit": page_size, "offset": (page - 1) * page_size}
        if search:
            where += " AND (lower(u.nombre_completo) LIKE :search OR lower(u.email) LIKE :search)"
            params["search"] = f"%{search.lower()}%"
        with self.session_factory() as session:
            total = session.execute(text("SELECT COUNT(*) FROM usuarios u" + where), params).scalar_one()
            rows = session.execute(text(OPERATOR_SELECT + where + """
                ORDER BY lower(u.nombre_completo), u.id LIMIT :limit OFFSET :offset
            """), params).mappings().all()
        return [public_record(row) for row in rows], total

    def prepare_retry(self, user_id: UUID, temporary_password: str) -> dict:
        with self.session_factory.begin() as session:
            lock = " FOR UPDATE" if _is_postgresql(session) else ""
            row = session.execute(text("""
                SELECT id, nombre_completo, email, activo, primer_ingreso
                FROM usuarios WHERE id = :id AND rol = 'operador'
            """ + lock), {"id": str(user_id)}).mappings().one_or_none()
            if row is None:
                raise OperadorNotFoundError
            if not row["activo"]:
                raise OperadorAccessConflictError("El operador está desactivado.")
            if not row["primer_ingreso"]:
                raise OperadorAccessConflictError("La cuenta ya fue activada y no usa contraseña temporal.")
            # Leer la entrega después de obtener el bloqueo: otra transacción pudo
            # actualizarla mientras esta esperaba el bloqueo del usuario.
            delivery = session.execute(text("""
                SELECT estado, updated_at FROM entregas_credenciales WHERE usuario_id = :id
            """), {"id": str(user_id)}).mappings().one_or_none()
            if delivery is None:
                raise OperadorAccessConflictError("La cuenta no tiene un registro de entrega. Revisá su migración.")
            updated = delivery["updated_at"]
            if isinstance(updated, str):
                updated = datetime.fromisoformat(updated)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if delivery["estado"] == "pendiente" and updated > datetime.now(UTC) - timedelta(minutes=2):
                raise OperadorAccessConflictError("Hay un envío en curso. Esperá dos minutos antes de reintentar.")
            delivery_id = str(uuid4())
            expression = (
                "crypt(:password, gen_salt('bf'))" if _is_postgresql(session) else ":password"
            )
            params = {"id": str(user_id), "password": temporary_password,
                      "delivery_id": delivery_id}
            session.execute(text(f"""
                UPDATE usuarios SET password_hash = {expression}, intentos_fallidos = 0,
                    bloqueado_hasta = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), params)
            # Cambiar el identificador permite ignorar resultados de un envío anterior.
            session.execute(text("""
                UPDATE entregas_credenciales SET id = :delivery_id, estado = 'pendiente',
                    ultimo_error = NULL, enviado_en = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE usuario_id = :id
            """), params)
            return {"id": str(user_id), "email": row["email"],
                    "nombre_completo": row["nombre_completo"], "delivery_id": delivery_id}

    def record_delivery(self, context: dict, *, sent: bool) -> None:
        with self.session_factory.begin() as session:
            session.execute(text("""
                UPDATE entregas_credenciales SET estado = :estado,
                    intentos = intentos + 1, ultimo_error = :error,
                    enviado_en = CASE WHEN :sent THEN CURRENT_TIMESTAMP ELSE NULL END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE usuario_id = :id AND id = :delivery_id
            """), {"id": str(context["id"]), "delivery_id": str(context["delivery_id"]),
                   "estado": "enviado" if sent else "fallido", "sent": sent,
                   "error": None if sent else "No se pudo entregar el correo de bienvenida."})

    def deactivate(self, user_id: UUID) -> int:
        with self.session_factory.begin() as session:
            lock = " FOR UPDATE" if _is_postgresql(session) else ""
            exists = session.execute(text("""
                SELECT id FROM usuarios WHERE id = :id AND rol = 'operador'
            """ + lock), {"id": str(user_id)}).scalar_one_or_none()
            if exists is None:
                raise OperadorNotFoundError
            session.execute(text("""
                UPDATE usuarios SET activo = false, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND rol = 'operador'
            """), {"id": str(user_id)})
            result = session.execute(text("""
                UPDATE reclamos SET operador_asignado_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE operador_asignado_id = :id AND estado = 'Escalado'
            """), {"id": str(user_id)})
            return result.rowcount
