"""Rutas HTTP para administrar inquilinos y su asociación actual."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.db.access import SqlAlchemyAccessRepository
from app.db.inquilinos import SqlAlchemyInquilinosRepository
from app.schemas.inquilinos import (
    InquilinoCreate,
    InquilinoResponse,
    InquilinosPage,
    InquilinoUpdate,
)
from app.services.inquilinos_service import (
    InquilinoDuplicateDniError,
    InquilinoDuplicateEmailError,
    InquilinoHasClaimsError,
    InquilinoNotFoundError,
    InquilinoPropertyNotFoundError,
    InquilinoPropertyOccupiedError,
    InquilinosService,
)
from app.services.access_service import (
    AccessAlreadyActivatedError,
    AccessInvitationService,
    AccessNotFoundError,
    SmtpWelcomeEmailSender,
)

router = APIRouter(prefix="/inquilinos", tags=["inquilinos"])
property_router = APIRouter(prefix="/propiedades", tags=["inquilinos"])


def get_inquilinos_service() -> InquilinosService:
    return InquilinosService(
        SqlAlchemyInquilinosRepository(),
        AccessInvitationService(
            SqlAlchemyAccessRepository(),
            SmtpWelcomeEmailSender(),
        ),
    )


def _duplicate_dni_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "duplicate_tenant_dni",
            "field": "dni",
            "message": "Ya existe un inquilino registrado con ese DNI.",
        },
    )


def _duplicate_email_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "duplicate_tenant_email",
            "field": "email",
            "message": "Ya existe un inquilino registrado con ese email.",
        },
    )


def _property_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "code": "property_not_found",
            "field": "propiedad_id",
            "message": "La propiedad seleccionada no existe.",
        },
    )


def _property_occupied_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "property_has_active_tenant",
            "field": "propiedad_id",
            "message": "La propiedad seleccionada ya tiene un inquilino activo.",
        },
    )


@router.post("", response_model=InquilinoResponse, status_code=status.HTTP_201_CREATED)
def create_inquilino(
    payload: InquilinoCreate,
    service: InquilinosService = Depends(get_inquilinos_service),
) -> InquilinoResponse:
    try:
        return service.create(payload)
    except InquilinoDuplicateDniError as error:
        raise _duplicate_dni_error() from error
    except InquilinoDuplicateEmailError as error:
        raise _duplicate_email_error() from error
    except InquilinoPropertyNotFoundError as error:
        raise _property_not_found_error() from error
    except InquilinoPropertyOccupiedError as error:
        raise _property_occupied_error() from error


@router.get("", response_model=InquilinosPage)
def list_inquilinos(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    service: InquilinosService = Depends(get_inquilinos_service),
) -> InquilinosPage:
    return service.list(page=page, page_size=page_size, search=search)


@router.get("/{inquilino_id}", response_model=InquilinoResponse)
def get_inquilino(
    inquilino_id: UUID,
    service: InquilinosService = Depends(get_inquilinos_service),
) -> InquilinoResponse:
    try:
        return service.get_detail(inquilino_id)
    except InquilinoNotFoundError as error:
        raise HTTPException(status_code=404, detail="Inquilino no encontrado.") from error


@router.post("/{inquilino_id}/acceso/reintentar", response_model=InquilinoResponse)
def retry_inquilino_access(
    inquilino_id: UUID,
    service: InquilinosService = Depends(get_inquilinos_service),
) -> InquilinoResponse:
    try:
        return service.retry_access(inquilino_id)
    except (InquilinoNotFoundError, AccessNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No encontramos una cuenta vinculada al inquilino.",
        ) from error
    except AccessAlreadyActivatedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "access_already_activated",
                "message": "La cuenta ya fue activada y no usa la contraseña temporal.",
            },
        ) from error


@router.put("/{inquilino_id}", response_model=InquilinoResponse)
def update_inquilino(
    inquilino_id: UUID,
    payload: InquilinoUpdate,
    service: InquilinosService = Depends(get_inquilinos_service),
) -> InquilinoResponse:
    try:
        return service.update(inquilino_id, payload)
    except InquilinoNotFoundError as error:
        raise HTTPException(status_code=404, detail="Inquilino no encontrado.") from error
    except InquilinoDuplicateDniError as error:
        raise _duplicate_dni_error() from error
    except InquilinoDuplicateEmailError as error:
        raise _duplicate_email_error() from error
    except InquilinoPropertyNotFoundError as error:
        raise _property_not_found_error() from error
    except InquilinoPropertyOccupiedError as error:
        raise _property_occupied_error() from error


@router.patch("/{inquilino_id}/desasociar", response_model=InquilinoResponse)
def disassociate_inquilino(
    inquilino_id: UUID,
    service: InquilinosService = Depends(get_inquilinos_service),
) -> InquilinoResponse:
    try:
        return service.disassociate(inquilino_id)
    except InquilinoNotFoundError as error:
        raise HTTPException(status_code=404, detail="Inquilino no encontrado.") from error


@router.delete("/{inquilino_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inquilino(
    inquilino_id: UUID,
    service: InquilinosService = Depends(get_inquilinos_service),
) -> Response:
    try:
        service.delete(inquilino_id)
    except InquilinoNotFoundError as error:
        raise HTTPException(status_code=404, detail="Inquilino no encontrado.") from error
    except InquilinoHasClaimsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "tenant_has_claims",
                "message": (
                    "No se puede eliminar el inquilino porque tiene reclamos "
                    "históricos asociados. Podés desasociarlo de la propiedad."
                ),
            },
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@property_router.get(
    "/{propiedad_id}/inquilino",
    response_model=InquilinoResponse | None,
)
def get_property_tenant(
    propiedad_id: UUID,
    service: InquilinosService = Depends(get_inquilinos_service),
) -> InquilinoResponse | None:
    try:
        return service.get_by_property(propiedad_id)
    except InquilinoPropertyNotFoundError as error:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.") from error
