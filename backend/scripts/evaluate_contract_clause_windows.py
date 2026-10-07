"""Evalúa una ventana por llamada y consolida sin repetir ventanas completadas."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

from dotenv import load_dotenv


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services.contract_clause_corpus import (  # noqa: E402
    ContractClauseCorpusError, file_sha256, get_document, get_expected_controls,
    load_json, verify_document, verify_prompt_freeze,
)
from app.services.contract_clause_llm import (  # noqa: E402
    DEFAULT_MODEL, PROMPT_VERSION, get_clause_model,
)
from app.services.contract_clause_windows import (  # noqa: E402
    build_clause_windows, evaluate_clause_window, merge_clause_window_results,
    write_json_atomically,
)
from app.services.contract_text_extraction import extract_contract_text  # noqa: E402


DEFAULT_MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v4_manifest.json"
DEFAULT_CONTROLS = PROJECT / "docs/evaluaciones/hu30/controles_corpus_v2.json"


def _safe_provider_value(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_./-]{1,160}", value):
        return value
    return None


def _provider_failure_metadata(error: Exception) -> dict[str, object]:
    current: BaseException | None = error
    while current is not None:
        code = getattr(current, "code", None)
        if isinstance(code, int) and 400 <= code <= 599:
            metadata: dict[str, object] = {"provider_status": code}
            status = _safe_provider_value(getattr(current, "status", None))
            if status:
                metadata["provider_code"] = status
            details = getattr(current, "details", None)
            if isinstance(details, dict):
                response = details.get("error", details)
                if isinstance(response, dict):
                    for item in response.get("details", []):
                        if not isinstance(item, dict):
                            continue
                        if str(item.get("@type", "")).endswith("QuotaFailure"):
                            for violation in item.get("violations", []):
                                if not isinstance(violation, dict):
                                    continue
                                for source, target in (
                                    ("quotaMetric", "quota_metric"),
                                    ("quotaId", "quota_id"),
                                    ("quotaValue", "quota_value"),
                                ):
                                    value = _safe_provider_value(violation.get(source))
                                    if value:
                                        metadata[target] = value

                        elif str(item.get("@type", "")).endswith("RetryInfo"):
                            value = _safe_provider_value(item.get("retryDelay"))
                            if value:
                                metadata["retry_delay"] = value
            return metadata
        current = current.__cause__
    return {"provider_status": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True, help="ID del corpus validado.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--controls", type=Path, default=DEFAULT_CONTROLS)
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--run-window", type=int, metavar="N",
        help="Ejecuta sólo la ventana N; requiere autorización externa explícita.",
    )
    action.add_argument(
        "--assemble", action="store_true",
        help="Consolida ventanas completas sin llamar a Gemini.",
    )
    args = parser.parse_args()

    try:
        manifest = load_json(args.manifest)
        verify_prompt_freeze(manifest, PROJECT)
        document = get_document(manifest, args.document)
        path = verify_document(document, PROJECT)
        controls = get_expected_controls(load_json(args.controls), args.document)
        config = manifest.get("windowed_evaluation") or {}
        if args.document not in config.get("allowed_documents", []):
            raise ContractClauseCorpusError(
                f"El modo por ventanas no está habilitado para {args.document}."
            )
        if config.get("strategy") != "overlapping_page_windows":
            raise ContractClauseCorpusError("El manifiesto no define la estrategia por ventanas.")
        relative_dir = Path(config.get("results_directory", ""))
        results_dir = (PROJECT / relative_dir).resolve()
        if not relative_dir.parts or relative_dir.is_absolute() or not results_dir.is_relative_to(PROJECT.resolve()):
            raise ContractClauseCorpusError("El directorio de resultados está fuera del proyecto.")
        pages_per_window = config.get("pages_per_window")
        overlap_pages = config.get("overlap_pages")
        if not isinstance(pages_per_window, int) or not isinstance(overlap_pages, int):
            raise ContractClauseCorpusError("El manifiesto no define tamaños de ventana válidos.")
        extracted = extract_contract_text(path.read_bytes())
        windows = build_clause_windows(
            extracted.pages,
            pages_per_window=pages_per_window,
            overlap_pages=overlap_pages,
        )
        source_hash = file_sha256(path)
        expected_model = manifest["prompt_freeze"]["model"]
        document_dir = results_dir / args.document.lower()
    except (ContractClauseCorpusError, KeyError, ValueError) as error:
        print(f"Preflight fallido: {error}")
        return 2

    if args.run_window is None and not args.assemble:
        print(json.dumps({
            "document": args.document,
            "prompt_version": PROMPT_VERSION,
            "model": expected_model,
            "source_sha256": source_hash,
            "extraction_complete": extracted.complete,
            "expected_controls": len(controls),
            "external_calls": 0,
            "windows": [{
                "index": window.index,
                "pages": window.page_numbers,
                "characters": len(window.model_text),
                "result_exists": (document_dir / f"ventana_{window.index:02d}.json").exists(),
            } for window in windows],
        }, ensure_ascii=False, indent=2))
        return 0

    if args.run_window is not None:
        if args.run_window < 1 or args.run_window > len(windows):
            print(f"La ventana debe estar entre 1 y {len(windows)}.")
            return 2
        window = windows[args.run_window - 1]
        result_path = document_dir / f"ventana_{window.index:02d}.json"
        if result_path.exists():
            print(f"La ventana {window.index} ya tiene resultado; no se repite la llamada.")
            return 2
        load_dotenv(args.env_file, override=True)
        configured_model = os.getenv("CONTRACT_CLAUSE_MODEL", DEFAULT_MODEL)
        if configured_model != expected_model:
            print("El modelo configurado no coincide con el manifiesto congelado.")
            return 2
        os.environ["CONTRACT_ANALYSIS_EXTERNAL_ENABLED"] = "true"
        started = time.monotonic()
        try:
            result = evaluate_clause_window(
                window, get_clause_model(),
                document_id=args.document,
                source_sha256=source_hash,
                prompt_version=PROMPT_VERSION,
                model_name=configured_model,
                result_path=result_path,
            )
        except Exception as error:
            failure = {
                "document": args.document,
                "window_index": window.index,
                "pages": window.page_numbers,
                "source_sha256": source_hash,
                "prompt_version": PROMPT_VERSION,
                "model": configured_model,
                "attempted_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "error_type": type(error).__name__,
                **_provider_failure_metadata(error),
                "result_files_created": False,
                "privacy": "No se registran claves ni texto contractual.",
            }
            failure_path = document_dir / "fallos" / f"ventana_{window.index:02d}_{uuid4().hex}.json"
            write_json_atomically(failure_path, failure)
            print(json.dumps({**failure, "log": str(failure_path.relative_to(PROJECT))}, ensure_ascii=False))
            return 1
        print(json.dumps({
            "document": args.document,
            "window_index": window.index,
            "pages": window.page_numbers,
            "model_proposals": result["model_proposals"],
            "valid_clauses": len(result["valid_clauses"]),
            "rejected_proposals": len(result["rejected_proposals"]),
            "external_calls": 1,
            "result": str(result_path.relative_to(PROJECT)),
        }, ensure_ascii=False))
        return 0

    paths = [document_dir / f"ventana_{window.index:02d}.json" for window in windows]
    missing = [window.index for window, path in zip(windows, paths, strict=True) if not path.exists()]
    if missing:
        print("Faltan ventanas para consolidar: " + ", ".join(map(str, missing)))
        return 2
    try:
        result = merge_clause_window_results(
            windows, [load_json(path) for path in paths],
            document_id=args.document,
            source_sha256=source_hash,
            prompt_version=PROMPT_VERSION,
            model_name=expected_model,
        )
    except ContractClauseCorpusError as error:
        print(f"No se pudieron consolidar las ventanas: {error}")
        return 2
    result["source_windows"] = [
        {"path": str(path.relative_to(PROJECT)), "sha256": file_sha256(path)}
        for path in paths
    ]
    output = document_dir / f"resultado_{args.document.lower()}_{PROMPT_VERSION}_ventanas.json"
    review_output = document_dir / f"revision_{args.document.lower()}_{PROMPT_VERSION}_ventanas.json"
    if output.exists():
        if load_json(output) != result:
            print("Ya existe una consolidación diferente; no se sobrescribe.")
            return 2
    else:
        write_json_atomically(output, result)
    if not review_output.exists():
        write_json_atomically(review_output, {
            "document": args.document,
            "result": str(output.relative_to(PROJECT)),
            "controls": [
                {"id": item["id"], "state": "pendiente", "matched_proposals": [], "notes": ""}
                for item in controls
            ],
            "accepted_hallucinations": None,
            "reviewed_by": None,
            "reviewed_at": None,
        })
    print(json.dumps({
        "document": args.document,
        "windows_completed": len(windows),
        "model_proposals": result["model_proposals"],
        "valid_clauses": len(result["valid_clauses"]),
        "duplicate_proposals_removed": result["duplicate_proposals_removed"],
        "external_calls": result["external_calls"],
        "result": str(output.relative_to(PROJECT)),
        "review_template": str(review_output.relative_to(PROJECT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
