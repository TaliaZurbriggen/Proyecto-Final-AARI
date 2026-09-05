"""Rutas HTTP para el alta y la clasificación de reclamos."""

from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from app.agents.classification.graph import build_classification_graph
from app.api.auth import require_inquilino
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.reclamos import (
    ClaimClassificationResponse,
    ClaimContextResponse,
    ClaimCreatedResponse,
)
from app.services.claim_notifications import (
    ClaimNotificationService,
    SmtpClaimEmailSender,
)
from app.services.claim_storage import SupabaseClaimPhotoStorage
from app.services.classification_service import ClaimNotFoundError, ClassificationService
from app.services.claims_creation_service import (
    MAX_PHOTO_BYTES,
    ActiveClaimExistsError,
    ClaimCreationService,
    ClaimPhotoStorageError,
    ClaimPhotoUpload,
    ClaimValidationError,
    TenantClaimContextError,
)

router = APIRouter(prefix="/reclamos", tags=["reclamos"])


def get_classification_service() -> ClassificationService:
    """Construye las dependencias de producción de la clasificación."""

    return ClassificationService(SqlAlchemyClaimsRepository(), build_classification_graph())


def get_claim_creation_service() -> ClaimCreationService:
    return ClaimCreationService(
        SqlAlchemyClaimsRepository(),
        SupabaseClaimPhotoStorage(),
    )


def get_claim_notification_service() -> ClaimNotificationService:
    return ClaimNotificationService(
        SqlAlchemyClaimsRepository(),
        SmtpClaimEmailSender(),
    )


def _claim_error(
    *, code: str, message: str, field: str | None = None, status_code: int
) -> HTTPException:
    detail = {"code": code, "message": message}
    if field:
        detail["field"] = field
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/contexto", response_model=ClaimContextResponse)
def get_claim_context(
    user: AuthenticatedUser = Depends(require_inquilino),
    service: ClaimCreationService = Depends(get_claim_creation_service),
) -> ClaimContextResponse:
    """Devuelve la identidad y unidad que se usarán en el alta."""

    try:
        context = service.get_context(user_id=user.id, profile_id=user.perfil_id)
    except TenantClaimContextError as error:
        raise _claim_error(
            code="tenant_context_unavailable",
            message="Tu cuenta no tiene una propiedad activa asociada.",
            status_code=status.HTTP_409_CONFLICT,
        ) from error
    return ClaimContextResponse(
        inquilino_nombre=context.tenant_name,
        inquilino_email=context.tenant_email,
        propiedad=context.property,
    )


@router.post(
    "",
    response_model=ClaimCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_claim(
    background_tasks: BackgroundTasks,
    descripcion: str = Form(...),
    urgencia: str = Form(...),
    fotos: list[UploadFile] = File(default=[]),
    user: AuthenticatedUser = Depends(require_inquilino),
    service: ClaimCreationService = Depends(get_claim_creation_service),
    notification_service: ClaimNotificationService = Depends(
        get_claim_notification_service
    ),
) -> ClaimCreatedResponse:
    """Persiste el reclamo y agenda la confirmación por correo."""

    uploads: list[ClaimPhotoUpload] = []
    for photo in fotos:
        content = await photo.read(MAX_PHOTO_BYTES + 1)
        await photo.close()
        uploads.append(
            ClaimPhotoUpload(
                content=content,
                content_type=photo.content_type or "",
                filename=photo.filename or "foto",
            )
        )

    try:
        created = service.create(
            user_id=user.id,
            profile_id=user.perfil_id,
            description=descripcion,
            urgency=urgencia,
            photos=uploads,
        )
    except ClaimValidationError as error:
        raise _claim_error(
            code="invalid_claim",
            message=str(error),
            field=error.field,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from error
    except TenantClaimContextError as error:
        raise _claim_error(
            code="tenant_context_unavailable",
            message="Tu cuenta no tiene una propiedad activa asociada.",
            status_code=status.HTTP_409_CONFLICT,
        ) from error
    except ActiveClaimExistsError as error:
        raise _claim_error(
            code="active_claim_exists",
            message=(
                "Ya tenés un reclamo activo para esta unidad. "
                "Esperá su resolución antes de crear otro."
            ),
            status_code=status.HTTP_409_CONFLICT,
        ) from error
    except ClaimPhotoStorageError as error:
        raise _claim_error(
            code="photo_storage_unavailable",
            message=str(error),
            field="fotos",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from error

    background_tasks.add_task(
        notification_service.deliver,
        created.notification_id,
    )
    return created.response


@router.post(
    "/{reclamo_id}/clasificar",
    response_model=ClaimClassificationResponse,
    status_code=status.HTTP_200_OK,
)
def classify_claim(
    reclamo_id: UUID,
    service: ClassificationService = Depends(get_classification_service),
) -> ClaimClassificationResponse:
    """Clasifica un reclamo existente y persiste clasificación o escalado."""

    try:
        return service.classify(reclamo_id)
    except ClaimNotFoundError as error:
        raise HTTPException(status_code=404, detail="Reclamo no encontrado.") from error
