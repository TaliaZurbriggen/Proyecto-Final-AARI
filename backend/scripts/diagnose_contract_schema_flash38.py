"""Una invocación autorizada: esquema completo y fuente sintética breve."""

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services.contract_clause_corpus import load_json, verify_prompt_freeze  # noqa: E402
from app.services.contract_clause_reference_trial import execute_reference_trial  # noqa: E402
from app.services.contract_clause_v5 import build_segmented_input  # noqa: E402
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded  # noqa: E402
from app.services.contract_clause_v7 import SourceClauseBatch, get_v7_model  # noqa: E402
from app.services.contract_clause_v9 import (  # noqa: E402
    PROMPT_VERSION, build_v9_prompt, evaluate_v9_with_model,
)
from app.services.contract_text_extraction import ContractText, PageText  # noqa: E402


MODEL = "gemini-3.8-flash"
MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v9_flash38_manifest.json"
OUTPUT = PROJECT / "docs/evaluaciones/hu30/diagnostico_flash38_esquema_completo/resultado.json"
SYNTHETIC_SOURCE = (
    "PRIMERA: El locador debe reparar las filtraciones del techo.\n"
    "SEGUNDA: El locatario debe reparar los daños que haya causado por uso indebido."
)


def synthetic_document() -> ContractText:
    return ContractText([PageText(1, SYNTHETIC_SOURCE, "synthetic", True)], True)


def prepare_metadata() -> dict:
    manifest = load_json(MANIFEST)
    if (
        manifest["prompt_freeze"]["model"] != MODEL
        or manifest["prompt_freeze"]["prompt_version"] != PROMPT_VERSION
    ):
        raise ValueError("Modelo o versión distintos de los autorizados.")
    frozen = verify_prompt_freeze(manifest, PROJECT)
    prepared = build_segmented_input(synthetic_document())
    if prepared.reconstructed_pages() != {1: SYNTHETIC_SOURCE}:
        raise ValueError("La preparación no conserva la fuente sintética.")
    prompt = build_v9_prompt(prepared)
    schema = json.dumps(SourceClauseBatch.model_json_schema(), sort_keys=True, ensure_ascii=False)
    return {
        "diagnostic_version": "flash38-full-schema-synthetic-2026-10-02",
        "document": "SYNTHETIC-01", "model": MODEL, "prompt_version": PROMPT_VERSION,
        "source_type": "invented_text", "real_contracts_sent": 0,
        "synthetic_source": SYNTHETIC_SOURCE,
        "source_sha256": hashlib.sha256(SYNTHETIC_SOURCE.encode("utf-8")).hexdigest(),
        "source_characters": len(SYNTHETIC_SOURCE), "prompt_characters": len(prompt),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "schema_name": SourceClauseBatch.__name__,
        "schema_sha256": hashlib.sha256(schema.encode("utf-8")).hexdigest(),
        "structured_output_method": "function_calling", "frozen_files": frozen,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "packages": {name: version(name) for name in ("langchain-google-genai", "google-genai")},
        "counts_towards_corpus_metrics": False,
    }


def run_probe(factory, path: Path, *, metadata: dict) -> dict:
    if path.exists():
        raise TrialAlreadyRecorded("Ya existe este diagnóstico; no se repite.")
    return execute_reference_trial(
        synthetic_document(), factory(), path, metadata=metadata,
        evaluate=evaluate_v9_with_model,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    try:
        metadata = prepare_metadata()
    except Exception as error:
        print(f"Preparación incompleta ({type(error).__name__}); no se llamó a Gemini.")
        return 2
    if not args.run:
        print(json.dumps({**metadata, "external_calls": 0}, ensure_ascii=False, indent=2))
        return 0
    if OUTPUT.exists():
        print("Ya existe evidencia; no se repite la llamada.")
        return 2
    load_dotenv(args.env_file, override=False)
    os.environ["CONTRACT_ANALYSIS_EXTERNAL_ENABLED"] = "true"
    try:
        result = run_probe(lambda: get_v7_model(MODEL), OUTPUT, metadata=metadata)
    except TrialAlreadyRecorded:
        print("Ya existe evidencia; no se repite la llamada.")
        return 2
    except Exception as error:
        print(f"Diagnóstico incompleto ({type(error).__name__}); no se reintenta.")
        return 1
    print(json.dumps({
        "state": result["state"], "adapter_invocations": result["adapter_invocations"],
        "model_proposals": result["model_proposals"],
        "valid_clauses": len(result["valid_clauses"]),
        "rejected_proposals": len(result["rejected_proposals"]),
        "source_preserved": result["source_preserved"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
