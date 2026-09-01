"""Persistencia SQL de inquilinos sobre el esquema de Supabase."""

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.access import (
    access_from_row,
    create_access_account,
    sync_pending_access_account,
)
from app.db.database import SessionLocal
from app.services.inquilinos_service import (
    InquilinoDuplicateDniError,
    InquilinoDuplicateEmailError,
    InquilinoHasClaimsError,
    InquilinoPropertyNotFoundError,
    InquilinoPropertyOccupiedError,
)


class SqlAlchemyInquilinosRepository:
    """Repositorio transaccional compatible con PostgreSQL y SQLite de pruebas."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _translate_integrity_error(error: IntegrityError) -> None:
        diagnostic = getattr(error.orig, "diag", None)
        constraint = getattr(diagnostic, "constraint_name", "") or ""
        message = str(error.orig).lower()

        if constraint == "inquilinos_dni_key" or "inquilinos.dni" in message:
            raise InquilinoDuplicateDniError from error
        if (
            constraint == "uq_inquilinos_email_normalizado"
            or "uq_inquilinos_email_normalizado" in message
            or "index 'uq_inquilinos_email_normalizado'" in message
        ):
            raise InquilinoDuplicateEmailError from error
        if (
            constraint in {"usuarios_email_key", "uq_usuarios_email_normalizado"}
            or "usuarios.email" in message
            or "uq_usuarios_email_normalizado" in message
        ):
            raise InquilinoDuplicateEmailError from error
        if (
            constraint == "uq_inquilinos_propiedad_activa"
            or "uq_inquilinos_propiedad_activa" in message
            or "index 'uq_inquilinos_propiedad_activa'" in message
        ):
            raise InquilinoPropertyOccupiedError from error
        if constraint == "inquilinos_propiedad_id_fkey" or "foreign key" in message:
            raise InquilinoPropertyNotFoundError from error
        raise error

    @staticmethod
    def _ensure_property_available(
        session, propiedad_id: object, *, excluding_tenant_id: object | None = None
    ) -> None:
        property_exists = session.execute(
            text("SELECT 1 FROM propiedades WHERE id = :propiedad_id"),
            {"propiedad_id": str(propiedad_id)},
        ).scalar_one_or_none()
        if property_exists is None:
            raise InquilinoPropertyNotFoundError

        params = {"propiedad_id": str(propiedad_id)}
        exclusion = ""
        if excluding_tenant_id is not None:
            exclusion = "AND id <> :inquilino_id"
            params["inquilino_id"] = str(excluding_tenant_id)
        occupied = session.execute(
            text(
                "SELECT 1 FROM inquilinos "
                "WHERE propiedad_id = :propiedad_id AND estado = 'activo' "
                f"{exclusion} LIMIT 1"
            ),
            params,
        ).scalar_one_or_none()
        if occupied is not None:
            raise InquilinoPropertyOccupiedError

    @staticmethod
    def _public_record(row: dict[str, object]) -> dict[str, object]:
        record = dict(row)
        property_id = record.get("propiedad_id")
        property_data = None
        if property_id is not None:
            property_data = {
                "id": property_id,
                "direccion": record["propiedad_direccion"],
                "provincia": record["propiedad_provincia"],
                "localidad": record["propiedad_localidad"],
                "barrio": record["propiedad_barrio"],
                "tipo": record["propiedad_tipo"],
                "piso": record["propiedad_piso"],
                "numero": record["propiedad_numero"],
            }
        return {
            "id": record["id"],
            "nombre_completo": record["nombre_completo"],
            "dni": record["dni"],
            "email": record["email"],
            "telefono": record["telefono"],
            "propiedad": property_data,
            "estado": record["estado"],
            "cantidad_reclamos": int(record["cantidad_reclamos"]),
            "acceso": access_from_row(record),
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }

    @staticmethod
    def _select_base() -> str:
        return """
            SELECT i.id, i.nombre_completo, i.dni, i.email, i.telefono,
                   CAST(i.estado AS TEXT) AS estado,
                   i.created_at, i.updated_at,
                   p.id AS propiedad_id,
                   p.direccion AS propiedad_direccion,
                   p.provincia AS propiedad_provincia,
                   p.localidad AS propiedad_localidad,
                   p.barrio AS propiedad_barrio,
                   CAST(p.tipo AS TEXT) AS propiedad_tipo,
                   p.piso AS propiedad_piso,
                   p.numero AS propiedad_numero,
                   CAST((
                       SELECT COUNT(*) FROM reclamos r
                       WHERE r.inquilino_id = i.id
                   ) AS INTEGER) AS cantidad_reclamos,
                   CAST(ec.estado AS TEXT) AS acceso_estado,
                   ec.intentos AS acceso_intentos,
                   ec.ultimo_error AS acceso_ultimo_error,
                   ec.enviado_en AS acceso_enviado_en,
                   u.primer_ingreso AS acceso_primer_ingreso
            FROM inquilinos i
            LEFT JOIN propiedades p ON p.id = i.propiedad_id
            LEFT JOIN usuarios u ON u.id = i.usuario_id
            LEFT JOIN entregas_credenciales ec ON ec.usuario_id = u.id
        """

    def create(self, data: dict[str, object]) -> dict[str, object]:
        inquilino_id = str(uuid4())
        statement = text(
            """
            INSERT INTO inquilinos
                (id, nombre_completo, dni, email, telefono, propiedad_id,
                 estado, usuario_id)
            VALUES
                (:id, :nombre_completo, :dni, :email, :telefono,
                 :propiedad_id, 'activo', :usuario_id)
            """
        )
        try:
            with self.session_factory.begin() as session:
                self._ensure_property_available(session, data["propiedad_id"])
                user_id = create_access_account(
                    session,
                    email=str(data["email"]),
                    temporary_password=str(data["dni"]),
                    role="inquilino",
                )
                session.execute(
                    statement,
                    {"id": inquilino_id, "usuario_id": user_id, **data},
                )
        except IntegrityError as error:
            self._translate_integrity_error(error)

        record = self.get_detail(UUID(inquilino_id))
        if record is None:  # pragma: no cover - defensa ante una BD inconsistente
            raise RuntimeError("El inquilino creado no pudo recuperarse.")
        return {**record, "usuario_id": user_id}

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
                WHERE lower(i.nombre_completo) LIKE :search
                   OR i.dni LIKE :search
                   OR lower(i.email) LIKE :search
                   OR lower(COALESCE(p.direccion, '')) LIKE :search
                   OR lower(COALESCE(p.localidad, '')) LIKE :search
            """
            params["search"] = f"%{search.lower()}%"

        count_statement = text(
            f"""
            SELECT COUNT(*)
            FROM inquilinos i
            LEFT JOIN propiedades p ON p.id = i.propiedad_id
            {where_clause}
            """
        )
        list_statement = text(
            f"""
            {self._select_base()}
            {where_clause}
            ORDER BY lower(i.nombre_completo), i.id
            LIMIT :limit OFFSET :offset
            """
        )
        with self.session_factory() as session:
            total = int(session.execute(count_statement, params).scalar_one())
            rows = session.execute(list_statement, params).mappings().all()
        return [self._public_record(dict(row)) for row in rows], total

    def get_detail(self, inquilino_id: UUID) -> dict[str, object] | None:
        statement = text(
            f"""
            {self._select_base()}
            WHERE i.id = :inquilino_id
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement, {"inquilino_id": str(inquilino_id)}
            ).mappings().one_or_none()
        return self._public_record(dict(row)) if row else None

    def property_exists(self, propiedad_id: UUID) -> bool:
        with self.session_factory() as session:
            return (
                session.execute(
                    text("SELECT 1 FROM propiedades WHERE id = :propiedad_id"),
                    {"propiedad_id": str(propiedad_id)},
                ).scalar_one_or_none()
                is not None
            )

    def get_active_by_property(
        self, propiedad_id: UUID
    ) -> dict[str, object] | None:
        statement = text(
            f"""
            {self._select_base()}
            WHERE i.propiedad_id = :propiedad_id AND i.estado = 'activo'
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement, {"propiedad_id": str(propiedad_id)}
            ).mappings().one_or_none()
        return self._public_record(dict(row)) if row else None

    def update(
        self, inquilino_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None:
        property_id = data.get("propiedad_id")
        statement = text(
            """
            UPDATE inquilinos
            SET nombre_completo = :nombre_completo,
                dni = :dni,
                email = :email,
                telefono = :telefono,
                propiedad_id = :propiedad_id,
                estado = :estado,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :inquilino_id
            """
        )
        params = {
            "inquilino_id": str(inquilino_id),
            **data,
            "estado": "activo" if property_id is not None else "sin_propiedad_asignada",
        }
        try:
            with self.session_factory.begin() as session:
                current = session.execute(
                    text(
                        "SELECT email, dni, usuario_id FROM inquilinos "
                        "WHERE id = :inquilino_id"
                    ),
                    {"inquilino_id": str(inquilino_id)},
                ).mappings().one_or_none()
                if current is None:
                    return None
                if property_id is not None:
                    self._ensure_property_available(
                        session,
                        property_id,
                        excluding_tenant_id=inquilino_id,
                    )
                session.execute(statement, params)
                if current["usuario_id"] is not None:
                    sync_pending_access_account(
                        session,
                        user_id=current["usuario_id"],
                        email=str(data["email"]),
                        temporary_password=str(data["dni"]),
                        email_changed=str(current["email"]).lower() != str(data["email"]).lower(),
                        dni_changed=str(current["dni"]) != str(data["dni"]),
                    )
        except IntegrityError as error:
            self._translate_integrity_error(error)
        return self.get_detail(inquilino_id)

    def disassociate(self, inquilino_id: UUID) -> dict[str, object] | None:
        statement = text(
            """
            UPDATE inquilinos
            SET propiedad_id = NULL,
                estado = 'sin_propiedad_asignada',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :inquilino_id
            """
        )
        with self.session_factory.begin() as session:
            result = session.execute(
                statement, {"inquilino_id": str(inquilino_id)}
            )
            if result.rowcount == 0:
                return None
        return self.get_detail(inquilino_id)

    def delete(self, inquilino_id: UUID) -> bool:
        params = {"inquilino_id": str(inquilino_id)}
        with self.session_factory.begin() as session:
            current = session.execute(
                text(
                    "SELECT usuario_id FROM inquilinos "
                    "WHERE id = :inquilino_id"
                ),
                params,
            ).mappings().one_or_none()
            if current is None:
                return False
            claims_count = int(
                session.execute(
                    text(
                        "SELECT COUNT(*) FROM reclamos "
                        "WHERE inquilino_id = :inquilino_id"
                    ),
                    params,
                ).scalar_one()
            )
            if claims_count:
                raise InquilinoHasClaimsError
            result = session.execute(
                text("DELETE FROM inquilinos WHERE id = :inquilino_id"), params
            )
            if result.rowcount > 0 and current["usuario_id"] is not None:
                session.execute(
                    text("DELETE FROM usuarios WHERE id = :user_id"),
                    {"user_id": str(current["usuario_id"])},
                )
            return result.rowcount > 0
