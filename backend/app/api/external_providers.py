"""HU18: registro por el responsable y consulta privada del contacto externo."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import require_roles
from app.db.external_providers import SqlAlchemyExternalProvidersRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.external_providers import ExternalProviderDetail, ExternalProviderRequest, ExternalProviderResult
from app.services.external_providers_service import ExternalProviderError

router = APIRouter(tags=["proveedor externo"])
reader = require_roles("administrador", "inquilino", "propietario")
writer = require_roles("inquilino", "propietario")


def get_external_providers_repository():
    return SqlAlchemyExternalProvidersRepository()


def run(action):
    try:
        return action()
    except ExternalProviderError as error:
        raise HTTPException(error.status, detail={"code": error.code, "message": str(error)},
                            headers={"Cache-Control": "no-store"}) from None
    except SQLAlchemyError:
        raise HTTPException(503, detail={"code": "external_provider_unavailable",
            "message": "No pudimos consultar o guardar el proveedor. Volvé a intentarlo."},
            headers={"Cache-Control": "no-store"}) from None


@router.get("/reclamos/{claim_id}/proveedor-externo", response_model=ExternalProviderDetail)
def get_external_provider(claim_id: UUID, response: Response, user: AuthenticatedUser = Depends(reader),
                          repository=Depends(get_external_providers_repository)):
    response.headers["Cache-Control"] = "no-store"
    return run(lambda: repository.get(claim_id, user))


@router.post("/reclamos/{claim_id}/proveedor-externo", response_model=ExternalProviderResult)
def register_external_provider(claim_id: UUID, body: ExternalProviderRequest, response: Response,
                               user: AuthenticatedUser = Depends(writer),
                               repository=Depends(get_external_providers_repository)):
    response.headers["Cache-Control"] = "no-store"
    return run(lambda: repository.register(claim_id, user, body))
