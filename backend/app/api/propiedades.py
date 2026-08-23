"""Rutas HTTP para administrar propiedades."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.db.propiedades import SqlAlchemyPropiedadesRepository
from app.schemas.propiedades import (
    PropiedadCreate,
    PropiedadResponse,
    PropiedadesPage,
    PropiedadUpdate,
)
from app.services.propiedades_service import (
    DuplicatePropertyAddressError,
    PropiedadNotFoundError,
    PropiedadesService,
    PropertyHasActiveTenantError,
    PropertyHasClaimsError,
    PropietarioNotFoundError,
)

router = APIRouter(prefix="/propiedades", tags=["propiedades"])


def get_propiedades_service() -> PropiedadesService:
    return PropiedadesService(SqlAlchemyPropiedadesRepository())


def _owner_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "code": "owner_not_found",
            "field": "propietario_id",
            "message": "El propietario seleccionado no existe.",
        },
    )


@router.post("", response_model=PropiedadResponse, status_code=status.HTTP_201_CREATED)
def create_propiedad(
    payload: PropiedadCreate,
    service: PropiedadesService = Depends(get_propiedades_service),
) -> PropiedadResponse:
    try:
        return service.create(payload)
    except DuplicatePropertyAddressError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_address",
                "field": "direccion",
                "message": "Ya existe una propiedad registrada en esa ubicación y unidad.",
            },
        ) from error
    except PropietarioNotFoundError as error:
        raise _owner_not_found_error() from error


@router.get("", response_model=PropiedadesPage)
def list_propiedades(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    service: PropiedadesService = Depends(get_propiedades_service),
) -> PropiedadesPage:
    return service.list(page=page, page_size=page_size, search=search)


@router.get("/{propiedad_id}", response_model=PropiedadResponse)
def get_propiedad(
    propiedad_id: UUID,
    service: PropiedadesService = Depends(get_propiedades_service),
) -> PropiedadResponse:
    try:
        return service.get_detail(propiedad_id)
    except PropiedadNotFoundError as error:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.") from error


@router.put("/{propiedad_id}", response_model=PropiedadResponse)
def update_propiedad(
    propiedad_id: UUID,
    payload: PropiedadUpdate,
    service: PropiedadesService = Depends(get_propiedades_service),
) -> PropiedadResponse:
    try:
        return service.update(propiedad_id, payload)
    except PropiedadNotFoundError as error:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.") from error
    except DuplicatePropertyAddressError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_address",
                "field": "direccion",
                "message": "Ya existe una propiedad registrada en esa ubicación y unidad.",
            },
        ) from error
    except PropietarioNotFoundError as error:
        raise _owner_not_found_error() from error


@router.delete("/{propiedad_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_propiedad(
    propiedad_id: UUID,
    service: PropiedadesService = Depends(get_propiedades_service),
) -> Response:
    try:
        service.delete(propiedad_id)
    except PropiedadNotFoundError as error:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.") from error
    except PropertyHasClaimsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "property_has_claims",
                "message": (
                    "No se puede eliminar la propiedad porque tiene reclamos "
                    "históricos asociados."
                ),
            },
        ) from error
    except PropertyHasActiveTenantError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "property_has_active_tenant",
                "message": (
                    "No se puede eliminar la propiedad porque tiene un "
                    "inquilino activo."
                ),
            },
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
