"""Rutas HTTP para administrar propietarios."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.db.access import SqlAlchemyAccessRepository
from app.db.propietarios import SqlAlchemyPropietariosRepository
from app.schemas.propietarios import (
    PropietarioCreate,
    PropietarioDetailResponse,
    PropietarioResponse,
    PropietariosPage,
    PropietarioUpdate,
)
from app.services.propietarios_service import (
    DuplicatePropietarioValueError,
    PropietarioHasPropertiesError,
    PropietarioNotFoundError,
    PropietariosService,
)
from app.services.access_service import (
    AccessAlreadyActivatedError,
    AccessInvitationService,
    AccessNotFoundError,
    SmtpWelcomeEmailSender,
)

router = APIRouter(prefix="/propietarios", tags=["propietarios"])


def get_propietarios_service() -> PropietariosService:
    return PropietariosService(
        SqlAlchemyPropietariosRepository(),
        AccessInvitationService(
            SqlAlchemyAccessRepository(),
            SmtpWelcomeEmailSender(),
        ),
    )


def _duplicate_value_error(error: DuplicatePropietarioValueError) -> HTTPException:
    labels = {"dni": "DNI", "email": "email"}
    label = labels.get(error.field, error.field)
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "duplicate_field",
            "field": error.field,
            "message": f"Ya existe un propietario con ese {label}.",
        },
    )


@router.post(
    "",
    response_model=PropietarioResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_propietario(
    payload: PropietarioCreate,
    service: PropietariosService = Depends(get_propietarios_service),
) -> PropietarioResponse:
    try:
        return service.create(payload)
    except DuplicatePropietarioValueError as error:
        raise _duplicate_value_error(error) from error


@router.get("", response_model=PropietariosPage)
def list_propietarios(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=120),
    service: PropietariosService = Depends(get_propietarios_service),
) -> PropietariosPage:
    return service.list(page=page, page_size=page_size, search=search)


@router.get("/{propietario_id}", response_model=PropietarioDetailResponse)
def get_propietario(
    propietario_id: UUID,
    service: PropietariosService = Depends(get_propietarios_service),
) -> PropietarioDetailResponse:
    try:
        return service.get_detail(propietario_id)
    except PropietarioNotFoundError as error:
        raise HTTPException(status_code=404, detail="Propietario no encontrado.") from error


@router.post(
    "/{propietario_id}/acceso/reintentar",
    response_model=PropietarioDetailResponse,
)
def retry_propietario_access(
    propietario_id: UUID,
    service: PropietariosService = Depends(get_propietarios_service),
) -> PropietarioDetailResponse:
    try:
        return service.retry_access(propietario_id)
    except (PropietarioNotFoundError, AccessNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No encontramos una cuenta vinculada al propietario.",
        ) from error
    except AccessAlreadyActivatedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "access_already_activated",
                "message": "La cuenta ya fue activada y no usa la contraseña temporal.",
            },
        ) from error


@router.put("/{propietario_id}", response_model=PropietarioResponse)
def update_propietario(
    propietario_id: UUID,
    payload: PropietarioUpdate,
    service: PropietariosService = Depends(get_propietarios_service),
) -> PropietarioResponse:
    try:
        return service.update(propietario_id, payload)
    except PropietarioNotFoundError as error:
        raise HTTPException(status_code=404, detail="Propietario no encontrado.") from error
    except DuplicatePropietarioValueError as error:
        raise _duplicate_value_error(error) from error


@router.delete("/{propietario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_propietario(
    propietario_id: UUID,
    service: PropietariosService = Depends(get_propietarios_service),
) -> Response:
    try:
        service.delete(propietario_id)
    except PropietarioNotFoundError as error:
        raise HTTPException(status_code=404, detail="Propietario no encontrado.") from error
    except PropietarioHasPropertiesError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "owner_has_properties",
                "message": (
                    "No se puede eliminar el propietario porque tiene "
                    "inmuebles asociados."
                ),
            },
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
