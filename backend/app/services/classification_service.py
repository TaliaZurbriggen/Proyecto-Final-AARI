"""Orquestación entre el reclamo persistido y el grafo de clasificación."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.schemas.reclamos import AgentClassificationResult, ClaimClassificationResponse


class ClaimNotFoundError(Exception):
    """Señala que no existe el reclamo solicitado."""


@dataclass(frozen=True)
class ClaimForClassification:
    """Datos existentes que necesita el grafo para clasificar."""

    reclamo_id: UUID
    descripcion: str
    urgencia: str
    rubro_declarado: str | None
    clausulas_contrato: list[dict[str, object]]


class ClaimsRepository(Protocol):
    """Puerto de persistencia para que el servicio pueda probarse sin Supabase."""

    def get_for_classification(self, reclamo_id: UUID) -> ClaimForClassification | None:
        """Obtiene un reclamo existente y su contexto de clasificación."""

    def persist_classification(
        self,
        reclamo_id: UUID,
        result: AgentClassificationResult,
    ) -> ClaimClassificationResponse:
        """Guarda el resultado y registra el origen agente en una transacción."""


class ClassificationGraph(Protocol):
    """Contrato mínimo de LangGraph usado por este servicio."""

    def invoke(self, state: dict[str, object]) -> dict[str, object]:
        """Ejecuta el flujo de clasificación."""


class ClassificationService:
    """Clasifica un reclamo existente y persiste el resultado obtenido."""

    def __init__(self, repository: ClaimsRepository, graph: ClassificationGraph) -> None:
        self.repository = repository
        self.graph = graph

    def classify(self, reclamo_id: UUID) -> ClaimClassificationResponse:
        claim = self.repository.get_for_classification(reclamo_id)
        if claim is None:
            raise ClaimNotFoundError

        graph_result = self.graph.invoke(
            {
                "reclamo_id": str(claim.reclamo_id),
                "descripcion": claim.descripcion,
                "urgencia": claim.urgencia,
                "rubro_declarado": claim.rubro_declarado,
                "clausulas_contrato": claim.clausulas_contrato,
            }
        )
        result = AgentClassificationResult.model_validate(graph_result)
        return self.repository.persist_classification(reclamo_id, result)
