"""Definición del grafo mínimo de clasificación de reclamos."""

from langgraph.graph import END, START, StateGraph

from .llm import ClaimClassifier
from .nodes import classify_claim
from .state import ClassificationState


def build_classification_graph(classifier: ClaimClassifier | None = None):
    """Construye el flujo Inicio -> clasificar reclamo -> Fin.

    ``classifier`` permite inyectar un doble de prueba o, en producción,
    utilizar Gemini a través de la configuración local.
    """

    def classification_node(state: ClassificationState) -> dict[str, object]:
        return classify_claim(state, classifier)

    builder = StateGraph(ClassificationState)
    builder.add_node("clasificar_reclamo", classification_node)
    builder.add_edge(START, "clasificar_reclamo")
    builder.add_edge("clasificar_reclamo", END)

    return builder.compile()