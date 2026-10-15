"""Acceso por participante; no expone comandos arbitrarios del grafo."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.agents.coordination.state import CoordinationResponse, ResumeRequest
from app.api.auth import require_roles
from app.db.coordination import PostgresCoordinationRepository
from app.schemas.auth import AuthenticatedUser
from app.services.coordination_service import CoordinationError, CoordinationService


router = APIRouter(prefix="/reclamos", tags=["coordinación"])
require_participant = require_roles("administrador", "operador", "propietario", "inquilino")


def get_coordination_service():
    return CoordinationService(PostgresCoordinationRepository())


@router.get("/{reclamo_id}/coordinacion", response_model=CoordinationResponse)
def get_context(reclamo_id: UUID, user: AuthenticatedUser = Depends(require_participant),
                service: CoordinationService = Depends(get_coordination_service)):
    try:
        return service.get(reclamo_id, user)
    except CoordinationError as error:
        raise HTTPException(error.status, detail={"code": error.code, "message": str(error)}) from None


@router.post("/{reclamo_id}/coordinacion/retomar", response_model=CoordinationResponse)
def resume_context(reclamo_id: UUID, request: ResumeRequest,
                   user: AuthenticatedUser = Depends(require_participant),
                   service: CoordinationService = Depends(get_coordination_service)):
    try:
        return service.resume(reclamo_id, request, user)
    except CoordinationError as error:
        raise HTTPException(error.status, detail={"code": error.code, "message": str(error)}) from None
