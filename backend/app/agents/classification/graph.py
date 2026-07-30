"""Definici?n del grafo de clasificaci?n de reclamos."""

from langgraph.graph import END, START, StateGraph

from .llm import ClaimClassifier
from .nodes import classify_claim
from .state import ClassificationState


def build_classification_graph(
    classifier: ClaimClassifier | None = None,
    confidence_threshold: float | None = None,
):
    """Construye Inicio -> clasificar reclamo -> Fin."""

    def classification_node(state: ClassificationState) -> dict[str, object]:
        return classify_claim(state, classifier, confidence_threshold)

    builder = StateGraph(ClassificationState)
    builder.add_node("clasificar_reclamo", classification_node)
    builder.add_edge(START, "clasificar_reclamo")
    builder.add_edge("clasificar_reclamo", END)
    return builder.compile()
