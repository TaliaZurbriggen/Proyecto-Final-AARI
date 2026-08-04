"""Ejecuta una medicion recuperable del clasificador sobre casos sinteticos.

Este script llama a Gemini y no debe ejecutarse dentro de pytest. La opcion
--validar-conjunto permite revisar datos y lotes sin consumir cuota.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.classification.evaluation import evaluate_case, summarize_results
from app.agents.classification.graph import build_classification_graph
from app.agents.classification.llm import get_gemini_classifier
from app.agents.classification.resources import get_confidence_threshold


DEFAULT_DATASET = BACKEND_DIR / "tests" / "data" / "conjunto_prueba_61_casos.json"
DEFAULT_BATCHES = BACKEND_DIR / "tests" / "data" / "aari111_lotes.json"
DEFAULT_RESULTS_DIR = BACKEND_DIR.parent / "docs" / "evaluaciones" / "aari111"
DEFAULT_URGENCY = "media"


def load_cases(dataset_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Carga y valida los campos minimos requeridos por la medicion."""

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset.get("casos")
    if not isinstance(cases, list) or not cases:
        raise ValueError("El conjunto de prueba debe contener una lista no vacia de casos.")

    required_fields = {
        "id",
        "descripcion",
        "rubro_declarado",
        "clausulas_contrato",
        "escalar_esperado",
    }
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not required_fields <= set(case):
            raise ValueError("Se encontro un caso con campos requeridos incompletos.")
        case_id = str(case["id"])
        if case_id in ids:
            raise ValueError(f"El identificador '{case_id}' esta repetido.")
        ids.add(case_id)
        if case["escalar_esperado"]:
            if not case.get("motivo_escalado_esperado"):
                raise ValueError(f"El caso '{case_id}' debe declarar motivo de escalado.")
        elif case.get("categoria_esperada") not in {
            "ordinario",
            "extraordinario",
            "expensa",
        }:
            raise ValueError(f"El caso '{case_id}' debe declarar una categoria esperada valida.")

    return dataset, cases


