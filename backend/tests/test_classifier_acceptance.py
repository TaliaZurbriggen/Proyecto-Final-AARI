"""Pruebas de aceptación reproducibles sobre la evidencia real de AARI-112."""

from collections import Counter
import json
from pathlib import Path

import pytest

from app.agents.classification.evaluation import evaluate_case, summarize_results


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "backend" / "tests" / "data" / "conjunto_prueba_80_casos.json"
CHECKPOINT_PATH = (
    REPO_ROOT / "docs" / "evaluaciones" / "aari112" / "resultados_v5_parciales.json"
)
REPORT_PATH = REPO_ROOT / "docs" / "evaluaciones" / "aari112" / "resultados_v5.json"


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_evidence() -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    dataset = load_json(DATASET_PATH)
    checkpoints = load_json(CHECKPOINT_PATH)
    assert isinstance(dataset, dict)
    assert isinstance(checkpoints, dict)
    cases = dataset["casos"]
    assert isinstance(cases, list)
    return cases, checkpoints


def graph_result(checkpoint: dict[str, object]) -> dict[str, object]:
    result = dict(checkpoint["obtenido"])
    result["estado_clasificacion"] = (
        "escalado" if result["debe_escalar"] else "clasificado"
    )
    return result


def test_dataset_and_checkpoint_cover_the_same_80_unique_cases():
    cases, checkpoints = load_evidence()
    case_ids = [str(case["id"]) for case in cases]

    assert len(cases) == 80
    assert len(case_ids) == len(set(case_ids))
    assert set(case_ids) == set(checkpoints)
    assert Counter(case["conjunto_origen"] for case in cases) == {
        "baseline_61": 61,
        "holdout_19": 19,
    }


def test_checkpoint_expected_values_match_the_validated_dataset():
    cases, checkpoints = load_evidence()

    for case in cases:
        expected = checkpoints[str(case["id"])]["esperado"]
        assert expected["categoria"] == case["categoria_esperada"]
        assert expected["escalar"] == case["escalar_esperado"]
        assert expected["motivo_esperado"] == case.get("motivo_escalado_esperado")
        assert expected["motivos_aceptables"] == case.get("motivos_aceptables")


def test_real_v5_evidence_reproduces_the_hu9_acceptance_result():
    cases, checkpoints = load_evidence()
    evaluated = [
        evaluate_case(case, graph_result(checkpoints[str(case["id"])]))
        for case in cases
    ]
    summary = summarize_results(evaluated)

    assert summary["total_casos"] == 80
    assert summary["aciertos"] == 70
    assert summary["exactitud_global"] == pytest.approx(0.875)
    assert summary["exactitud_macro"] == pytest.approx(0.8808, abs=0.0001)
    assert summary["respuestas_modelo_invalidas"] == 0
    assert summary["exactitud_global"] >= 0.85

    expected_categories = {
        "ordinario": (23, 21),
        "extraordinario": (22, 21),
        "expensa": (12, 11),
        "escalar": (23, 17),
    }
    for category, (total, correct) in expected_categories.items():
        assert summary["por_categoria"][category]["total"] == total
        assert summary["por_categoria"][category]["aciertos"] == correct

    for origin, expected_total, expected_correct in (
        ("baseline_61", 61, 53),
        ("holdout_19", 19, 17),
    ):
        origin_cases = [
            case for case in cases if case["conjunto_origen"] == origin
        ]
        origin_summary = summarize_results(
            [
                evaluate_case(case, graph_result(checkpoints[str(case["id"])]))
                for case in origin_cases
            ]
        )
        assert origin_summary["total_casos"] == expected_total
        assert origin_summary["aciertos"] == expected_correct


def test_versioned_report_matches_the_replayed_evidence():
    report = load_json(REPORT_PATH)

    assert report["prompt_version"] == "v5"
    assert report["v5"]["correctos"] == 70
    assert report["v5"]["total"] == 80
    assert report["v5"]["precision"] == pytest.approx(0.875)
    assert report["v5"]["respuestas_invalidas"] == 0
    assert report["por_origen"]["baseline_61"]["correctos"] == 53
    assert report["por_origen"]["holdout_19"]["correctos"] == 17
    assert report["criterio_aceptacion_hu9"] == {
        "umbral": 0.85,
        "universo": "80 casos validados con Oikos",
        "cumple": True,
    }
