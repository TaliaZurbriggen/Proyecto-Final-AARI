"""Reglas de aplicación para la gestión de propietarios."""

from typing import Protocol
from uuid import UUID

from app.services.access_service import AccessInvitationService
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

    def __init__(
        self,
        repository: PropietariosRepository,
        access_service: AccessInvitationService | None = None,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    def create(self, payload: PropietarioCreate) -> PropietarioResponse:
        record = self.repository.create(payload.model_dump(mode="json"))
        if self.access_service is not None:
            self.access_service.deliver(
                user_id=UUID(str(record["usuario_id"])),
                recipient=payload.email,
                person_name=payload.nombre_completo,
                temporary_password=payload.dni,
            )
            refreshed = self.repository.get_detail(UUID(str(record["id"])))
            if refreshed is not None:
                record = refreshed
        return PropietarioResponse.model_validate(record)

    def retry_access(self, propietario_id: UUID) -> PropietarioDetailResponse:
        if self.repository.get_detail(propietario_id) is None:
            raise PropietarioNotFoundError
        if self.access_service is None:  # pragma: no cover - error de composición
            raise RuntimeError("El servicio de acceso no está configurado.")
        self.access_service.retry(entity="propietario", entity_id=propietario_id)
        return self.get_detail(propietario_id)

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
