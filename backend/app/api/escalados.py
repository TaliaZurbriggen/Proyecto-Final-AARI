"""Endpoints HU13, protegidos para el personal activo de la inmobiliaria."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response

from app.agents.classification.graph import build_manual_classification_graph
from app.api.auth import require_roles
from app.api.reclamos import get_claim_notification_service
from app.db.escalados import SqlAlchemyEscalatedClaimsRepository
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.escalados import (
    EscalatedClaimDetail, EscalatedClaimsPage, ManualClassificationRequest,
    ManualClassificationResponse,
)
from app.services.claim_notifications import ClaimNotificationService
from app.services.claim_storage import SupabaseClaimPhotoStorage
from app.services.claims_creation_service import ClaimPhotoStorageError
from app.services.escalated_claims_service import (
    EscalatedClaimNotFoundError, EscalatedClaimsService, ManualClassificationConflictError,
    ManualClassificationPermissionError,
)


router = APIRouter(prefix="/reclamos", tags=["casos escalados"])
require_staff = require_roles("administrador", "operador")


def get_escalated_repository():
    return SqlAlchemyEscalatedClaimsRepository()


def get_manual_service():
    return EscalatedClaimsService(SqlAlchemyClaimsRepository(), build_manual_classification_graph())


def get_staff_photo_storage():
    return SupabaseClaimPhotoStorage()


def not_found():
    return HTTPException(404, detail={"code": "claim_not_found", "message": "No encontramos ese reclamo o adjunto."})


@router.get("/escalados", response_model=EscalatedClaimsPage)
def list_escalated_claims(
    page: int = Query(default=1, ge=1, le=1_000_000),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=200),
    user: AuthenticatedUser = Depends(require_staff),
    repository=Depends(get_escalated_repository),
):
    return repository.list(page=page, page_size=page_size, search=search)


@router.get("/escalados/{reclamo_id}", response_model=EscalatedClaimDetail)
def get_escalated_claim(
    reclamo_id: UUID, user: AuthenticatedUser = Depends(require_staff),
    repository=Depends(get_escalated_repository),
):
    try:
        return repository.get(reclamo_id)
    except EscalatedClaimNotFoundError as error:
        raise not_found() from error


@router.get("/escalados/{reclamo_id}/fotos/{foto_id}")
def get_escalated_photo(
    reclamo_id: UUID, foto_id: UUID, user: AuthenticatedUser = Depends(require_staff),
    repository=Depends(get_escalated_repository), storage=Depends(get_staff_photo_storage),
):
    try:
        reference = repository.photo(reclamo_id, foto_id)
        content = storage.download(reference["url"])
    except EscalatedClaimNotFoundError as error:
        raise not_found() from error
    except ClaimPhotoStorageError as error:
        raise HTTPException(503, detail={"code": "photo_unavailable", "message": str(error)}) from error
    return Response(content=content, media_type="image/png" if reference["formato"] == "PNG" else "image/jpeg",
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{reclamo_id}/resolver-escalado", response_model=ManualClassificationResponse)
def resolve_escalated_claim(
    reclamo_id: UUID, request: ManualClassificationRequest, background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(require_staff), service=Depends(get_manual_service),
    notifications: ClaimNotificationService = Depends(get_claim_notification_service),
):
    try:
        saved = service.resolve(reclamo_id, request, user)
    except EscalatedClaimNotFoundError as error:
        raise not_found() from error
    except ManualClassificationPermissionError as error:
        raise HTTPException(403, detail={"code": "forbidden", "message": "Tu cuenta no puede aplicar esta decisión."}) from error
    except ManualClassificationConflictError as error:
        raise HTTPException(409, detail={"code": "claim_changed", "message": str(error)}) from error
    if saved.notification_id is not None:
        background_tasks.add_task(notifications.deliver, saved.notification_id)
    return saved.response
