"""Reglas del alta de reclamos, independientes de FastAPI y Supabase."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from app.schemas.reclamos import ClaimCreatedResponse, ClaimPropertyContext


MAX_PHOTOS = 3
MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_PHOTO_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
}
ALLOWED_URGENCIES = {"baja", "media", "alta"}


class ClaimValidationError(Exception):
    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.field = field


class TenantClaimContextError(Exception):
    """El usuario no tiene un inquilino activo con propiedad vinculada."""


class ActiveClaimExistsError(Exception):
    """Ya existe un reclamo no resuelto para la misma unidad e inquilino."""


class ClaimPhotoStorageError(Exception):
    """Una foto no pudo guardarse o limpiarse de forma segura."""


@dataclass(frozen=True)
class TenantClaimContext:
    tenant_id: UUID
    tenant_name: str
    tenant_email: str
    property: ClaimPropertyContext


@dataclass(frozen=True)
class ClaimPhotoUpload:
    content: bytes
    content_type: str
    filename: str


@dataclass(frozen=True)
class StoredClaimPhoto:
    id: UUID
    path: str
    format: str
    size_bytes: int


@dataclass(frozen=True)
class PersistedClaim:
    response: ClaimCreatedResponse
    notification_id: UUID


class ClaimCreationRepository(Protocol):
    def get_creation_context(
        self, *, user_id: UUID, profile_id: UUID
    ) -> TenantClaimContext | None: ...

    def has_active_claim(self, *, tenant_id: UUID, property_id: UUID) -> bool: ...

    def create_claim(
        self,
        *,
        claim_id: UUID,
        context: TenantClaimContext,
        description: str,
        urgency: str,
        photos: list[StoredClaimPhoto],
        user_id: UUID,
    ) -> PersistedClaim: ...


class ClaimPhotoStorage(Protocol):
    def upload(
        self,
        *,
        claim_id: UUID,
        tenant_id: UUID,
        photo_id: UUID,
        extension: str,
        content_type: str,
        content: bytes,
    ) -> str: ...

    def delete(self, path: str) -> None: ...


class ClaimCreationService:
    """Valida, guarda fotos y persiste el alta como una unidad lógica."""

    def __init__(
        self,
        repository: ClaimCreationRepository,
        storage: ClaimPhotoStorage,
    ) -> None:
        self.repository = repository
        self.storage = storage

    def get_context(self, *, user_id: UUID, profile_id: UUID | None) -> TenantClaimContext:
        if profile_id is None:
            raise TenantClaimContextError
        context = self.repository.get_creation_context(
            user_id=user_id,
            profile_id=profile_id,
        )
        if context is None:
            raise TenantClaimContextError
        return context

    def create(
        self,
        *,
        user_id: UUID,
        profile_id: UUID | None,
        description: str,
        urgency: str,
        photos: list[ClaimPhotoUpload],
    ) -> PersistedClaim:
        clean_description = description.strip()
        if not 20 <= len(clean_description) <= 1000:
            raise ClaimValidationError(
                "Describí el problema usando entre 20 y 1000 caracteres.",
                field="descripcion",
            )
        if urgency not in ALLOWED_URGENCIES:
            raise ClaimValidationError(
                "Seleccioná una urgencia válida.",
                field="urgencia",
            )
        if len(photos) > MAX_PHOTOS:
            raise ClaimValidationError(
                "Podés adjuntar hasta 3 fotos.",
                field="fotos",
            )

        context = self.get_context(user_id=user_id, profile_id=profile_id)
        if self.repository.has_active_claim(
            tenant_id=context.tenant_id,
            property_id=context.property.id,
        ):
            raise ActiveClaimExistsError

        claim_id = uuid4()
        stored_photos: list[StoredClaimPhoto] = []
        try:
            for photo in photos:
                image_format, extension = self._validate_photo(photo)
                photo_id = uuid4()
                path = self.storage.upload(
                    claim_id=claim_id,
                    tenant_id=context.tenant_id,
                    photo_id=photo_id,
                    extension=extension,
                    content_type=photo.content_type,
                    content=photo.content,
                )
                stored_photos.append(
                    StoredClaimPhoto(
                        id=photo_id,
                        path=path,
                        format=image_format,
                        size_bytes=len(photo.content),
                    )
                )

            return self.repository.create_claim(
                claim_id=claim_id,
                context=context,
                description=clean_description,
                urgency=urgency,
                photos=stored_photos,
                user_id=user_id,
            )
        except Exception:
            self._cleanup(stored_photos)
            raise

    @staticmethod
    def _validate_photo(photo: ClaimPhotoUpload) -> tuple[str, str]:
        if photo.content_type not in ALLOWED_PHOTO_TYPES:
            raise ClaimValidationError(
                "Las fotos deben ser JPG, JPEG o PNG.",
                field="fotos",
            )
        if not photo.content or len(photo.content) > MAX_PHOTO_BYTES:
            raise ClaimValidationError(
                "Cada foto debe pesar como máximo 5 MB.",
                field="fotos",
            )

        is_jpeg = photo.content.startswith(b"\xff\xd8\xff")
        is_png = photo.content.startswith(b"\x89PNG\r\n\x1a\n")
        if (photo.content_type == "image/jpeg" and not is_jpeg) or (
            photo.content_type == "image/png" and not is_png
        ):
            raise ClaimValidationError(
                "El contenido de una foto no coincide con su formato.",
                field="fotos",
            )
        return ALLOWED_PHOTO_TYPES[photo.content_type]

    def _cleanup(self, photos: list[StoredClaimPhoto]) -> None:
        cleanup_failed = False
        for photo in photos:
            try:
                self.storage.delete(photo.path)
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            raise ClaimPhotoStorageError(
                "No se pudo revertir por completo la carga de fotos."
            )
