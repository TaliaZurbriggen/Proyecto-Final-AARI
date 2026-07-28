"""Nodos del flujo de clasificación."""

from .llm import ClaimClassifier, build_classification_prompt, get_gemini_classifier
from .schemas import ModelClassification
from .state import ClassificationState


def classify_claim(
    state: ClassificationState,
    classifier: ClaimClassifier | None = None,
) -> dict[str, object]:
    """Clasifica un reclamo mediante Gemini y devuelve datos validados.

    El clasificador es inyectable para que las pruebas no realicen llamadas a
    proveedores externos ni requieran una clave de API.
    """

    active_classifier = classifier or get_gemini_classifier()
    response = active_classifier.invoke(build_classification_prompt(state))
    classification = ModelClassification.model_validate(response)

    return classification.model_dump()