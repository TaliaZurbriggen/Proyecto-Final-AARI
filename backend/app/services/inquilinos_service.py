"""Reglas de aplicación para la gestión de inquilinos."""

from typing import Protocol
from uuid import UUID

from app.schemas.inquilinos import (
    InquilinoCreate,
    InquilinoResponse,
    InquilinosPage,
    InquilinoUpdate,
)


class InquilinoNotFoundError(Exception):
    """El inquilino solicitado no existe."""


class InquilinoDuplicateDniError(Exception):
    """El DNI ya identifica a otro inquilino."""


class InquilinoDuplicateEmailError(Exception):
    """El email normalizado ya identifica a otro inquilino."""


class InquilinoPropertyNotFoundError(Exception):
    """La propiedad seleccionada no existe."""


class InquilinoPropertyOccupiedError(Exception):
    """La propiedad ya tiene un inquilino activo."""


class InquilinoHasClaimsError(Exception):
    """El inquilino conserva reclamos históricos y no puede eliminarse."""


class InquilinosRepository(Protocol):
    def create(self, data: dict[str, object]) -> dict[str, object]: ...

    def list(
        self, *, page: int, page_size: int, search: str | None
    ) -> tuple[list[dict[str, object]], int]: ...

    def get_detail(self, inquilino_id: UUID) -> dict[str, object] | None: ...

    def property_exists(self, propiedad_id: UUID) -> bool: ...

    def get_active_by_property(
        self, propiedad_id: UUID
    ) -> dict[str, object] | None: ...

    def update(
        self, inquilino_id: UUID, data: dict[str, object]
    ) -> dict[str, object] | None: ...

    def disassociate(self, inquilino_id: UUID) -> dict[str, object] | None: ...

    def delete(self, inquilino_id: UUID) -> bool: ...


class InquilinosService:
    """Orquesta asociaciones, estados y contratos de respuesta."""

    def __init__(self, repository: InquilinosRepository) -> None:
        self.repository = repository

    def create(self, payload: InquilinoCreate) -> InquilinoResponse:
        record = self.repository.create(payload.model_dump(mode="json"))
        return InquilinoResponse.model_validate(record)

    def list(
        self, *, page: int, page_size: int, search: str | None
    ) -> InquilinosPage:
        normalized_search = search.strip() if search and search.strip() else None
        items, total = self.repository.list(
            page=page,
            page_size=page_size,
            search=normalized_search,
        )
        return InquilinosPage.build(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_detail(self, inquilino_id: UUID) -> InquilinoResponse:
        record = self.repository.get_detail(inquilino_id)
        if record is None:
            raise InquilinoNotFoundError
        return InquilinoResponse.model_validate(record)

    def get_by_property(self, propiedad_id: UUID) -> InquilinoResponse | None:
        if not self.repository.property_exists(propiedad_id):
            raise InquilinoPropertyNotFoundError
        record = self.repository.get_active_by_property(propiedad_id)
        return InquilinoResponse.model_validate(record) if record else None

    def update(
        self, inquilino_id: UUID, payload: InquilinoUpdate
    ) -> InquilinoResponse:
        record = self.repository.update(
            inquilino_id,
            payload.model_dump(mode="json"),
        )
        if record is None:
            raise InquilinoNotFoundError
        return InquilinoResponse.model_validate(record)

    def disassociate(self, inquilino_id: UUID) -> InquilinoResponse:
        record = self.repository.disassociate(inquilino_id)
        if record is None:
            raise InquilinoNotFoundError
        return InquilinoResponse.model_validate(record)

    def delete(self, inquilino_id: UUID) -> None:
        if not self.repository.delete(inquilino_id):
            raise InquilinoNotFoundError
