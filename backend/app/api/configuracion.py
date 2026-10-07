"""HU14: solo administración gestiona el contacto de la inmobiliaria."""

from fastapi import APIRouter, Depends

from app.api.auth import require_roles
from app.db.configuracion import SqlAlchemyAgencyConfigurationRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.expensas import AgencyEmailRequest, AgencyEmailResponse


router = APIRouter(prefix="/configuracion", tags=["configuración de inmobiliaria"])
require_agency_admin = require_roles("administrador")


def get_agency_configuration_repository():
    return SqlAlchemyAgencyConfigurationRepository()


@router.get("/correo-inmobiliaria", response_model=AgencyEmailResponse)
def get_agency_email(user: AuthenticatedUser = Depends(require_agency_admin),
                     repository=Depends(get_agency_configuration_repository)):
    return repository.get()


@router.put("/correo-inmobiliaria", response_model=AgencyEmailResponse)
def update_agency_email(payload: AgencyEmailRequest,
                        user: AuthenticatedUser = Depends(require_agency_admin),
                        repository=Depends(get_agency_configuration_repository)):
    return repository.update(payload.email)
