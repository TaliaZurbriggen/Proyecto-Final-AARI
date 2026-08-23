"""Reglas de aplicación para la gestión de propiedades."""

from typing import Protocol
from uuid import UUID

from app.schemas.propiedades import (
    PropiedadCreate,
    PropiedadResponse,
    PropiedadesPage,
    PropiedadUpdate,
)


class PropiedadNotFoundError(Exception):
    """La propiedad solicitada no existe."""


class PropietarioNotFoundError(Exception):
    """El propietario indicado no existe."""


class DuplicatePropertyAddressError(Exception):
    """La ubicación y unidad ya identifican otra propiedad."""


class PropertyHasClaimsError(Exception):
    """Una propiedad con reclamos históricos conserva su trazabilidad."""


class PropertyHasActiveTenantError(Exception):
    """Una propiedad ocupada no puede eliminarse."""


class PropiedadesRepository(Protocol):
    def create(self, data: dict[str, object]) -> dict[str, object]: ...

    def list(
        self, *, page: int, page_size: int, search: str | None
    ) -> tuple[list[dict[str, object]], int]: ...

    def get_detail(self, propiedad_id: UUID) -> dict[str, object] | None: ...

    def update(
        self, propiedad_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None: ...

    def delete(self, propiedad_id: UUID) -> bool: ...


class PropiedadesService:
    """Orquesta validaciones de existencia y contratos de respuesta."""

    def __init__(self, repository: PropiedadesRepository) -> None:
        self.repository = repository

    def create(self, payload: PropiedadCreate) -> PropiedadResponse:
        record = self.repository.create(payload.model_dump(mode="json"))
        return PropiedadResponse.model_validate(record)

    def list(
        self, *, page: int, page_size: int, search: str | None
    ) -> PropiedadesPage:
        normalized_search = search.strip() if search and search.strip() else None
        items, total = self.repository.list(
            page=page,
            page_size=page_size,
            search=normalized_search,
        )
        return PropiedadesPage.build(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_detail(self, propiedad_id: UUID) -> PropiedadResponse:
        record = self.repository.get_detail(propiedad_id)
        if record is None:
            raise PropiedadNotFoundError
        return PropiedadResponse.model_validate(record)

    def update(
        self, propiedad_id: UUID, payload: PropiedadUpdate
    ) -> PropiedadResponse:
        record = self.repository.update(
            propiedad_id,
            payload.model_dump(mode="json"),
        )
        if record is None:
            raise PropiedadNotFoundError
        return PropiedadResponse.model_validate(record)

    def delete(self, propiedad_id: UUID) -> None:
        deleted = self.repository.delete(propiedad_id)
        if not deleted:
            raise PropiedadNotFoundError
