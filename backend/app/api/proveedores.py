"""Rutas HTTP para administrar proveedores y sus especialidades."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.proveedores import SqlAlchemyProveedoresRepository
from app.schemas.propiedades import ProvinciaArgentina
from app.schemas.proveedores import (
    EspecialidadResponse,
    ProveedorCreate,
    ProveedorEstadoUpdate,
    ProveedorResponse,
    ProveedoresPage,
    ProveedorUpdate,
)
from app.services.proveedores_service import (
    EspecialidadNotFoundError,
    ProveedorDuplicatePhoneError,
    ProveedorNotFoundError,
    ProveedoresService,
)

router = APIRouter(prefix="/proveedores", tags=["proveedores"])
specialties_router = APIRouter(prefix="/especialidades", tags=["proveedores"])


def get_proveedores_service() -> ProveedoresService:
    return ProveedoresService(SqlAlchemyProveedoresRepository())


def _duplicate_phone_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "duplicate_provider_phone",
            "field": "telefono",
            "message": "Ya existe un proveedor registrado con ese teléfono.",
        },
    )


def _specialty_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "code": "specialty_not_found",
            "field": "especialidad_ids",
            "message": "Una de las especialidades seleccionadas ya no existe.",
        },
    )


@specialties_router.get("", response_model=list[EspecialidadResponse])
def list_especialidades(
    service: ProveedoresService = Depends(get_proveedores_service),
) -> list[EspecialidadResponse]:
    return service.list_specialties()


@router.post("", response_model=ProveedorResponse, status_code=status.HTTP_201_CREATED)
def create_proveedor(
    payload: ProveedorCreate,
    service: ProveedoresService = Depends(get_proveedores_service),
) -> ProveedorResponse:
    try:
        return service.create(payload)
    except ProveedorDuplicatePhoneError as error:
        raise _duplicate_phone_error() from error
    except EspecialidadNotFoundError as error:
        raise _specialty_not_found_error() from error


@router.get("", response_model=ProveedoresPage)
def list_proveedores(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    especialidad_id: UUID | None = None,
    provincia: ProvinciaArgentina | None = None,
    localidad: str | None = Query(default=None, max_length=100),
    barrio: str | None = Query(default=None, max_length=100),
    activo: bool | None = None,
    service: ProveedoresService = Depends(get_proveedores_service),
) -> ProveedoresPage:
    if barrio and barrio.strip() and (
        provincia is None or not localidad or not localidad.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "incomplete_neighborhood_filter",
                "field": "barrio",
                "message": (
                    "Seleccioná provincia y localidad para filtrar por barrio."
                ),
            },
        )

    return service.list(
        page=page,
        page_size=page_size,
        search=search,
        especialidad_id=especialidad_id,
        provincia=provincia.value if provincia else None,
        localidad=localidad,
        barrio=barrio,
        activo=activo,
    )


@router.get("/{proveedor_id}", response_model=ProveedorResponse)
def get_proveedor(
    proveedor_id: UUID,
    service: ProveedoresService = Depends(get_proveedores_service),
) -> ProveedorResponse:
    try:
        return service.get_detail(proveedor_id)
    except ProveedorNotFoundError as error:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.") from error


@router.put("/{proveedor_id}", response_model=ProveedorResponse)
def update_proveedor(
    proveedor_id: UUID,
    payload: ProveedorUpdate,
    service: ProveedoresService = Depends(get_proveedores_service),
) -> ProveedorResponse:
    try:
        return service.update(proveedor_id, payload)
    except ProveedorNotFoundError as error:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.") from error
    except ProveedorDuplicatePhoneError as error:
        raise _duplicate_phone_error() from error
    except EspecialidadNotFoundError as error:
        raise _specialty_not_found_error() from error


@router.patch("/{proveedor_id}/estado", response_model=ProveedorResponse)
def update_proveedor_estado(
    proveedor_id: UUID,
    payload: ProveedorEstadoUpdate,
    service: ProveedoresService = Depends(get_proveedores_service),
) -> ProveedorResponse:
    try:
        return service.update_status(proveedor_id, payload)
    except ProveedorNotFoundError as error:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.") from error
