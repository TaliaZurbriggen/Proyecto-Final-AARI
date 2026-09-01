"""Reglas de aplicación para proveedores, especialidades y coberturas."""

from typing import Protocol
from uuid import UUID

from app.schemas.proveedores import (
    EspecialidadResponse,
    ProveedorCreate,
    ProveedorEstadoUpdate,
    ProveedorResponse,
    ProveedoresPage,
    ProveedorUpdate,
)


class ProveedorNotFoundError(Exception):
    """El proveedor solicitado no existe."""


class ProveedorDuplicatePhoneError(Exception):
    """El teléfono normalizado ya pertenece a otro proveedor."""


class EspecialidadNotFoundError(Exception):
    """Alguna especialidad seleccionada no existe."""


class ProveedoresRepository(Protocol):
    def list_specialties(self) -> list[dict[str, object]]: ...

    def create(self, data: dict[str, object]) -> dict[str, object]: ...

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
    ) -> tuple[list[dict[str, object]], int]: ...

    def get_detail(self, proveedor_id: UUID) -> dict[str, object] | None: ...

    def update(
        self, proveedor_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None: ...

    def update_status(
        self, proveedor_id: UUID, activo: bool
    ) -> dict[str, object] | None: ...


class ProveedoresService:
    def __init__(self, repository: ProveedoresRepository) -> None:
        self.repository = repository

    def list_specialties(self) -> list[EspecialidadResponse]:
        return [
            EspecialidadResponse.model_validate(item)
            for item in self.repository.list_specialties()
        ]

    def create(self, payload: ProveedorCreate) -> ProveedorResponse:
        record = self.repository.create(payload.model_dump(mode="json"))
        return ProveedorResponse.model_validate(record)

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
    ) -> ProveedoresPage:
        items, total = self.repository.list(
            page=page,
            page_size=page_size,
            search=search.strip() if search and search.strip() else None,
            especialidad_id=especialidad_id,
            provincia=provincia,
            localidad=localidad.strip() if localidad and localidad.strip() else None,
            barrio=barrio.strip() if barrio and barrio.strip() else None,
            activo=activo,
        )
        return ProveedoresPage.build(
            items=items, page=page, page_size=page_size, total=total
        )

    def get_detail(self, proveedor_id: UUID) -> ProveedorResponse:
        record = self.repository.get_detail(proveedor_id)
        if record is None:
            raise ProveedorNotFoundError
        return ProveedorResponse.model_validate(record)

    def update(
        self, proveedor_id: UUID, payload: ProveedorUpdate
    ) -> ProveedorResponse:
        record = self.repository.update(
            proveedor_id, payload.model_dump(mode="json")
        )
        if record is None:
            raise ProveedorNotFoundError
        return ProveedorResponse.model_validate(record)

    def update_status(
        self, proveedor_id: UUID, payload: ProveedorEstadoUpdate
    ) -> ProveedorResponse:
        record = self.repository.update_status(proveedor_id, payload.activo)
        if record is None:
            raise ProveedorNotFoundError
        return ProveedorResponse.model_validate(record)
