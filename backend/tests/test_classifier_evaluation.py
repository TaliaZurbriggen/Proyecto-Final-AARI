"""Pruebas deterministas de las reglas de evaluacion de AARI-111."""

import pytest

from app.agents.classification.evaluation import evaluate_case, expected_category, summarize_results


def classified_result(category: str) -> dict[str, object]:
    return {
        "estado_clasificacion": "clasificado",
        "tipo_gasto": category,
        "motivo_escalado": None,
        "confianza": 0.9,
    }


def escalated_result(reason: str) -> dict[str, object]:
    return {
        "estado_clasificacion": "escalado",
        "tipo_gasto": None,
        "motivo_escalado": reason,
        "confianza": 0.6,
    }


def test_classified_case_requires_the_expected_category_without_escalation():
    case = {
        "id": "caso-clasificado",
        "categoria_esperada": "ordinario",
        "escalar_esperado": False,
    }

    evaluation = evaluate_case(case, classified_result("ordinario"))

    assert expected_category(case) == "ordinario"
    assert evaluation["correcto"] is True
    assert evaluation["tipo_error"] is None


def test_expected_escalation_requires_an_accepted_reason():
    case = {
        "id": "caso-escalado",
        "categoria_esperada": None,
        "escalar_esperado": True,
        "motivo_escalado_esperado": "riesgo_seguridad",
    }

    correct = evaluate_case(case, escalated_result("riesgo_seguridad"))
    incorrect = evaluate_case(case, escalated_result("confianza_insuficiente"))

    assert correct["correcto"] is True
    assert incorrect["tipo_error"] == "motivo_escalado_incorrecto"


def test_expected_escalation_accepts_alternative_reason_declared_by_the_dataset():
    case = {
        "id": "caso-multiple",
        "categoria_esperada": None,
        "escalar_esperado": True,
        "motivo_escalado_esperado": "riesgo_seguridad",
        "motivos_aceptables": ["riesgo_seguridad", "multiples_rubros"],
    }

    evaluation = evaluate_case(case, escalated_result("multiples_rubros"))

    assert evaluation["correcto"] is True


def test_evaluation_distinguishes_missing_and_unnecessary_escalation():
    escalation_case = {
        "id": "caso-debe-escalar",
        "categoria_esperada": None,
        "escalar_esperado": True,
        "motivo_escalado_esperado": "causa_no_identificable",
    }
    category_case = {
        "id": "caso-no-debe-escalar",
        "categoria_esperada": "expensa",
        "escalar_esperado": False,
    }

    missing = evaluate_case(escalation_case, classified_result("ordinario"))
    unnecessary = evaluate_case(category_case, escalated_result("confianza_insuficiente"))

    assert missing["tipo_error"] == "falta_escalado"
    assert unnecessary["tipo_error"] == "escalado_indebido"


def test_summary_reports_global_and_macro_accuracy_by_category():
    results = [
        {
            "categoria_esperada": "ordinario",
            "correcto": True,
            "tipo_error": None,
            "confianza": 0.9,
        },
        {
            "categoria_esperada": "ordinario",
            "correcto": False,
            "tipo_error": "categoria_incorrecta",
            "confianza": 0.8,
        },
        {
            "categoria_esperada": "escalar",
            "correcto": True,
            "tipo_error": None,
            "confianza": None,
        },
    ]

    summary = summarize_results(results)

    assert summary["total_casos"] == 3
    assert summary["aciertos"] == 2
    assert summary["exactitud_global"] == 2 / 3
    assert summary["por_categoria"]["ordinario"]["exactitud"] == 0.5
    assert summary["por_categoria"]["escalar"]["exactitud"] == 1.0
    assert summary["exactitud_macro"] == 0.75
    assert summary["errores_por_tipo"] == {"categoria_incorrecta": 1}
    assert summary["confianza_promedio"] == pytest.approx(0.85)
    assert summary["respuestas_modelo_invalidas"] == 0
