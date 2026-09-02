"""Persistencia SQL para usuarios y control de intentos de acceso."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.db.database import SessionLocal


class SqlAlchemyUsuariosRepository:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def find_for_login(self, email: str, password: str) -> dict[str, object] | None:
        statement = text(
            """
            SELECT u.id, u.email, CAST(u.rol AS TEXT) AS rol,
                   u.primer_ingreso, u.activo,
                   intentos_fallidos, bloqueado_hasta,
                   password_hash = crypt(:password, password_hash) AS password_valid,
                   COALESCE(
                       (SELECT p.id FROM propietarios p WHERE p.usuario_id = u.id),
                       (SELECT i.id FROM inquilinos i WHERE i.usuario_id = u.id)
                   ) AS perfil_id
            FROM usuarios u
            WHERE lower(u.email) = :email
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement,
                {"email": email, "password": password},
            ).mappings().one_or_none()
        return dict(row) if row else None

    def get_by_id(self, user_id: UUID) -> dict[str, object] | None:
        statement = text(
            """
            SELECT u.id, u.email, CAST(u.rol AS TEXT) AS rol,
                   u.primer_ingreso, u.activo,
                   COALESCE(
                       (SELECT p.id FROM propietarios p WHERE p.usuario_id = u.id),
                       (SELECT i.id FROM inquilinos i WHERE i.usuario_id = u.id)
                   ) AS perfil_id
            FROM usuarios u
            WHERE u.id = :user_id
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement,
                {"user_id": str(user_id)},
            ).mappings().one_or_none()
        return dict(row) if row else None

    def record_failed_attempt(
        self,
        user_id: UUID,
        *,
        now: datetime,
        max_attempts: int,
        lock_minutes: int,
    ) -> datetime | None:
        statement = text(
            """
            UPDATE usuarios
            SET intentos_fallidos = LEAST(intentos_fallidos + 1, :max_attempts),
                bloqueado_hasta = CASE
                    WHEN intentos_fallidos + 1 >= :max_attempts
                    THEN :now + (:lock_minutes * INTERVAL '1 minute')
                    ELSE bloqueado_hasta
                END,
                updated_at = :now
            WHERE id = :user_id
            RETURNING bloqueado_hasta
            """
        )
        with self.session_factory.begin() as session:
            value = session.execute(
                statement,
                {
                    "user_id": str(user_id),
                    "now": now,
                    "max_attempts": max_attempts,
                    "lock_minutes": lock_minutes,
                },
            ).scalar_one()
        return value

    def reset_failed_attempts(self, user_id: UUID, *, now: datetime) -> None:
        statement = text(
            """
            UPDATE usuarios
            SET intentos_fallidos = 0,
                bloqueado_hasta = NULL,
                updated_at = :now
            WHERE id = :user_id
            """
        )
        with self.session_factory.begin() as session:
            session.execute(statement, {"user_id": str(user_id), "now": now})
