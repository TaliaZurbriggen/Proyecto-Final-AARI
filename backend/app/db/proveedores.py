"""Persistencia SQL de proveedores, especialidades y coberturas."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.services.proveedores_service import (
    EspecialidadNotFoundError,
    ProveedorDuplicatePhoneError,
)


class SqlAlchemyProveedoresRepository:
    """Repositorio transaccional compatible con PostgreSQL y SQLite de pruebas."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _translate_integrity_error(error: IntegrityError) -> None:
        diagnostic = getattr(error.orig, "diag", None)
        constraint = getattr(diagnostic, "constraint_name", "") or ""
        message = str(error.orig).lower()
        if (
            constraint in {"proveedores_telefono_key", "uq_proveedores_telefono"}
            or "proveedores.telefono" in message
            or "uq_proveedores_telefono" in message
        ):
            raise ProveedorDuplicatePhoneError from error
        raise error

    @staticmethod
    def _base_select() -> str:
        return """
            SELECT p.id, p.nombre_razon_social, p.matricula, p.telefono,
                   p.activo, p.hora_inicio, p.hora_fin,
                   p.created_at, p.updated_at
            FROM proveedores p
        """

    @staticmethod
    def _hydrate_relations(session, rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
        records = [dict(row) for row in rows]
        if not records:
            return records

        by_id = {str(record["id"]): record for record in records}
        for record in records:
            record["especialidades"] = []
            record["coberturas"] = []

        provider_ids = list(by_id)
        specialty_statement = text(
            """
            SELECT pe.proveedor_id, e.id, e.nombre
            FROM proveedor_especialidades pe
            JOIN especialidades e ON e.id = pe.especialidad_id
            WHERE pe.proveedor_id IN :provider_ids
            ORDER BY lower(e.nombre), e.id
            """
        ).bindparams(bindparam("provider_ids", expanding=True))
        for row in session.execute(
            specialty_statement, {"provider_ids": provider_ids}
        ).mappings():
            by_id[str(row["proveedor_id"])]["especialidades"].append(
                {"id": row["id"], "nombre": row["nombre"]}
            )

        coverage_statement = text(
            """
            SELECT c.proveedor_id, c.id, c.provincia, c.localidad,
                   c.cubre_toda_localidad, b.barrio
            FROM proveedor_coberturas c
            LEFT JOIN proveedor_cobertura_barrios b ON b.cobertura_id = c.id
            WHERE c.proveedor_id IN :provider_ids
            ORDER BY lower(c.provincia), lower(c.localidad), lower(b.barrio)
            """
        ).bindparams(bindparam("provider_ids", expanding=True))
        coverage_by_id: dict[str, dict[str, object]] = {}
        for row in session.execute(
            coverage_statement, {"provider_ids": provider_ids}
        ).mappings():
            coverage_id = str(row["id"])
            coverage = coverage_by_id.get(coverage_id)
            if coverage is None:
                coverage = {
                    "id": row["id"],
                    "provincia": row["provincia"],
                    "localidad": row["localidad"],
                    "cubre_toda_localidad": bool(row["cubre_toda_localidad"]),
                    "barrios": [],
                }
                coverage_by_id[coverage_id] = coverage
                by_id[str(row["proveedor_id"])]["coberturas"].append(coverage)
            if row["barrio"] is not None:
                coverage["barrios"].append(row["barrio"])
        return records

    @staticmethod
    def _replace_relations(session, proveedor_id: str, data: dict[str, object]) -> None:
        selected_ids = {str(value) for value in data["especialidad_ids"]}
        custom_names = list(data["especialidades_personalizadas"])

        if selected_ids:
            existing_statement = text(
                "SELECT id FROM especialidades WHERE id IN :specialty_ids"
            ).bindparams(bindparam("specialty_ids", expanding=True))
            existing_ids = {
                str(value)
                for value in session.execute(
                    existing_statement,
                    {"specialty_ids": list(selected_ids)},
                ).scalars()
            }
            if existing_ids != selected_ids:
                raise EspecialidadNotFoundError

        for name in custom_names:
            session.execute(
                text(
                    """
                    INSERT INTO especialidades (id, nombre)
                    VALUES (:id, :nombre)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"id": str(uuid4()), "nombre": name},
            )
            specialty_id = session.execute(
                text(
                    "SELECT id FROM especialidades "
                    "WHERE lower(trim(nombre)) = lower(trim(:nombre))"
                ),
                {"nombre": name},
            ).scalar_one()
            selected_ids.add(str(specialty_id))

        if not selected_ids:  # defensa adicional al contrato Pydantic
            raise EspecialidadNotFoundError

        session.execute(
            text(
                "DELETE FROM proveedor_especialidades WHERE proveedor_id = :provider_id"
            ),
            {"provider_id": proveedor_id},
        )
        for specialty_id in selected_ids:
            session.execute(
                text(
                    """
                    INSERT INTO proveedor_especialidades
                        (proveedor_id, especialidad_id)
                    VALUES (:provider_id, :specialty_id)
                    """
                ),
                {"provider_id": proveedor_id, "specialty_id": specialty_id},
            )

        session.execute(
            text(
                """
                DELETE FROM proveedor_cobertura_barrios
                WHERE cobertura_id IN (
                    SELECT id FROM proveedor_coberturas
                    WHERE proveedor_id = :provider_id
                )
                """
            ),
            {"provider_id": proveedor_id},
        )
        session.execute(
            text("DELETE FROM proveedor_coberturas WHERE proveedor_id = :provider_id"),
            {"provider_id": proveedor_id},
        )
        for raw_coverage in data["coberturas"]:
            coverage = dict(raw_coverage)
            coverage_id = str(uuid4())
            session.execute(
                text(
                    """
                    INSERT INTO proveedor_coberturas
                        (id, proveedor_id, provincia, localidad,
                         cubre_toda_localidad)
                    VALUES
                        (:id, :provider_id, :provincia, :localidad,
                         :cubre_toda_localidad)
                    """
                ),
                {
                    "id": coverage_id,
                    "provider_id": proveedor_id,
                    "provincia": coverage["provincia"],
                    "localidad": coverage["localidad"],
                    "cubre_toda_localidad": coverage["cubre_toda_localidad"],
                },
            )
            for neighborhood in coverage["barrios"]:
                session.execute(
                    text(
                        """
                        INSERT INTO proveedor_cobertura_barrios
                            (id, cobertura_id, barrio)
                        VALUES (:id, :coverage_id, :neighborhood)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "coverage_id": coverage_id,
                        "neighborhood": neighborhood,
                    },
                )

    def list_specialties(self) -> list[dict[str, object]]:
        with self.session_factory() as session:
            rows = session.execute(
                text("SELECT id, nombre FROM especialidades ORDER BY lower(nombre), id")
            ).mappings().all()
        return [dict(row) for row in rows]

    def create(self, data: dict[str, object]) -> dict[str, object]:
        provider_id = str(uuid4())
        try:
            with self.session_factory.begin() as session:
                session.execute(
                    text(
                        """
                        INSERT INTO proveedores
                            (id, nombre_razon_social, matricula, telefono, activo,
                             hora_inicio, hora_fin)
                        VALUES
                            (:id, :nombre_razon_social, :matricula, :telefono,
                             :activo, :hora_inicio, :hora_fin)
                        """
                    ),
                    {"id": provider_id, **data},
                )
                self._replace_relations(session, provider_id, data)
        except IntegrityError as error:
            self._translate_integrity_error(error)

        record = self.get_detail(UUID(provider_id))
        if record is None:  # pragma: no cover
            raise RuntimeError("El proveedor creado no pudo recuperarse.")
        return record

    def list(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        especialidad_id: UUID | None,
        provincia: str | None,
        localidad: str | None,
        barrio: str | None,
        activo: bool | None,
    ) -> tuple[list[dict[str, object]], int]:
        clauses: list[str] = []
        params: dict[str, object] = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        if search:
            digits = "".join(character for character in search if character.isdigit())
            clauses.append(
                """(
                    lower(p.nombre_razon_social) LIKE :search
                    OR lower(COALESCE(p.matricula, '')) LIKE :search
                    OR p.telefono LIKE :phone_search
                )"""
            )
            params["search"] = f"%{search.lower()}%"
            params["phone_search"] = f"%{digits or search}%"
        if activo is not None:
            clauses.append("p.activo = :active")
            params["active"] = activo
        if especialidad_id is not None:
            clauses.append(
                """EXISTS (
                    SELECT 1 FROM proveedor_especialidades pe
                    WHERE pe.proveedor_id = p.id
                      AND pe.especialidad_id = :specialty_id
                )"""
            )
            params["specialty_id"] = str(especialidad_id)

        coverage_filters: list[str] = []
        if provincia:
            coverage_filters.append("lower(c.provincia) = lower(:province)")
            params["province"] = provincia
        if localidad:
            coverage_filters.append("lower(c.localidad) LIKE :locality")
            params["locality"] = f"%{localidad.lower()}%"
        if barrio:
            coverage_filters.append(
                """(
                    c.cubre_toda_localidad = true
                    OR EXISTS (
                        SELECT 1 FROM proveedor_cobertura_barrios cb
                        WHERE cb.cobertura_id = c.id
                          AND lower(cb.barrio) LIKE :neighborhood
                    )
                )"""
            )
            params["neighborhood"] = f"%{barrio.lower()}%"
        if coverage_filters:
            clauses.append(
                "EXISTS (SELECT 1 FROM proveedor_coberturas c "
                "WHERE c.proveedor_id = p.id AND "
                + " AND ".join(coverage_filters)
                + ")"
            )

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.session_factory() as session:
            total = int(
                session.execute(
                    text(f"SELECT COUNT(*) FROM proveedores p {where_clause}"),
                    params,
                ).scalar_one()
            )
            rows = session.execute(
                text(
                    f"""
                    {self._base_select()}
                    {where_clause}
                    ORDER BY lower(p.nombre_razon_social), p.id
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
            records = self._hydrate_relations(session, rows)
        return records, total

    def get_detail(self, proveedor_id: UUID) -> dict[str, object] | None:
        with self.session_factory() as session:
            row = session.execute(
                text(f"{self._base_select()} WHERE p.id = :provider_id"),
                {"provider_id": str(proveedor_id)},
            ).mappings().one_or_none()
            if row is None:
                return None
            return self._hydrate_relations(session, [dict(row)])[0]

    def update(
        self, proveedor_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None:
        params = {"provider_id": str(proveedor_id), **data}
        try:
            with self.session_factory.begin() as session:
                exists = session.execute(
                    text("SELECT 1 FROM proveedores WHERE id = :provider_id"),
                    {"provider_id": str(proveedor_id)},
                ).scalar_one_or_none()
                if exists is None:
                    return None
                session.execute(
                    text(
                        """
                        UPDATE proveedores
                        SET nombre_razon_social = :nombre_razon_social,
                            matricula = :matricula,
                            telefono = :telefono,
                            activo = :activo,
                            hora_inicio = :hora_inicio,
                            hora_fin = :hora_fin,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :provider_id
                        """
                    ),
                    params,
                )
                self._replace_relations(session, str(proveedor_id), data)
        except IntegrityError as error:
            self._translate_integrity_error(error)
        return self.get_detail(proveedor_id)

    def update_status(
        self, proveedor_id: UUID, activo: bool
    ) -> dict[str, object] | None:
        with self.session_factory.begin() as session:
            result = session.execute(
                text(
                    """
                    UPDATE proveedores
                    SET activo = :active, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :provider_id
                    """
                ),
                {"provider_id": str(proveedor_id), "active": activo},
            )
            if result.rowcount == 0:
                return None
        return self.get_detail(proveedor_id)
