"""Persistencia SQL de propiedades sobre el esquema de Supabase."""

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.services.propiedades_service import (
    DuplicatePropertyAddressError,
    PropertyHasActiveTenantError,
    PropertyHasClaimsError,
    PropietarioNotFoundError,
)


class SqlAlchemyPropiedadesRepository:
    """Repositorio transaccional compatible con PostgreSQL y SQLite de pruebas."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _translate_integrity_error(error: IntegrityError) -> None:
        diagnostic = getattr(error.orig, "diag", None)
        constraint = getattr(diagnostic, "constraint_name", "") or ""
        message = str(error.orig).lower()

        if (
            constraint.startswith("uq_propiedades_direccion_")
            or "uq_propiedades_direccion_" in message
            or "propiedades.direccion" in message
            or "index 'uq_propiedades" in message
        ):
            raise DuplicatePropertyAddressError from error
        if constraint == "propiedades_propietario_id_fkey" or "foreign key" in message:
            raise PropietarioNotFoundError from error
        raise error

    @staticmethod
    def _ensure_owner(session, propietario_id: object) -> None:
        exists = session.execute(
            text("SELECT 1 FROM propietarios WHERE id = :propietario_id"),
            {"propietario_id": str(propietario_id)},
        ).scalar_one_or_none()
        if exists is None:
            raise PropietarioNotFoundError

    @staticmethod
    def _public_record(row: dict[str, object]) -> dict[str, object]:
        record = dict(row)
        return {
            "id": record["id"],
            "direccion": record["direccion"],
            "provincia": record["provincia"],
            "localidad": record["localidad"],
            "barrio": record["barrio"],
            "tipo": record["tipo"],
            "piso": record["piso"],
            "numero": record["numero"],
            "propietario": {
                "id": record["propietario_id"],
                "nombre_completo": record["propietario_nombre"],
            },
            "cantidad_reclamos": int(record["cantidad_reclamos"]),
            "tiene_inquilino_activo": bool(record["tiene_inquilino_activo"]),
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }

    def create(self, data: dict[str, object]) -> dict[str, object]:
        propiedad_id = str(uuid4())
        statement = text(
            """
            INSERT INTO propiedades
                (id, direccion, provincia, localidad, barrio, tipo, piso,
                 numero, propietario_id)
            VALUES
                (:id, :direccion, :provincia, :localidad, :barrio, :tipo,
                 :piso, :numero, :propietario_id)
            """
        )
        params = {"id": propiedad_id, **data}

        try:
            with self.session_factory.begin() as session:
                self._ensure_owner(session, data["propietario_id"])
                session.execute(statement, params)
        except IntegrityError as error:
            self._translate_integrity_error(error)

        record = self.get_detail(UUID(propiedad_id))
        if record is None:  # pragma: no cover - defensa ante una BD inconsistente
            raise RuntimeError("La propiedad creada no pudo recuperarse.")
        return record

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
                WHERE lower(p.direccion) LIKE :search
                   OR lower(p.provincia) LIKE :search
                   OR lower(p.localidad) LIKE :search
                   OR lower(COALESCE(p.barrio, '')) LIKE :search
                   OR lower(pr.nombre_completo) LIKE :search
            """
            params["search"] = f"%{search.lower()}%"

        count_statement = text(
            f"""
            SELECT COUNT(*)
            FROM propiedades p
            JOIN propietarios pr ON pr.id = p.propietario_id
            {where_clause}
            """
        )
        list_statement = text(
            f"""
            SELECT p.id, p.direccion, p.provincia, p.localidad, p.barrio,
                   CAST(p.tipo AS TEXT) AS tipo, p.piso, p.numero,
                   p.created_at, p.updated_at,
                   pr.id AS propietario_id,
                   pr.nombre_completo AS propietario_nombre,
                   CAST((
                       SELECT COUNT(*) FROM reclamos r
                       WHERE r.propiedad_id = p.id
                   ) AS INTEGER) AS cantidad_reclamos,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM inquilinos i
                       WHERE i.propiedad_id = p.id AND i.estado = 'activo'
                   ) THEN 1 ELSE 0 END AS tiene_inquilino_activo
            FROM propiedades p
            JOIN propietarios pr ON pr.id = p.propietario_id
            {where_clause}
            ORDER BY lower(p.provincia), lower(p.localidad), lower(p.direccion),
                     COALESCE(p.piso, -2147483648),
                     lower(COALESCE(p.numero, '')), p.id
            LIMIT :limit OFFSET :offset
            """
        )

        with self.session_factory() as session:
            total = int(session.execute(count_statement, params).scalar_one())
            rows = session.execute(list_statement, params).mappings().all()

        return [self._public_record(dict(row)) for row in rows], total

    def get_detail(self, propiedad_id: UUID) -> dict[str, object] | None:
        statement = text(
            """
            SELECT p.id, p.direccion, p.provincia, p.localidad, p.barrio,
                   CAST(p.tipo AS TEXT) AS tipo, p.piso, p.numero,
                   p.created_at, p.updated_at,
                   pr.id AS propietario_id,
                   pr.nombre_completo AS propietario_nombre,
                   CAST((
                       SELECT COUNT(*) FROM reclamos r
                       WHERE r.propiedad_id = p.id
                   ) AS INTEGER) AS cantidad_reclamos,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM inquilinos i
                       WHERE i.propiedad_id = p.id AND i.estado = 'activo'
                   ) THEN 1 ELSE 0 END AS tiene_inquilino_activo
            FROM propiedades p
            JOIN propietarios pr ON pr.id = p.propietario_id
            WHERE p.id = :propiedad_id
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement, {"propiedad_id": str(propiedad_id)}
            ).mappings().one_or_none()
        return self._public_record(dict(row)) if row else None

    def update(
        self, propiedad_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None:
        existence_statement = text(
            "SELECT 1 FROM propiedades WHERE id = :propiedad_id"
        )
        update_statement = text(
            """
            UPDATE propiedades
            SET direccion = :direccion,
                provincia = :provincia,
                localidad = :localidad,
                barrio = :barrio,
                tipo = :tipo,
                piso = :piso,
                numero = :numero,
                propietario_id = :propietario_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :propiedad_id
            """
        )
        params = {"propiedad_id": str(propiedad_id), **data}

        try:
            with self.session_factory.begin() as session:
                exists = session.execute(
                    existence_statement, {"propiedad_id": str(propiedad_id)}
                ).scalar_one_or_none()
                if exists is None:
                    return None
                self._ensure_owner(session, data["propietario_id"])
                session.execute(update_statement, params)
        except IntegrityError as error:
            self._translate_integrity_error(error)

        return self.get_detail(propiedad_id)

    def delete(self, propiedad_id: UUID) -> bool:
        params = {"propiedad_id": str(propiedad_id)}
        with self.session_factory.begin() as session:
            exists = session.execute(
                text("SELECT 1 FROM propiedades WHERE id = :propiedad_id"), params
            ).scalar_one_or_none()
            if exists is None:
                return False

            claims_count = int(
                session.execute(
                    text(
                        "SELECT COUNT(*) FROM reclamos "
                        "WHERE propiedad_id = :propiedad_id"
                    ),
                    params,
                ).scalar_one()
            )
            if claims_count:
                raise PropertyHasClaimsError

            active_tenant = session.execute(
                text(
                    "SELECT 1 FROM inquilinos "
                    "WHERE propiedad_id = :propiedad_id AND estado = 'activo' "
                    "LIMIT 1"
                ),
                params,
            ).scalar_one_or_none()
            if active_tenant is not None:
                raise PropertyHasActiveTenantError

            result = session.execute(
                text("DELETE FROM propiedades WHERE id = :propiedad_id"), params
            )
            return result.rowcount > 0
