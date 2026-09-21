"""Definici?n del grafo de clasificaci?n de reclamos."""

from langgraph.graph import END, START, StateGraph

from .llm import ClaimClassifier
from .nodes import classify_claim, determine_responsible_actor
from .state import ClassificationState


def build_classification_graph(
    classifier: ClaimClassifier | None = None,
    confidence_threshold: float | None = None,
):
    """Construye clasificación -> intención de notificación, sin efectos externos."""

    def classification_node(state: ClassificationState) -> dict[str, object]:
        return classify_claim(state, classifier, confidence_threshold)

    builder = StateGraph(ClassificationState)
    builder.add_node("clasificar_reclamo", classification_node)
    builder.add_node("determinar_actor_responsable", determine_responsible_actor)
    builder.add_edge(START, "clasificar_reclamo")
    builder.add_edge("clasificar_reclamo", "determinar_actor_responsable")
    builder.add_edge("determinar_actor_responsable", END)
    return builder.compile()
