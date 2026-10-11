"""HU15: accesible solamente al personal activo de la inmobiliaria."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import require_roles
from app.db.provider_candidates import SqlAlchemyProviderCandidatesRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.provider_candidates import (
    CandidateClaimsPage, CandidateProvidersPage, CandidateSearchExecution, CandidateSearchRequest,
)
from app.schemas.proveedores import EspecialidadResponse
from app.services.provider_candidates_service import (
    CandidateClaimNotFoundError, CandidateSearchConflictError, CandidateSearchPermissionError,
    CandidateSpecialtyNotFoundError, ProviderCandidatesService,
)

router = APIRouter(prefix="/reclamos", tags=["proveedores candidatos"])
require_staff = require_roles("administrador", "operador")


def get_candidates_repository():
    return SqlAlchemyProviderCandidatesRepository()


def get_candidates_service(repository=Depends(get_candidates_repository)):
    return ProviderCandidatesService(repository)


@router.get("/pendientes-asignacion", response_model=CandidateClaimsPage)
def pending_assignment(
    page: int = Query(1, ge=1, le=1_000_000),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=200),
    user: AuthenticatedUser = Depends(require_staff),
    repository=Depends(get_candidates_repository),
):
    return repository.list(page=page, page_size=page_size, search=search)


@router.get("/especialidades-proveedores", response_model=list[EspecialidadResponse])
def candidate_specialties(
    user: AuthenticatedUser = Depends(require_staff), repository=Depends(get_candidates_repository),
):
    return repository.specialties()


@router.get("/{reclamo_id}/proveedores-candidatos", response_model=CandidateProvidersPage)
def get_candidates(
    reclamo_id: UUID,
    page: int = Query(1, ge=1, le=1_000_000),
    page_size: int = Query(20, ge=1, le=100),
    audit_page: int = Query(1, ge=1, le=1_000_000),
    user: AuthenticatedUser = Depends(require_staff), repository=Depends(get_candidates_repository),
):
    try:
        return repository.get(reclamo_id, page=page, page_size=page_size, audit_page=audit_page)
    except CandidateClaimNotFoundError as error:
        raise HTTPException(404, detail={"code": "claim_not_found", "message": "No encontramos ese reclamo en este circuito."}) from error


@router.post("/{reclamo_id}/buscar-proveedores", response_model=CandidateSearchExecution)
def search_candidates(
    reclamo_id: UUID, request: CandidateSearchRequest,
    user: AuthenticatedUser = Depends(require_staff), service=Depends(get_candidates_service),
):
    try:
        return service.search(reclamo_id, request, user)
    except CandidateClaimNotFoundError as error:
        raise HTTPException(404, detail={"code": "claim_not_found", "message": "No encontramos ese reclamo en este circuito."}) from error
    except CandidateSearchConflictError as error:
        raise HTTPException(409, detail={"code": "claim_changed", "message": str(error)}) from error
    except CandidateSearchPermissionError as error:
        raise HTTPException(403, detail={"code": "forbidden", "message": "Tu cuenta no puede registrar esta búsqueda."}) from error
    except CandidateSpecialtyNotFoundError as error:
        raise HTTPException(422, detail={"code": "specialty_not_found", "field": "especialidad_id",
                                       "message": "La especialidad ya no existe. Actualizá el catálogo."}) from error
