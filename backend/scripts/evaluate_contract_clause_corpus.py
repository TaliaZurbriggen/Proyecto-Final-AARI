"""Prepara o ejecuta una evaluación controlada del corpus v2 de HU30."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services.contract_clause_corpus import (
    ContractClauseCorpusError,
    calculate_review_metrics,
    file_sha256,
    get_document,
    get_expected_controls,
    load_json,
    verify_document,
    verify_prompt_freeze,
)
from app.services.contract_clause_llm import (
    DEFAULT_MODEL,
    EXTRACTOR_VERSION,
    PROMPT_VERSION,
    build_clause_prompt,
    get_clause_model,
    parse_batch,
)
from app.services.contract_clause_evidence import validate_and_anchor_evidence
from app.services.contract_text_extraction import extract_contract_text, minimize_personal_data


DEFAULT_MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v2_manifest.json"
DEFAULT_CONTROLS = PROJECT / "docs/evaluaciones/hu30/controles_corpus_v2.json"
RESULTS_DIR = PROJECT / "docs/evaluaciones/hu30/resultados_corpus_v2"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True, help="ID V01-V04 del manifiesto.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--controls", type=Path, default=DEFAULT_CONTROLS)
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check-extraction",
        action="store_true",
        help="Ejecuta sólo la lectura local/OCR y no llama a Gemini.",
    )
    action.add_argument(
        "--run",
        action="store_true",
        help="Realiza una única llamada externa. Requiere autorización explícita previa.",
    )
    action.add_argument(
        "--score-review",
        type=Path,
        help="Calcula métricas de una revisión humana completa, sin llamar a Gemini.",
    )
    args = parser.parse_args()
    require_validated = args.run or args.score_review is not None

    try:
        manifest = load_json(args.manifest)
        controls_file = load_json(args.controls)
        frozen = verify_prompt_freeze(manifest, PROJECT)
        document = get_document(manifest, args.document)
        path = verify_document(
            document,
            PROJECT,
            require_validated_expectations=require_validated,
        )
        controls = get_expected_controls(
            controls_file,
            args.document,
            require_validated=require_validated,
        )
        results_dir = PROJECT / manifest.get(
            "results_directory",
            str(RESULTS_DIR.relative_to(PROJECT)),
        )
    except ContractClauseCorpusError as error:
        print(str(error))
        return 2

    preflight = {
        "document": args.document,
        "source": str(path.relative_to(PROJECT)),
        "source_sha256": file_sha256(path),
        "prompt_version": manifest["prompt_freeze"]["prompt_version"],
        "model": manifest["prompt_freeze"]["model"],
        "frozen_files": frozen,
        "expectations_state": document.get("expectations_state"),
        "expected_controls": len(controls),
        "external_calls": 0,
    }
    if args.score_review is not None:
        try:
            review = load_json(args.score_review)
            metrics = calculate_review_metrics(
                controls,
                review,
                manifest["thresholds"],
            )
        except ContractClauseCorpusError as error:
            print(str(error))
            return 2
        print(json.dumps({**preflight, "metrics": metrics}, ensure_ascii=False, indent=2))
        return 0
    if not args.run:
        if args.check_extraction:
            load_dotenv(args.env_file, override=True)
            extracted = extract_contract_text(path.read_bytes())
            preflight["local_extraction"] = {
                "pages": len(extracted.pages),
                "complete": extracted.complete,
                "characters": sum(len(page.text) for page in extracted.pages),
                "methods": [page.method for page in extracted.pages],
            }
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        print("No se llamó a Gemini. Para ejecutar hace falta autorización y --run.")
        return 0

    output = results_dir / f"resultado_{args.document.lower()}_{PROMPT_VERSION}.json"
    review_output = results_dir / f"revision_{args.document.lower()}_{PROMPT_VERSION}.json"
    if output.exists() or review_output.exists():
        print("Ya existe evidencia para este documento; no se repite la llamada automáticamente.")
        return 2

    load_dotenv(args.env_file, override=True)
    os.environ["CONTRACT_ANALYSIS_EXTERNAL_ENABLED"] = "true"
    pdf_bytes = path.read_bytes()
    extracted = extract_contract_text(pdf_bytes)
    batch = parse_batch(
        get_clause_model().invoke(build_clause_prompt(minimize_personal_data(extracted.model_text)))
    )
    clauses, rejected, incidents = validate_and_anchor_evidence(
        batch, {page.page: page.text for page in extracted.pages}
    )
    results_dir.mkdir(parents=True, exist_ok=True)
    result = {
        **preflight,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "model": os.getenv("CONTRACT_CLAUSE_MODEL", DEFAULT_MODEL),
        "prompt_version": PROMPT_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "pages": len(extracted.pages),
        "local_extraction_complete": extracted.complete,
        "external_calls": 1,
        "model_proposals": len(batch.clausulas),
        "valid_clauses": [item.model_dump(mode="json") for item in clauses],
        "rejected_proposals": [item.model_dump(mode="json") for item in rejected],
        "evidence_incidents": incidents,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    review_output.write_text(json.dumps({
        "document": args.document,
        "result": str(output.relative_to(PROJECT)),
        "controls": [
            {"id": item["id"], "state": "pendiente", "matched_proposals": [], "notes": ""}
            for item in controls
        ],
        "accepted_hallucinations": None,
        "reviewed_by": None,
        "reviewed_at": None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "document": args.document,
        "pages": len(extracted.pages),
        "model_proposals": len(batch.clausulas),
        "valid_clauses": len(clauses),
        "rejected_proposals": len(rejected),
        "external_calls": 1,
        "result": str(output.relative_to(PROJECT)),
        "review_template": str(review_output.relative_to(PROJECT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
