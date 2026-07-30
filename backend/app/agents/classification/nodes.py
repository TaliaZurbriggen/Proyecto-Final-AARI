"""Nodos del flujo de clasificaci?n."""

from .llm import ClaimClassifier, build_classification_prompt, get_gemini_classifier
from .resources import get_confidence_threshold, validate_confidence_threshold
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


def _apply_confidence_threshold(
    classification: ModelClassification,
    confidence_threshold: float,
) -> dict[str, object]:
    """Escala clasificaciones de baja confianza sin perder su fundamento."""

    result = classification.model_dump()
    if classification.debe_escalar:
        return {**result, "estado_clasificacion": "escalado"}
    if classification.confianza < confidence_threshold:
        return {
            **result,
            "tipo_gasto": None,
            "debe_escalar": True,
            "motivo_escalado": "confianza_insuficiente",
            "estado_clasificacion": "escalado",
        }
    return {**result, "estado_clasificacion": "clasificado"}


def classify_claim(
    state: ClassificationState,
    classifier: ClaimClassifier | None = None,
    confidence_threshold: float | None = None,
) -> dict[str, object]:
    """Clasifica o escala un reclamo mediante Gemini y salida validada."""

    try:
        active_classifier = classifier or get_gemini_classifier()
        threshold = (
            validate_confidence_threshold(confidence_threshold)
            if confidence_threshold is not None
            else get_confidence_threshold()
        )
        prompt = build_classification_prompt(state, threshold)
        response = active_classifier.invoke(prompt)
        classification = ModelClassification.model_validate(response)
    except Exception:
        # Los proveedores pueden lanzar errores diferentes en este l?mite externo.
        # Se aplica un fallback ?nico y no se exponen detalles internos.
        return _invalid_model_response()

    return _apply_confidence_threshold(classification, threshold)