def load_batches(
    batches_path: Path, cases: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Carga lotes y verifica que cubran el conjunto una sola vez."""

    raw_batches = json.loads(batches_path.read_text(encoding="utf-8-sig")).get("lotes")
    if not isinstance(raw_batches, dict) or not raw_batches:
        raise ValueError("El manifiesto debe contener lotes no vacios.")

    cases_by_id = {str(case["id"]): case for case in cases}
    used_ids: set[str] = set()
    batches: dict[str, list[dict[str, Any]]] = {}
    for batch_name, batch_ids in raw_batches.items():
        if not isinstance(batch_name, str) or not isinstance(batch_ids, list) or not batch_ids:
            raise ValueError("Cada lote debe tener nombre y al menos un caso.")
        if len(batch_ids) > 20:
            raise ValueError(f"El lote '{batch_name}' supera el maximo diario de 20 casos.")

        selected_cases: list[dict[str, Any]] = []
        for case_id in batch_ids:
            case_id = str(case_id)
            if case_id not in cases_by_id:
                raise ValueError(f"El lote '{batch_name}' referencia '{case_id}' inexistente.")
            if case_id in used_ids:
                raise ValueError(f"El caso '{case_id}' esta repetido entre lotes.")
            used_ids.add(case_id)
            selected_cases.append(cases_by_id[case_id])
        batches[batch_name] = selected_cases

    expected_ids = set(cases_by_id)
    if used_ids != expected_ids:
        missing = ", ".join(sorted(expected_ids - used_ids))
        extra = ", ".join(sorted(used_ids - expected_ids))
        detail = "; ".join(filter(None, [f"faltan: {missing}" if missing else "", f"sobran: {extra}" if extra else ""]))
        raise ValueError(f"Los lotes no cubren exactamente el conjunto ({detail}).")

    return batches


def checkpoint_path_for(batch_name: str) -> Path:
    """Devuelve el archivo versionable de evidencia para un lote."""

    return DEFAULT_RESULTS_DIR / f"{batch_name}.json"


def load_checkpoint(
    checkpoint_path: Path, batch_name: str, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Recupera resultados previos y rechaza checkpoints incompatibles."""

    if not checkpoint_path.exists():
        return []

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("lote") != batch_name:
        raise ValueError("El checkpoint corresponde a otro lote.")
    results = checkpoint.get("resultados_por_caso")
    if not isinstance(results, list):
        raise ValueError("El checkpoint no contiene resultados validos.")

    valid_ids = {str(case["id"]) for case in cases}
    result_ids = [str(item.get("id")) for item in results if isinstance(item, dict)]
    if len(result_ids) != len(results) or len(set(result_ids)) != len(result_ids):
        raise ValueError("El checkpoint contiene identificadores invalidos o repetidos.")
    if not set(result_ids) <= valid_ids:
        raise ValueError("El checkpoint contiene casos ajenos al lote.")
    return results


def build_report(
    dataset: dict[str, Any],
    batch_name: str,
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construye evidencia reproducible sin incluir secretos."""

    ordered_results = sorted(results, key=lambda item: str(item["id"]))
    metrics = summarize_results(ordered_results) if ordered_results else None
    pending_ids = sorted(
        str(case["id"]) for case in cases if str(case["id"]) not in {str(item["id"]) for item in ordered_results}
    )

    return {
        "version_formato": "1.0",
        "estado_corrida": "completa" if not pending_ids else "en_progreso",
        "ejecutado_en_utc": datetime.now(UTC).isoformat(),
        "modelo": os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
        "umbral_confianza": get_confidence_threshold(),
        "urgencia_fija": DEFAULT_URGENCY,
        "conjunto_prueba": {
            "version": dataset.get("version"),
            "cantidad_casos": len(dataset["casos"]),
            "estado": dataset.get("estado"),
        },
        "lote": batch_name,
        "cantidad_casos_lote": len(cases),
        "casos_pendientes": pending_ids,
        "metricas": metrics,
        "resultados_por_caso": ordered_results,
    }


def write_checkpoint(checkpoint_path: Path, report: dict[str, Any]) -> None:
    """Persiste de forma atomica para conservar los casos ya completados."""

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = checkpoint_path.with_suffix(f"{checkpoint_path.suffix}.tmp")
    temporary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(checkpoint_path)


def run_measurement(
    dataset: dict[str, Any],
    batch_name: str,
    cases: list[dict[str, Any]],
    checkpoint_path: Path,
) -> dict[str, Any]:
    """Ejecuta solo los pendientes y guarda un checkpoint tras cada respuesta."""

    results = load_checkpoint(checkpoint_path, batch_name, cases)
    completed_ids = {str(item["id"]) for item in results}
    pending_cases = [case for case in cases if str(case["id"]) not in completed_ids]
    if not pending_cases:
        return build_report(dataset, batch_name, cases, results)

    classifier = get_gemini_classifier()
    graph = build_classification_graph(classifier)
    for case in pending_cases:
        graph_result = graph.invoke(
            {
                "descripcion": case["descripcion"],
                "urgencia": DEFAULT_URGENCY,
                "rubro_declarado": case["rubro_declarado"],
                "clausulas_contrato": case["clausulas_contrato"],
            }
        )
        results.append(evaluate_case(case, dict(graph_result)))
        write_checkpoint(
            checkpoint_path,
            build_report(dataset, batch_name, cases, results),
        )

    return build_report(dataset, batch_name, cases, results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--lotes", type=Path, default=DEFAULT_BATCHES)
    parser.add_argument("--lote", help="Nombre del lote a ejecutar (por ejemplo, lote-1).")
    parser.add_argument(
        "--validar-conjunto",
        action="store_true",
        help="Valida el conjunto y todos los lotes sin llamar a Gemini.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="Archivo JSON donde recuperar y guardar el resultado del lote.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset, cases = load_cases(args.dataset)
    batches = load_batches(args.lotes, cases)
    print(f"Conjunto valido: {len(cases)} casos, version {dataset.get('version')}.")
    print("Lotes validos: " + ", ".join(f"{name} ({len(batch)})" for name, batch in batches.items()))
    if args.validar_conjunto:
        return 0
    if not args.lote:
        raise SystemExit("Indicá --lote para evitar ejecutar los 61 casos por accidente.")
    if args.lote not in batches:
        raise SystemExit(f"Lote desconocido: {args.lote}.")

    checkpoint_path = args.checkpoint or checkpoint_path_for(args.lote)
    report = run_measurement(dataset, args.lote, batches[args.lote], checkpoint_path)
    metrics = report["metricas"]
    if metrics:
        print(
            "Lote finalizado: "
            f"{metrics['aciertos']}/{metrics['total_casos']} "
            f"({metrics['exactitud_global']:.2%})."
        )
    print(f"Checkpoint: {checkpoint_path}")
    if report["estado_corrida"] != "completa":
        print(f"Pendientes en este lote: {len(report['casos_pendientes'])}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

