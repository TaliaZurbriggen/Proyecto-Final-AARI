"""Definición del grafo mínimo de clasificación de reclamos."""

from langgraph.graph import END, START, StateGraph

from .nodes import classify_claim
from .state import ClassificationState


def build_classification_graph():
    """Construye el flujo Inicio -> clasificar reclamo -> Fin."""

    builder = StateGraph(ClassificationState)
    builder.add_node("clasificar_reclamo", classify_claim)
    builder.add_edge(START, "clasificar_reclamo")
    builder.add_edge("clasificar_reclamo", END)

    return builder.compile()