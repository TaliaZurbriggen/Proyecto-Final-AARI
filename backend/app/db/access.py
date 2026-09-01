"""Persistencia compartida para cuentas y entrega de credenciales."""

from uuid import UUID, uuid4

from sqlalchemy import text

from app.db.database import SessionLocal


def _is_postgresql(session) -> bool:
    return session.bind is not None and session.bind.dialect.name == "postgresql"


def create_access_account(
    session,
    *,
    email: str,
    temporary_password: str,
    role: str,
) -> str:
    """Crea usuario y seguimiento de entrega dentro de una transacción existente."""

    user_id = str(uuid4())
    delivery_id = str(uuid4())
    password_expression = (
        "crypt(:temporary_password, gen_salt('bf'))"
        if _is_postgresql(session)
        else ":temporary_password"
    )
    session.execute(
        text(
            f"""
            INSERT INTO usuarios
                (id, email, password_hash, rol, primer_ingreso, activo)
            VALUES
                (:user_id, :email, {password_expression}, :role, true, true)
            """
        ),
        {
            "user_id": user_id,
            "email": email,
            "temporary_password": temporary_password,
            "role": role,
        },
    )
    session.execute(
        text(
            """
            INSERT INTO entregas_credenciales
                (id, usuario_id, destinatario_email, estado, intentos)
            VALUES
                (:delivery_id, :user_id, :email, 'pendiente', 0)
            """
        ),
        {"delivery_id": delivery_id, "user_id": user_id, "email": email},
    )
    return user_id


def sync_pending_access_account(
    session,
    *,
    user_id: object,
    email: str,
    temporary_password: str,
    email_changed: bool,
    dni_changed: bool,
) -> None:
    """Sincroniza identidad y contraseña solo mientras la cuenta no fue activada."""

    if not email_changed and not dni_changed:
        return

    password_expression = (
        "crypt(:temporary_password, gen_salt('bf'))"
        if _is_postgresql(session)
        else ":temporary_password"
    )
    session.execute(
        text(
            f"""
            UPDATE usuarios
            SET email = :email,
                password_hash = CASE
                    WHEN primer_ingreso AND :dni_changed
                    THEN {password_expression}
                    ELSE password_hash
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :user_id
            """
        ),
        {
            "user_id": str(user_id),
            "email": email,
            "temporary_password": temporary_password,
            "dni_changed": dni_changed,
        },
    )
    session.execute(
        text(
            """
            UPDATE entregas_credenciales
            SET destinatario_email = :email,
                estado = CASE
                    WHEN EXISTS (
                        SELECT 1 FROM usuarios
                        WHERE id = :user_id AND primer_ingreso
                    ) THEN 'pendiente'
                    ELSE estado
                END,
                ultimo_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE usuario_id = :user_id
            """
        ),
        {"user_id": str(user_id), "email": email},
    )


def access_from_row(row: dict[str, object]) -> dict[str, object] | None:
    """Convierte columnas prefijadas de un JOIN al contrato público."""

    if row.get("acceso_estado") is None:
        return None
    return {
        "estado": row["acceso_estado"],
        "intentos": int(row.get("acceso_intentos") or 0),
        "primer_ingreso": bool(row.get("acceso_primer_ingreso")),
        "ultimo_error": row.get("acceso_ultimo_error"),
        "enviado_en": row.get("acceso_enviado_en"),
    }


class SqlAlchemyAccessRepository:
    """Operaciones posteriores al alta y cambio de contraseña."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def mark_delivery_result(
        self,
        user_id: UUID,
        *,
        sent: bool,
        safe_error: str | None = None,
    ) -> None:
        with self.session_factory.begin() as session:
            session.execute(
                text(
                    """
                    UPDATE entregas_credenciales
                    SET estado = :estado,
                        intentos = intentos + 1,
                        ultimo_error = :safe_error,
                        enviado_en = CASE
                            WHEN :sent THEN CURRENT_TIMESTAMP
                            ELSE enviado_en
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE usuario_id = :user_id
                    """
                ),
                {
                    "user_id": str(user_id),
                    "estado": "enviado" if sent else "fallido",
                    "safe_error": safe_error,
                    "sent": sent,
                },
            )

    def get_delivery_context(
        self,
        *,
        entity: str,
        entity_id: UUID,
    ) -> dict[str, object] | None:
        table = {"propietario": "propietarios", "inquilino": "inquilinos"}.get(entity)
        if table is None:
            raise ValueError("Tipo de entidad de acceso inválido.")
        statement = text(
            f"""
            SELECT u.id AS usuario_id, u.primer_ingreso,
                   person.nombre_completo, person.dni, person.email,
                   ec.estado
            FROM {table} person
            JOIN usuarios u ON u.id = person.usuario_id
            JOIN entregas_credenciales ec ON ec.usuario_id = u.id
            WHERE person.id = :entity_id
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement, {"entity_id": str(entity_id)}
            ).mappings().one_or_none()
        return dict(row) if row else None

    def change_password(
        self,
        user_id: UUID,
        *,
        current_password: str,
        new_password: str,
    ) -> bool:
        with self.session_factory.begin() as session:
            if _is_postgresql(session):
                current_condition = "password_hash = crypt(:current_password, password_hash)"
                new_expression = "crypt(:new_password, gen_salt('bf'))"
            else:
                current_condition = "password_hash = :current_password"
                new_expression = ":new_password"
            result = session.execute(
                text(
                    f"""
                    UPDATE usuarios
                    SET password_hash = {new_expression},
                        primer_ingreso = false,
                        intentos_fallidos = 0,
                        bloqueado_hasta = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :user_id
                      AND {current_condition}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "current_password": current_password,
                    "new_password": new_password,
                },
            )
            return result.rowcount > 0
