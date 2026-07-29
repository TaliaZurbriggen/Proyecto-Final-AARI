"""Nodos del flujo de clasificación."""

from .llm import ClaimClassifier, build_classification_prompt, get_gemini_classifier
from .schemas import ModelClassification
from .state import ClassificationState


def _invalid_model_response() -> dict[str, object]:
    """Devuelve un resultado seguro sin exponer detalles internos del proveedor."""

    return {
        "tipo_gasto": None,
        "confianza": None,
        "fundamento": None,
        "debe_escalar": True,
        "motivo_escalado": "respuesta_modelo_invalida",
        "estado_clasificacion": "escalado",
    }


def classify_claim(
    state: ClassificationState,
    classifier: ClaimClassifier | None = None,
) -> dict[str, object]:
    """Clasifica un reclamo mediante Gemini y devuelve datos validados.

    El clasificador es inyectable para que las pruebas no realicen llamadas a
    proveedores externos ni requieran una clave de API.
    """

    active_classifier = classifier or get_gemini_classifier()
    prompt = build_classification_prompt(state)

    try:
        response = active_classifier.invoke(prompt)
        classification = ModelClassification.model_validate(response)
    except Exception:
        # Los proveedores pueden lanzar errores diferentes en este límite externo.
        # Se aplica un fallback único y no se exponen detalles internos.
        return _invalid_model_response()

    return classification.model_dump()