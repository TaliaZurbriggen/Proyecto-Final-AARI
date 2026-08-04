"""Reglas deterministas para evaluar resultados del clasificador."""

from collections import Counter, defaultdict
from statistics import fmean
from typing import Any


CATEGORIES = ("ordinario", "extraordinario", "expensa", "escalar")


def expected_category(case: dict[str, Any]) -> str:
    """Devuelve la categoria evaluable esperada para un caso del conjunto."""

    if case["escalar_esperado"]:
        return "escalar"
    return str(case["categoria_esperada"])


def evaluate_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Compara una salida del grafo con un caso etiquetado."""

    expected = expected_category(case)
    actual_escalated = result.get("estado_clasificacion") == "escalado"
    actual = "escalar" if actual_escalated else result.get("tipo_gasto")
    actual_reason = result.get("motivo_escalado")

    error_type: str | None = None
    if expected == "escalar":
        if not actual_escalated:
            error_type = "falta_escalado"
        else:
            accepted_reasons = case.get("motivos_aceptables") or [
                case["motivo_escalado_esperado"]
            ]
            if actual_reason not in accepted_reasons:
                error_type = "motivo_escalado_incorrecto"
    elif actual_escalated:
        error_type = "escalado_indebido"
    elif actual != expected:
        error_type = "categoria_incorrecta"

    return {
        "id": case["id"],
        "categoria_esperada": expected,
        "categoria_obtenida": actual,
        "motivo_escalado_obtenido": actual_reason,
        "confianza": result.get("confianza"),
        "respuesta_modelo_invalida": actual_reason == "respuesta_modelo_invalida",
        "correcto": error_type is None,
        "tipo_error": error_type,
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcula exactitud global, por categoria y el promedio macro."""

    if not results:
        raise ValueError("No se pueden resumir resultados vacios.")

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_category[str(result["categoria_esperada"])].append(result)

    metrics_by_category: dict[str, dict[str, Any]] = {}
    for category in CATEGORIES:
        category_results = by_category.get(category, [])
        total = len(category_results)
        correct = sum(bool(item["correcto"]) for item in category_results)
        metrics_by_category[category] = {
            "total": total,
            "aciertos": correct,
            "exactitud": correct / total if total else None,
        }

    total = len(results)
    correct = sum(bool(item["correcto"]) for item in results)
    available_accuracies = [
        metric["exactitud"]
        for metric in metrics_by_category.values()
        if metric["exactitud"] is not None
    ]
    confidences = [
        float(item["confianza"])
        for item in results
        if isinstance(item.get("confianza"), (int, float))
        and not isinstance(item.get("confianza"), bool)
    ]

    invalid_responses = sum(
        bool(item.get("respuesta_modelo_invalida")) for item in results
    )

    return {
        "total_casos": total,
        "aciertos": correct,
        "exactitud_global": correct / total,
        "exactitud_macro": fmean(available_accuracies),
        "por_categoria": metrics_by_category,
        "errores_por_tipo": dict(
            sorted(
                Counter(
                    str(item["tipo_error"])
                    for item in results
                    if item["tipo_error"] is not None
                ).items()
            )
        ),
        "confianza_promedio": fmean(confidences) if confidences else None,
        "respuestas_modelo_invalidas": invalid_responses,
    }
