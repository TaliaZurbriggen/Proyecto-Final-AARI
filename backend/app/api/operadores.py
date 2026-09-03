"""Gestión administrativa de operadores."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import require_admin
from app.db.operadores import SqlAlchemyOperadoresRepository
from app.schemas.operadores import (
    OperadorCreate, OperadorDesactivadoResponse, OperadorResponse, OperadoresPage,
)
from app.services.access_service import SmtpWelcomeEmailSender
from app.services.operadores_service import (
    DuplicateOperadorEmailError, OperadorAccessConflictError,
    OperadorNotFoundError, OperadoresService,
)

router = APIRouter(prefix="/usuarios/operadores", tags=["operadores"],
                   dependencies=[Depends(require_admin)])


def get_operadores_service() -> OperadoresService:
    return OperadoresService(SqlAlchemyOperadoresRepository(), SmtpWelcomeEmailSender())


def _unavailable() -> HTTPException:
    # SQLAlchemy puede incluir parámetros sensibles en su excepción original.
    return HTTPException(503, detail="No pudimos completar la operación. Revisá la conexión y las migraciones del backend.")


@router.get("", response_model=OperadoresPage)
def list_operadores(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=120),
    service: OperadoresService = Depends(get_operadores_service),
) -> OperadoresPage:
    try:
        return service.list(page=page, page_size=page_size, search=search)
    except SQLAlchemyError:
        raise _unavailable() from None


@router.post("", response_model=OperadorResponse, status_code=201)
def create_operador(payload: OperadorCreate, service: OperadoresService = Depends(get_operadores_service)):
    try:
        return service.create(payload)
    except DuplicateOperadorEmailError:
        raise HTTPException(409, detail={"code": "duplicate_field", "field": "email",
                            "message": "Ese email ya está registrado en el sistema."}) from None
    except SQLAlchemyError:
        raise _unavailable() from None


@router.patch("/{operador_id}/desactivar", response_model=OperadorDesactivadoResponse)
def deactivate_operador(operador_id: UUID, service: OperadoresService = Depends(get_operadores_service)):
    try:
        return service.deactivate(operador_id)
    except OperadorNotFoundError:
        raise HTTPException(404, detail="Operador no encontrado.") from None
    except SQLAlchemyError:
        raise _unavailable() from None


@router.post("/{operador_id}/acceso/reintentar", response_model=OperadorResponse)
def retry_operador_access(operador_id: UUID, service: OperadoresService = Depends(get_operadores_service)):
    try:
        return service.retry_access(operador_id)
    except OperadorNotFoundError:
        raise HTTPException(404, detail="Operador no encontrado.") from None
    except OperadorAccessConflictError as error:
        raise HTTPException(409, detail={"code": "operator_access_conflict", "message": str(error)}) from None
    except SQLAlchemyError:
        raise _unavailable() from None
