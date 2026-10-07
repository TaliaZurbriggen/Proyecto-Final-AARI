"""Una corrida autorizada de V04/v6 con Flash-Lite, sin repetir resultados."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services.contract_clause_corpus import (  # noqa: E402
    file_sha256, get_document, load_json, verify_document, verify_prompt_freeze,
)
from app.services.contract_clause_llm import get_clause_model  # noqa: E402
from app.services.contract_clause_v5 import build_segmented_input  # noqa: E402
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded  # noqa: E402
from app.services.contract_clause_v6 import (  # noqa: E402
    PROMPT_PATH, PROMPT_VERSION, build_v6_prompt,
)
from app.services.contract_clause_v6_trial import execute_v6_trial  # noqa: E402
from app.services.contract_text_extraction import extract_contract_text  # noqa: E402


EXPECTED_PROMPT_SHA256 = "76a11d51a39be29f0429377b573bd5fc4e3afd4cafcfefc3a237239b47c96314"
MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v4_manifest.json"
RESULT = PROJECT / "docs/evaluaciones/hu30/resultados_v6/resultado_v04_v6.json"
MODEL = "gemini-3.5-flash-lite"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    if RESULT.exists():
        print("Ya existe evidencia de V04/v6; no se repite la llamada.")
        return 2
    try:
        manifest = load_json(MANIFEST)
        verify_prompt_freeze(manifest, PROJECT)
        source = verify_document(get_document(manifest, "V04"), PROJECT)
        prompt_sha = file_sha256(PROMPT_PATH)
        if prompt_sha != EXPECTED_PROMPT_SHA256:
            raise ValueError("Cambió el prompt v6 congelado.")
        extracted = extract_contract_text(source.read_bytes())
        prepared = build_segmented_input(extracted)
        prompt = build_v6_prompt(prepared)
        metadata = {
            "document": "V04", "source_sha256": file_sha256(source),
            "prompt_version": PROMPT_VERSION, "prompt_sha256": prompt_sha,
            "frozen_files": [
                {"path": path, "sha256": file_sha256(PROJECT / path)}
                for path in (
                    "backend/app/services/contract_clause_v5.py",
                    "backend/app/services/contract_clause_v6.py",
                    "backend/app/services/contract_clause_segments.py",
                    "backend/app/services/contract_clause_evidence.py",
                    "backend/app/services/contract_clause_llm.py",
                )
            ],
            "model": MODEL,
            "source_characters": sum(len(page.text) for page in extracted.pages),
            "prompt_characters": len(prompt),
            "result_path": str(RESULT.relative_to(PROJECT)),
        }
    except Exception as error:
        print(f"La preparación no se completó ({type(error).__name__}); no se llamó a Gemini.")
        return 2
    if not args.run:
        print(json.dumps({**metadata, "external_calls": 0}, ensure_ascii=False, indent=2))
        return 0

    load_dotenv(args.env_file, override=False)
    os.environ["CONTRACT_ANALYSIS_EXTERNAL_ENABLED"] = "true"
    os.environ["CONTRACT_CLAUSE_MODEL"] = MODEL
    try:
        result = execute_v6_trial(extracted, get_clause_model(), RESULT, metadata=metadata)
    except TrialAlreadyRecorded:
        print("Ya existe evidencia de V04/v6; no se repite la llamada.")
        return 2
    except Exception as error:
        print(f"La corrida no se completó ({type(error).__name__}); no se reintenta.")
        return 1
    print(json.dumps({
        "state": result["state"], "model": MODEL,
        "adapter_invocations": result["adapter_invocations"],
        "model_proposals": result["model_proposals"],
        "valid_clauses": len(result["valid_clauses"]),
        "rejected_proposals": len(result["rejected_proposals"]),
        "result_path": str(RESULT.relative_to(PROJECT)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
