"""Ensayos v7 autorizados del corpus conocido, con configuración congelada."""

from __future__ import annotations

import argparse
import hashlib
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
from app.services.contract_clause_v5 import build_segmented_input  # noqa: E402
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded  # noqa: E402
from app.services.contract_clause_v7 import (  # noqa: E402
    build_v7_prompt, get_v7_model,
)
from app.services.contract_clause_v7_trial import execute_v7_trial  # noqa: E402
from app.services.contract_text_extraction import extract_contract_text  # noqa: E402


MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v7_manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True, choices=("V01", "V02", "V03", "V04"))
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    try:
        manifest = load_json(MANIFEST)
        frozen = verify_prompt_freeze(manifest, PROJECT)
        result_path = PROJECT / manifest["results_directory"] / f"resultado_{args.document.lower()}_v7.json"
        if result_path.exists():
            print("Ya existe evidencia de esta corrida; no se repite la llamada.")
            return 2
        source = verify_document(get_document(manifest, args.document), PROJECT)
        extracted = extract_contract_text(source.read_bytes())
        ocr_hash = None
        if any(page.method == "ocr" for page in extracted.pages):
            ocr = manifest["ocr"]
            if os.getenv("TESSERACT_LANGUAGE", "spa") != ocr["language"]:
                raise ValueError("El idioma OCR no coincide con el manifiesto.")
            traineddata = Path(os.environ["TESSDATA_PREFIX"]) / f"{ocr['language']}.traineddata"
            ocr_hash = file_sha256(traineddata)
            if ocr_hash != ocr["traineddata_sha256"]:
                raise ValueError("Cambió el archivo de idioma OCR congelado.")
        prepared = build_segmented_input(extracted)
        prompt = build_v7_prompt(prepared)
        metadata = {
            "document": args.document, "source_sha256": file_sha256(source),
            "prompt_version": manifest["prompt_freeze"]["prompt_version"],
            "frozen_files": frozen, "model": manifest["prompt_freeze"]["model"],
            "source_characters": sum(len(page.text) for page in extracted.pages),
            "prompt_characters": len(prompt),
            "result_path": str(result_path.relative_to(PROJECT)),
            "ocr_language": os.getenv("TESSERACT_LANGUAGE", "spa"),
            "ocr_traineddata_sha256": ocr_hash,
            "extracted_pages_sha256": hashlib.sha256(json.dumps(
                [{"page": page.page, "text": page.text} for page in extracted.pages],
                ensure_ascii=False,
            ).encode("utf-8")).hexdigest(),
            "segments": len({b.segment_index for b in prepared.blocks if b.segment_index}),
        }
    except Exception as error:
        print(f"La preparación no se completó ({type(error).__name__}); no se llamó a Gemini.")
        return 2
    if not args.run:
        print(json.dumps({**metadata, "external_calls": 0}, ensure_ascii=False, indent=2))
        return 0

    os.environ["CONTRACT_ANALYSIS_EXTERNAL_ENABLED"] = "true"
    try:
        result = execute_v7_trial(extracted, get_v7_model(metadata["model"]), result_path, metadata=metadata)
    except TrialAlreadyRecorded:
        print("Ya existe evidencia de esta corrida; no se repite la llamada.")
        return 2
    except Exception as error:
        print(f"La corrida no se completó ({type(error).__name__}); no se reintenta.")
        return 1
    print(json.dumps({
        "document": args.document, "state": result["state"], "model": metadata["model"],
        "adapter_invocations": result["adapter_invocations"],
        "model_proposals": result["model_proposals"],
        "valid_clauses": len(result["valid_clauses"]),
        "rejected_proposals": len(result["rejected_proposals"]),
        "result_path": str(result_path.relative_to(PROJECT)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
