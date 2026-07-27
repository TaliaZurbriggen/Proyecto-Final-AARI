"""Nodos del flujo de clasificación."""

from .state import ClassificationState


def classify_claim(state: ClassificationState) -> dict[str, str]:
    """Representa el punto de clasificación dentro del flujo.

    AARI-106 solo construye y verifica el grafo. La integración con Claude se
    incorporará en AARI-107, por lo que este nodo no toma aún decisiones de
    negocio ni realiza llamadas externas.
    """

    return {"estado_clasificacion": "pendiente_modelo"}