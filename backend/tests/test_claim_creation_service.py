"""Pruebas unitarias del alta sin Supabase, Storage ni SMTP reales."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.schemas.reclamos import ClaimCreatedResponse, ClaimPropertyContext
from app.services.claims_creation_service import (
    ActiveClaimExistsError,
    ClaimCreationService,
    ClaimPhotoUpload,
    ClaimValidationError,
    PersistedClaim,
    StoredClaimPhoto,
    TenantClaimContext,
    TenantClaimContextError,
)


USER_ID = uuid4()
TENANT_ID = uuid4()
PROPERTY_ID = uuid4()
CONTEXT = TenantClaimContext(
    tenant_id=TENANT_ID,
    tenant_name="Lucía Pérez",
    tenant_email="lucia@example.com",
    property=ClaimPropertyContext(
        id=PROPERTY_ID,
        direccion="Av. San Martín 120",
        provincia="Santa Fe",
        localidad="San Francisco",
        barrio="Centro",
        tipo="departamento",
        piso=0,
        numero="B",
    ),
)


@dataclass
class FakeRepository:
    context: TenantClaimContext | None = CONTEXT
    active: bool = False
    fail_create: bool = False
    created_photos: list[StoredClaimPhoto] = field(default_factory=list)
    created_description: str | None = None

    def get_creation_context(
        self, *, user_id: UUID, profile_id: UUID
    ) -> TenantClaimContext | None:
        return self.context if user_id == USER_ID and profile_id == TENANT_ID else None

    def has_active_claim(self, *, tenant_id: UUID, property_id: UUID) -> bool:
        assert tenant_id == TENANT_ID
        assert property_id == PROPERTY_ID
        return self.active

    def create_claim(self, **data) -> PersistedClaim:
        if self.fail_create:
            raise RuntimeError("fallo simulado")
        self.created_photos = data["photos"]
        self.created_description = data["description"]
        return PersistedClaim(
            response=ClaimCreatedResponse(
                id=data["claim_id"],
                numero=7,
                estado="Recibido",
                creado_en=datetime(2026, 9, 4, 12, tzinfo=UTC),
                fotos_adjuntas=len(data["photos"]),
            ),
            notification_id=uuid4(),
        )


@dataclass
class FakeStorage:
    uploaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def upload(self, **data) -> str:
        path = (
            f"{data['tenant_id']}/{data['claim_id']}/"
            f"{data['photo_id']}{data['extension']}"
        )
        self.uploaded.append(path)
        return path

    def delete(self, path: str) -> None:
        self.deleted.append(path)


def png_photo(name: str = "cocina.png") -> ClaimPhotoUpload:
    return ClaimPhotoUpload(
        content=b"\x89PNG\r\n\x1a\ncontenido",
        content_type="image/png",
        filename=name,
    )


def test_creates_claim_with_private_photo_path_and_trimmed_description():
    repository = FakeRepository()
    storage = FakeStorage()
    service = ClaimCreationService(repository, storage)

    result = service.create(
        user_id=USER_ID,
        profile_id=TENANT_ID,
        description="  La canilla de la cocina pierde agua desde ayer.  ",
        urgency="media",
        photos=[png_photo()],
    )

    assert result.response.numero == 7
    assert result.response.fotos_adjuntas == 1
    assert repository.created_description == "La canilla de la cocina pierde agua desde ayer."
    assert repository.created_photos[0].path == storage.uploaded[0]
    assert "cocina.png" not in storage.uploaded[0]


def test_rejects_second_active_claim_before_uploading_photos():
    storage = FakeStorage()
    service = ClaimCreationService(FakeRepository(active=True), storage)

    with pytest.raises(ActiveClaimExistsError):
        service.create(
            user_id=USER_ID,
            profile_id=TENANT_ID,
            description="La canilla de la cocina pierde agua desde ayer.",
            urgency="media",
            photos=[png_photo()],
        )

    assert storage.uploaded == []


def test_rejects_mime_that_does_not_match_file_contents():
    service = ClaimCreationService(FakeRepository(), FakeStorage())
    fake = ClaimPhotoUpload(
        content=b"no-es-una-imagen",
        content_type="image/png",
        filename="foto.png",
    )

    with pytest.raises(ClaimValidationError, match="no coincide") as captured:
        service.create(
            user_id=USER_ID,
            profile_id=TENANT_ID,
            description="La canilla de la cocina pierde agua desde ayer.",
            urgency="media",
            photos=[fake],
        )

    assert captured.value.field == "fotos"


def test_rejects_description_shorter_than_twenty_characters():
    service = ClaimCreationService(FakeRepository(), FakeStorage())

    with pytest.raises(ClaimValidationError, match="20 y 1000") as captured:
        service.create(
            user_id=USER_ID,
            profile_id=TENANT_ID,
            description="Pierde agua.",
            urgency="media",
            photos=[],
        )

    assert captured.value.field == "descripcion"


def test_removes_uploaded_photos_when_database_persistence_fails():
    storage = FakeStorage()
    service = ClaimCreationService(FakeRepository(fail_create=True), storage)

    with pytest.raises(RuntimeError, match="fallo simulado"):
        service.create(
            user_id=USER_ID,
            profile_id=TENANT_ID,
            description="La canilla de la cocina pierde agua desde ayer.",
            urgency="baja",
            photos=[png_photo()],
        )

    assert storage.deleted == storage.uploaded


def test_rejects_user_without_active_tenant_property_context():
    service = ClaimCreationService(FakeRepository(context=None), FakeStorage())

    with pytest.raises(TenantClaimContextError):
        service.get_context(user_id=USER_ID, profile_id=TENANT_ID)
