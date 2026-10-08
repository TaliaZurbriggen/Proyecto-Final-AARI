"""Endpoint de lectura exclusivo del administrador."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import require_admin
from app.db.admin_home import SqlAlchemyAdminHomeRepository
from app.schemas.admin_home import AdminHomeSummary


router = APIRouter(
    prefix="/admin", tags=["inicio administrativo"],
    dependencies=[Depends(require_admin)],
)


def get_admin_home_repository() -> SqlAlchemyAdminHomeRepository:
    return SqlAlchemyAdminHomeRepository()


@router.get("/resumen", response_model=AdminHomeSummary)
def get_admin_summary(
    repository: SqlAlchemyAdminHomeRepository = Depends(get_admin_home_repository),
) -> AdminHomeSummary:
    try:
        return repository.get_summary()
    except SQLAlchemyError:
        # No exponer SQL, parámetros de conexión ni datos de la base.
        raise HTTPException(503, detail={
            "code": "summary_unavailable",
            "message": "No pudimos obtener el resumen. Podés volver a intentar.",
        }) from None
