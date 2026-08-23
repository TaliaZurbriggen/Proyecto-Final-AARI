"""Reglas de aplicación para la gestión de propietarios."""

from typing import Protocol
from uuid import UUID

from app.schemas.propietarios import (
    PropietarioCreate,
    PropietarioDetailResponse,
    PropietarioResponse,
    PropietariosPage,
    PropietarioUpdate,
)


class PropietarioNotFoundError(Exception):
    """El propietario solicitado no existe."""


class PropietarioHasPropertiesError(Exception):
    """No se puede eliminar un propietario con inmuebles asociados."""


class DuplicatePropietarioValueError(Exception):
    """Un campo que debe ser único ya está registrado."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(field)


class PropietariosRepository(Protocol):
    def create(self, data: dict[str, object]) -> dict[str, object]: ...

    def list(
        self, *, page: int, page_size: int, search: str | None
    ) -> tuple[list[dict[str, object]], int]: ...

    def get_detail(self, propietario_id: UUID) -> dict[str, object] | None: ...

    def update(
        self, propietario_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None: ...

    def delete(self, propietario_id: UUID) -> bool: ...


class PropietariosService:
    """Orquesta validaciones de existencia y contratos de respuesta."""

    def __init__(self, repository: PropietariosRepository) -> None:
        self.repository = repository

    def create(self, payload: PropietarioCreate) -> PropietarioResponse:
        record = self.repository.create(payload.model_dump(mode="json"))
        return PropietarioResponse.model_validate(record)

    def list(
        self, *, page: int, page_size: int, search: str | None
    ) -> PropietariosPage:
        normalized_search = search.strip() if search and search.strip() else None
        items, total = self.repository.list(
            page=page,
            page_size=page_size,
            search=normalized_search,
        )
        return PropietariosPage.build(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_detail(self, propietario_id: UUID) -> PropietarioDetailResponse:
        record = self.repository.get_detail(propietario_id)
        if record is None:
            raise PropietarioNotFoundError
        return PropietarioDetailResponse.model_validate(record)

    def update(
        self, propietario_id: UUID, payload: PropietarioUpdate
    ) -> PropietarioResponse:
        record = self.repository.update(
            propietario_id,
            payload.model_dump(mode="json"),
        )
        if record is None:
            raise PropietarioNotFoundError
        return PropietarioResponse.model_validate(record)

    def delete(self, propietario_id: UUID) -> None:
        deleted = self.repository.delete(propietario_id)
        if not deleted:
            raise PropietarioNotFoundError
