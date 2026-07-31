"""Rutas HTTP para los reclamos existentes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.classification.graph import build_classification_graph
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.schemas.reclamos import ClaimClassificationResponse
from app.services.classification_service import ClaimNotFoundError, ClassificationService

router = APIRouter(prefix="/reclamos", tags=["reclamos"])


def get_classification_service() -> ClassificationService:
    """Construye las dependencias de producción de la clasificación."""

    return ClassificationService(SqlAlchemyClaimsRepository(), build_classification_graph())


@router.post(
    "/{reclamo_id}/clasificar",
    response_model=ClaimClassificationResponse,
    status_code=status.HTTP_200_OK,
)
def classify_claim(
    reclamo_id: UUID,
    service: ClassificationService = Depends(get_classification_service),
) -> ClaimClassificationResponse:
    """Clasifica un reclamo existente y persiste clasificación o escalado."""

    try:
        return service.classify(reclamo_id)
    except ClaimNotFoundError as error:
        raise HTTPException(status_code=404, detail="Reclamo no encontrado.") from error
