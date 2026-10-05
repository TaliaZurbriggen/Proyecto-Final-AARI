"""HU11: rutas de lectura con permisos propios, separadas del CRUD administrativo."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.auth import require_roles
from app.db.property_claims import SqlAlchemyPropertyClaimsRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.property_claims import PropertyClaimDetail, PropertyClaimsFilters, PropertyClaimsPage
from app.services.property_claims_service import (
    PropertyClaimsService,
    PropertyHistoryClaimNotFoundError,
    PropertyHistoryForbiddenError,
    PropertyHistoryNotFoundError,
)


router = APIRouter(prefix="/propiedades", tags=["historial de reclamos"])
require_property_claim_reader = require_roles("administrador", "inquilino")


def get_property_claims_service() -> PropertyClaimsService:
    return PropertyClaimsService(SqlAlchemyPropertyClaimsRepository())


def history_error(error: Exception) -> HTTPException:
    if isinstance(error, PropertyHistoryForbiddenError):
        return HTTPException(status_code=403, detail={
            "code": "property_history_forbidden",
            "message": "No tenés permiso para consultar el historial de esta propiedad.",
        })
    if isinstance(error, PropertyHistoryNotFoundError):
        return HTTPException(status_code=404, detail={
            "code": "property_not_found", "message": "Propiedad no encontrada.",
        })
    return HTTPException(status_code=404, detail={
        "code": "claim_not_found", "message": "No encontramos ese reclamo en este historial.",
    })


@router.get("/{property_id}/reclamos", response_model=PropertyClaimsPage)
def list_property_claims(
    property_id: UUID,
    response: Response,
    filters: Annotated[PropertyClaimsFilters, Query()],
    user: AuthenticatedUser = Depends(require_property_claim_reader),
    service: PropertyClaimsService = Depends(get_property_claims_service),
) -> PropertyClaimsPage:
    try:
        result = service.list(property_id=property_id, user=user, filters=filters)
    except (PropertyHistoryForbiddenError, PropertyHistoryNotFoundError) as error:
        raise history_error(error) from error
    response.headers["X-Total-Count"] = str(result.total)
    return result


@router.get("/{property_id}/reclamos/{claim_id}", response_model=PropertyClaimDetail)
def get_property_claim(
    property_id: UUID,
    claim_id: UUID,
    user: AuthenticatedUser = Depends(require_property_claim_reader),
    service: PropertyClaimsService = Depends(get_property_claims_service),
) -> PropertyClaimDetail:
    try:
        return service.get(property_id=property_id, claim_id=claim_id, user=user)
    except (PropertyHistoryForbiddenError, PropertyHistoryNotFoundError,
            PropertyHistoryClaimNotFoundError) as error:
        raise history_error(error) from error
