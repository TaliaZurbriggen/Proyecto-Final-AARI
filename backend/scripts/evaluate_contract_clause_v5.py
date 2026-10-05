"""Una corrida V04/v5 autorizada, con checkpoint previo y sin reintentos manuales."""

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
    ContractClauseCorpusError,
    file_sha256,
    get_document,
    load_json,
    verify_document,
    verify_prompt_freeze,
)
from app.services.contract_clause_llm import get_clause_model  # noqa: E402
from app.services.contract_clause_segments import VALIDATOR_VERSION  # noqa: E402
from app.services.contract_clause_v5 import (  # noqa: E402
    PROMPT_PATH,
    PROMPT_VERSION,
    SegmentedInputError,
    build_segmented_input,
    build_v5_prompt,
)
from app.services.contract_clause_v5_trial import (  # noqa: E402
    TrialAlreadyRecorded,
    execute_v5_trial,
)
from app.services.contract_text_extraction import (  # noqa: E402
    ContractTextError,
    extract_contract_text,
)


EXPECTED_PROMPT_SHA256 = "2412cf4b50128b8ec307d05be07c22639acadf2683eeefb91e2777b6c8c4a4ba"
MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v4_manifest.json"
RESULTS_BY_MODEL = {
    "gemini-3.5-flash-lite": PROJECT / "docs/evaluaciones/hu30/resultados_v5/resultado_v04_v5.json",
    "gemini-3.5-flash": PROJECT / "docs/evaluaciones/hu30/resultados_v5/resultado_v04_v5_flash.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Ejecuta la llamada autorizada una vez.")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    parser.add_argument("--model", choices=RESULTS_BY_MODEL,
                        default="gemini-3.5-flash-lite")
    args = parser.parse_args()
    result_path = RESULTS_BY_MODEL[args.model]

    if result_path.exists():
        print(f"Ya existe evidencia de V04/v5 con {args.model}. No se repite la llamada.")
        return 2
    try:
        manifest = load_json(MANIFEST)
        verify_prompt_freeze(manifest, PROJECT)
        source = verify_document(get_document(manifest, "V04"), PROJECT)
        prompt_sha = file_sha256(PROMPT_PATH)
        if prompt_sha != EXPECTED_PROMPT_SHA256:
            raise ContractClauseCorpusError("El prompt v5 cambió desde su aprobación.")
        extracted = extract_contract_text(source.read_bytes())
        prepared = build_segmented_input(extracted)
        prompt = build_v5_prompt(prepared)
    except (ContractClauseCorpusError, ContractTextError, SegmentedInputError) as error:
        print(str(error))
        return 2

    metadata = {
        "document": "V04",
        "source_sha256": file_sha256(source),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": prompt_sha,
        "input_builder_sha256": file_sha256(BACKEND / "app/services/contract_clause_v5.py"),
        "verifier_version": VALIDATOR_VERSION,
        "verifier_sha256": file_sha256(BACKEND / "app/services/contract_clause_segments.py"),
        "model": args.model,
        "source_characters": sum(len(page.text) for page in extracted.pages),
        "prompt_characters": len(prompt),
        "result_path": str(result_path.relative_to(PROJECT)),
    }
    if not args.run:
        print(json.dumps({**metadata, "external_calls": 0}, ensure_ascii=False, indent=2))
        print("No se llamó a Gemini. Para hacerlo se requiere --run y autorización previa.")
        return 0

    load_dotenv(args.env_file, override=False)
    os.environ["CONTRACT_ANALYSIS_EXTERNAL_ENABLED"] = "true"
    os.environ["CONTRACT_CLAUSE_MODEL"] = args.model
    try:
        model = get_clause_model()
        result = execute_v5_trial(extracted, model, result_path, metadata=metadata)
    except TrialAlreadyRecorded:
        print("Ya existe evidencia de V04/v5. No se repite la llamada.")
        return 2
    except Exception as error:
        # No imprimir el mensaje del proveedor: puede contener texto o credenciales.
        print(f"La corrida no se completó ({type(error).__name__}). No se reintenta.")
        if result_path.exists():
            print(f"Revisá el estado seguro en {result_path.relative_to(PROJECT)}.")
        else:
            print("La llamada no llegó a registrarse; no se creó un checkpoint.")
        return 1

    print(json.dumps({
        "document": "V04",
        "state": result["state"],
        "adapter_invocations": result["adapter_invocations"],
        "model_proposals": result["model_proposals"],
        "valid_clauses": len(result["valid_clauses"]),
        "rejected_proposals": len(result["rejected_proposals"]),
        "result_path": str(result_path.relative_to(PROJECT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
