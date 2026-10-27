"""Administración de acceso, activación pública y perfil privado HU32."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.auth import require_admin, require_roles
from app.db.provider_access import SqlAlchemyProviderAccessRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.provider_access import (
    ProviderAccessResponse, ProviderActivationRequest, ProviderInvitationRequest, ProviderProfileResponse,
)
from app.services.provider_access_service import ProviderAccessError, ProviderAccessService


router = APIRouter(tags=["acceso de proveedores"])
require_provider = require_roles("proveedor")


def get_provider_access_service():
    return ProviderAccessService(SqlAlchemyProviderAccessRepository())


def _call(operation):
    try:
        return operation()
    except ProviderAccessError as error:
        detail = {"code": error.code, "message": str(error)}
        if error.field_name:
            detail["field"] = error.field_name
        raise HTTPException(status_code=error.status, detail=detail) from None


@router.get("/proveedores/{provider_id}/acceso", response_model=ProviderAccessResponse,
            dependencies=[Depends(require_admin)])
def access_status(provider_id: UUID, response: Response, service=Depends(get_provider_access_service)):
    response.headers["Cache-Control"] = "no-store"
    return _call(lambda: service.get(provider_id))


@router.post("/proveedores/{provider_id}/acceso", response_model=ProviderAccessResponse,
             dependencies=[Depends(require_admin)])
def invite_provider(provider_id: UUID, payload: ProviderInvitationRequest, response: Response,
                    service=Depends(get_provider_access_service)):
    response.headers["Cache-Control"] = "no-store"
    return _call(lambda: service.invite(provider_id, payload))


@router.post("/auth/proveedores/activar")
def activate_provider(payload: ProviderActivationRequest, response: Response,
                      service=Depends(get_provider_access_service)):
    response.headers["Cache-Control"] = "no-store"
    _call(lambda: service.activate(payload))
    return {"message": "Tu cuenta fue activada. Ya podés iniciar sesión."}


@router.get("/proveedor/perfil", response_model=ProviderProfileResponse)
def provider_profile(response: Response, user: AuthenticatedUser = Depends(require_provider),
                     service=Depends(get_provider_access_service)):
    response.headers["Cache-Control"] = "no-store"
    return _call(lambda: service.profile(user))
