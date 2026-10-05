"""Intervención humana sin consultar nuevamente al clasificador externo."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.schemas.auth import AuthenticatedUser
from app.schemas.escalados import ManualClassificationRequest, ManualClassificationResponse
from app.schemas.reclamos import AgentClassificationResult
from app.services.classification_service import ClassificationGraph


class EscalatedClaimNotFoundError(Exception):
    pass


class ManualClassificationConflictError(Exception):
    pass


class ManualClassificationPermissionError(Exception):
    pass


def ensure_manual_classification_allowed(*, estado, tipo_gasto, has_responsible, origen):
    if (
        estado not in {"Escalado", "Clasificación pendiente"}
        or tipo_gasto is not None
        or has_responsible
        or origen in {"operador", "administrador"}
    ):
        raise ManualClassificationConflictError(
            "El reclamo ya fue clasificado o avanzó de etapa. Actualizá la pantalla."
        )


@dataclass(frozen=True)
class ManualDecisionContext:
    user_id: UUID
    role: str
    expected_updated_at: datetime


@dataclass(frozen=True)
class PersistedManualClassification:
    response: ManualClassificationResponse
    notification_id: UUID | None


class ManualClassificationRepository(Protocol):
    def resolve_manual(self, claim_id: UUID, result: AgentClassificationResult,
                       decision: ManualDecisionContext) -> PersistedManualClassification: ...


class EscalatedClaimsService:
    def __init__(self, repository: ManualClassificationRepository, graph: ClassificationGraph):
        self.repository = repository
        self.graph = graph

    def resolve(self, claim_id: UUID, request: ManualClassificationRequest,
                user: AuthenticatedUser) -> PersistedManualClassification:
        if user.rol not in {"operador", "administrador"} or user.primer_ingreso:
            raise ManualClassificationPermissionError
        # Este grafo tiene una entrada exclusivamente humana: nunca contiene el LLM.
        state = self.graph.invoke({
            "tipo_gasto": request.tipo_gasto,
            "confianza": None,
            "fundamento": request.fundamento,
            "debe_escalar": False,
            "motivo_escalado": None,
            "estado_clasificacion": "clasificado",
        })
        result = AgentClassificationResult.model_validate(state)
        if (result.tipo_gasto != request.tipo_gasto or result.confianza is not None
                or result.fundamento != request.fundamento):
            raise RuntimeError("El flujo manual alteró la decisión recibida.")
        return self.repository.resolve_manual(claim_id, result, ManualDecisionContext(
            user_id=user.id, role=user.rol, expected_updated_at=request.expected_updated_at,
        ))
