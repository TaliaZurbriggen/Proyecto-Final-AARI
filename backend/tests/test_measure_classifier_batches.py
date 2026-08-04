"""Pruebas locales del mecanismo de lotes y checkpoints de AARI-111."""

import importlib.util
import json
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "measure_classifier.py"
SPEC = importlib.util.spec_from_file_location("measure_classifier", SCRIPT_PATH)
assert SPEC and SPEC.loader
measure_classifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measure_classifier)


def completed_result(case_id: str) -> dict[str, object]:
    return {
        "id": case_id,
        "categoria_esperada": "ordinario",
        "categoria_obtenida": "ordinario",
        "motivo_escalado_obtenido": None,
        "confianza": 0.9,
        "respuesta_modelo_invalida": False,
        "correcto": True,
        "tipo_error": None,
    }


def test_manifest_covers_the_61_cases_once_and_respects_daily_limit():
    _, cases = measure_classifier.load_cases(measure_classifier.DEFAULT_DATASET)
    batches = measure_classifier.load_batches(measure_classifier.DEFAULT_BATCHES, cases)

    ids = [case["id"] for batch in batches.values() for case in batch]

    assert [len(batch) for batch in batches.values()] == [20, 20, 20, 1]
    assert len(ids) == 61
    assert len(set(ids)) == 61
    assert set(ids) == {case["id"] for case in cases}


def test_first_batch_has_the_agreed_representative_distribution():
    _, cases = measure_classifier.load_cases(measure_classifier.DEFAULT_DATASET)
    batches = measure_classifier.load_batches(measure_classifier.DEFAULT_BATCHES, cases)

    first_batch = batches["lote-1"]
    distribution = {"ordinario": 0, "extraordinario": 0, "expensa": 0, "escalar": 0}
    for case in first_batch:
        category = "escalar" if case["escalar_esperado"] else case["categoria_esperada"]
        distribution[category] += 1

    assert distribution == {"ordinario": 6, "extraordinario": 6, "expensa": 3, "escalar": 5}


def test_checkpoint_round_trip_and_resume_validation(tmp_path):
    _, cases = measure_classifier.load_cases(measure_classifier.DEFAULT_DATASET)
    batches = measure_classifier.load_batches(measure_classifier.DEFAULT_BATCHES, cases)
    batch = batches["lote-1"]
    checkpoint = tmp_path / "lote-1.json"
    report = measure_classifier.build_report(
        {"version": "1.1", "casos": cases, "estado": "borrador"},
        "lote-1",
        batch,
        [completed_result("caso-01")],
    )

    measure_classifier.write_checkpoint(checkpoint, report)
    recovered = measure_classifier.load_checkpoint(checkpoint, "lote-1", batch)

    assert recovered == [completed_result("caso-01")]
    assert report["estado_corrida"] == "en_progreso"
    assert len(report["casos_pendientes"]) == 19


def test_checkpoint_rejects_another_batch_or_duplicate_case(tmp_path):
    _, cases = measure_classifier.load_cases(measure_classifier.DEFAULT_DATASET)
    batches = measure_classifier.load_batches(measure_classifier.DEFAULT_BATCHES, cases)
    checkpoint = tmp_path / "invalid.json"
    checkpoint.write_text(
        json.dumps(
            {
                "lote": "lote-1",
                "resultados_por_caso": [completed_result("caso-01"), completed_result("caso-01")],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="repetidos"):
        measure_classifier.load_checkpoint(checkpoint, "lote-1", batches["lote-1"])

    with pytest.raises(ValueError, match="otro lote"):
        measure_classifier.load_checkpoint(checkpoint, "lote-2", batches["lote-2"])


def test_completed_batch_does_not_invoke_gemini_again(tmp_path, monkeypatch):
    dataset, cases = measure_classifier.load_cases(measure_classifier.DEFAULT_DATASET)
    batches = measure_classifier.load_batches(measure_classifier.DEFAULT_BATCHES, cases)
    batch = batches["lote-4"]
    checkpoint = tmp_path / "lote-4.json"
    completed = [
        {
            **completed_result("caso-50"),
            "categoria_esperada": "escalar",
            "categoria_obtenida": "escalar",
        }
    ]
    measure_classifier.write_checkpoint(
        checkpoint,
        measure_classifier.build_report(dataset, "lote-4", batch, completed),
    )

    def must_not_call_gemini():
        pytest.fail("No debe invocar Gemini para un lote ya completado.")

    monkeypatch.setattr(measure_classifier, "get_gemini_classifier", must_not_call_gemini)
    report = measure_classifier.run_measurement(dataset, "lote-4", batch, checkpoint)

    assert report["estado_corrida"] == "completa"
    assert report["resultados_por_caso"] == completed
