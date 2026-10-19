"""HU17: sólo el actor autenticado responsable puede elegir."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import require_roles
from app.db.provider_choices import SqlAlchemyProviderChoicesRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.provider_choices import ProviderChoiceDetail, ProviderChoiceRequest, ProviderChoiceResult
from app.services.provider_choices_service import ProviderChoiceConflict, ProviderChoiceForbidden, ProviderChoiceNotFound

router = APIRouter(tags=["elección de proveedor"])
require_actor = require_roles("inquilino", "propietario")


def get_provider_choices_repository():
    return SqlAlchemyProviderChoicesRepository()


def run(action):
    try:
        return action()
    except ProviderChoiceNotFound:
        raise HTTPException(404, detail={"code": "not_found", "message": "No encontramos una elección de proveedor para tu cuenta."}) from None
    except ProviderChoiceForbidden:
        raise HTTPException(403, detail={"code": "forbidden", "message": "Tu cuenta no puede registrar esta elección."}) from None
    except ProviderChoiceConflict as error:
        raise HTTPException(409, detail={"code": "choice_conflict", "message": str(error)}) from error


@router.get("/reclamos/{claim_id}/tipo-proveedor", response_model=ProviderChoiceDetail)
def get_choice(claim_id: UUID, user: AuthenticatedUser = Depends(require_actor),
               repository=Depends(get_provider_choices_repository)):
    return run(lambda: repository.get(claim_id, user))


@router.post("/reclamos/{claim_id}/tipo-proveedor", response_model=ProviderChoiceResult)
def choose(claim_id: UUID, body: ProviderChoiceRequest, user: AuthenticatedUser = Depends(require_actor),
           repository=Depends(get_provider_choices_repository)):
    return run(lambda: repository.choose(claim_id, user, body))
