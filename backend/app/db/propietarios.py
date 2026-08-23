"""Persistencia SQL de propietarios sobre el esquema existente de Supabase."""

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.services.propietarios_service import (
    DuplicatePropietarioValueError,
    PropietarioHasPropertiesError,
)


class SqlAlchemyPropietariosRepository:
    """Repositorio transaccional compatible con PostgreSQL y SQLite de pruebas."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _translate_integrity_error(error: IntegrityError) -> None:
        diagnostic = getattr(error.orig, "diag", None)
        constraint = getattr(diagnostic, "constraint_name", "") or ""
        message = str(error.orig).lower()

        if constraint == "propietarios_dni_key" or "propietarios.dni" in message:
            raise DuplicatePropietarioValueError("dni") from error
        if (
            constraint == "uq_propietarios_email_normalizado"
            or "uq_propietarios_email_normalizado" in message
            or "lower(email)" in message
            or "propietarios.email" in message
        ):
            raise DuplicatePropietarioValueError("email") from error
        if constraint == "propiedades_propietario_id_fkey" or "foreign key" in message:
            raise PropietarioHasPropertiesError from error
        raise error

    def create(self, data: dict[str, object]) -> dict[str, object]:
        statement = text(
            """
            INSERT INTO propietarios (id, nombre_completo, dni, email, telefono)
            VALUES (:id, :nombre_completo, :dni, :email, :telefono)
            RETURNING id, nombre_completo, dni, email, telefono,
                      created_at, updated_at
            """
        )
        params = {"id": str(uuid4()), **data}

        try:
            with self.session_factory.begin() as session:
                row = session.execute(statement, params).mappings().one()
        except IntegrityError as error:
            self._translate_integrity_error(error)

        return {**dict(row), "cantidad_inmuebles": 0}

    def list(
        self, *, page: int, page_size: int, search: str | None
    ) -> tuple[list[dict[str, object]], int]:
        where_clause = ""
        params: dict[str, object] = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        if search:
            where_clause = """
                WHERE lower(pr.nombre_completo) LIKE :search
                   OR pr.dni LIKE :search
                   OR lower(pr.email) LIKE :search
            """
            params["search"] = f"%{search.lower()}%"

        count_statement = text(
            f"SELECT COUNT(*) FROM propietarios pr {where_clause}"
        )
        list_statement = text(
            f"""
            SELECT pr.id, pr.nombre_completo, pr.dni, pr.email, pr.telefono,
                   pr.created_at, pr.updated_at,
                   CAST(COUNT(p.id) AS INTEGER) AS cantidad_inmuebles
            FROM propietarios pr
            LEFT JOIN propiedades p ON p.propietario_id = pr.id
            {where_clause}
            GROUP BY pr.id, pr.nombre_completo, pr.dni, pr.email, pr.telefono,
                     pr.created_at, pr.updated_at
            ORDER BY lower(pr.nombre_completo), pr.id
            LIMIT :limit OFFSET :offset
            """
        )

        with self.session_factory() as session:
            total = int(session.execute(count_statement, params).scalar_one())
            rows = session.execute(list_statement, params).mappings().all()

        return [dict(row) for row in rows], total

    def get_detail(self, propietario_id: UUID) -> dict[str, object] | None:
        owner_statement = text(
            """
            SELECT pr.id, pr.nombre_completo, pr.dni, pr.email, pr.telefono,
                   pr.created_at, pr.updated_at,
                   CAST(COUNT(p.id) AS INTEGER) AS cantidad_inmuebles
            FROM propietarios pr
            LEFT JOIN propiedades p ON p.propietario_id = pr.id
            WHERE pr.id = :propietario_id
            GROUP BY pr.id, pr.nombre_completo, pr.dni, pr.email, pr.telefono,
                     pr.created_at, pr.updated_at
            """
        )
        properties_statement = text(
            """
            SELECT id, direccion, zona, CAST(tipo AS TEXT) AS tipo, piso, numero
            FROM propiedades
            WHERE propietario_id = :propietario_id
            ORDER BY lower(direccion), id
            """
        )
        params = {"propietario_id": str(propietario_id)}

        with self.session_factory() as session:
            owner = session.execute(owner_statement, params).mappings().one_or_none()
            if owner is None:
                return None
            properties = session.execute(properties_statement, params).mappings().all()

        return {**dict(owner), "propiedades": [dict(row) for row in properties]}

    def update(
        self, propietario_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None:
        statement = text(
            """
            UPDATE propietarios
            SET nombre_completo = :nombre_completo,
                dni = :dni,
                email = :email,
                telefono = :telefono,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :propietario_id
            RETURNING id, nombre_completo, dni, email, telefono,
                      created_at, updated_at
            """
        )
        params = {"propietario_id": str(propietario_id), **data}

        try:
            with self.session_factory.begin() as session:
                row = session.execute(statement, params).mappings().one_or_none()
        except IntegrityError as error:
            self._translate_integrity_error(error)

        if row is None:
            return None
        detail = self.get_detail(propietario_id)
        return detail

    def delete(self, propietario_id: UUID) -> bool:
        properties_statement = text(
            "SELECT COUNT(*) FROM propiedades WHERE propietario_id = :propietario_id"
        )
        delete_statement = text(
            "DELETE FROM propietarios WHERE id = :propietario_id"
        )
        params = {"propietario_id": str(propietario_id)}

        try:
            with self.session_factory.begin() as session:
                property_count = int(
                    session.execute(properties_statement, params).scalar_one()
                )
                if property_count:
                    raise PropietarioHasPropertiesError
                result = session.execute(delete_statement, params)
                return result.rowcount > 0
        except IntegrityError as error:
            self._translate_integrity_error(error)

        return False
