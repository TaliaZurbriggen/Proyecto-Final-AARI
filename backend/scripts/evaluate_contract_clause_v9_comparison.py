"""Compara v9/V04 con Flash, sin alterar el ensayo congelado Flash-Lite."""

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
from app.services.contract_clause_reference_trial import execute_reference_trial  # noqa: E402
from app.services.contract_clause_v5 import build_segmented_input  # noqa: E402
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded  # noqa: E402
from app.services.contract_clause_v7 import get_v7_model  # noqa: E402
from app.services.contract_clause_v9 import (  # noqa: E402
    PROMPT_VERSION, build_v9_prompt, evaluate_v9_with_model,
)
from app.services.contract_text_extraction import extract_contract_text  # noqa: E402


MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v9_flash_manifest.json"
BASELINE_MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v9_manifest.json"
BASELINE_RESULT = PROJECT / "docs/evaluaciones/hu30/resultados_v9/resultado_v04_v9.json"
COMPARISON_MODEL = "gemini-3.5-flash"


def validate_comparison_manifest(manifest: dict, baseline: dict) -> None:
    """Sólo se admite cambiar el modelo y el registro del ensayo, no sus reglas."""
    if baseline["prompt_freeze"]["model"] != "gemini-3.5-flash-lite":
        raise ValueError("El modelo de referencia no coincide.")
    if manifest["prompt_freeze"]["model"] != COMPARISON_MODEL:
        raise ValueError("El modelo comparado no es el autorizado.")
    for key in ("thresholds", "documents", "ocr"):
        if manifest[key] != baseline[key]:
            raise ValueError("La comparación cambió documentos, controles u OCR.")
    if manifest["prompt_freeze"]["prompt_version"] != baseline["prompt_freeze"]["prompt_version"]:
        raise ValueError("La comparación cambió la versión del prompt.")
    actual = {item["path"]: item["sha256"] for item in manifest["prompt_freeze"]["files"]}
    for item in baseline["prompt_freeze"]["files"]:
        if actual.get(item["path"]) != item["sha256"]:
            raise ValueError("La comparación cambió un archivo congelado.")
    if manifest["results_directory"] == baseline["results_directory"]:
        raise ValueError("La comparación debe tener resultados separados.")


def validate_same_input(metadata: dict, baseline: dict) -> None:
    """Impide consumir la llamada si la entrada ya no es la del ensayo Lite."""
    if (
        baseline.get("state") != "completed"
        or baseline.get("document") != "V04"
        or baseline.get("model") != "gemini-3.5-flash-lite"
        or baseline.get("source_preserved") is not True
    ):
        raise ValueError("Falta una referencia Flash-Lite completa y verificable.")
    for key in (
        "document", "prompt_version", "source_sha256", "source_characters",
        "prompt_characters", "extracted_pages_sha256",
        "ocr_language", "ocr_traineddata_sha256",
    ):
        if metadata.get(key) != baseline.get(key):
            raise ValueError("La entrada no coincide con el ensayo Flash-Lite.")
    actual = {item["path"]: item["sha256"] for item in metadata["frozen_files"]}
    for item in baseline["frozen_files"]:
        if actual.get(item["path"]) != item["sha256"]:
            raise ValueError("Cambió el pipeline del ensayo Flash-Lite.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", choices=("V04",), required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    try:
        manifest = load_json(MANIFEST)
        validate_comparison_manifest(manifest, load_json(BASELINE_MANIFEST))
        frozen = verify_prompt_freeze(manifest, PROJECT)
        if manifest["prompt_freeze"]["prompt_version"] != PROMPT_VERSION:
            raise ValueError("La versión no coincide con el manifiesto.")
        result_path = PROJECT / manifest["results_directory"] / f"resultado_{args.document.lower()}_v9_flash.json"
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
            ocr_hash = file_sha256(Path(os.environ["TESSDATA_PREFIX"]) / f"{ocr['language']}.traineddata")
            if ocr_hash != ocr["traineddata_sha256"]:
                raise ValueError("Cambió el archivo de idioma OCR congelado.")
        prepared = build_segmented_input(extracted)
        prompt = build_v9_prompt(prepared)
        metadata = {
            "document": args.document, "source_sha256": file_sha256(source),
            "prompt_version": PROMPT_VERSION, "frozen_files": frozen,
            "model": manifest["prompt_freeze"]["model"],
            "source_characters": sum(len(p.text) for p in extracted.pages),
            "prompt_characters": len(prompt), "result_path": str(result_path.relative_to(PROJECT)),
            "ocr_language": os.getenv("TESSERACT_LANGUAGE", "spa"), "ocr_traineddata_sha256": ocr_hash,
            "extracted_pages_sha256": hashlib.sha256(json.dumps(
                [{"page": p.page, "text": p.text} for p in extracted.pages], ensure_ascii=False,
            ).encode("utf-8")).hexdigest(),
        }
        baseline_result = load_json(BASELINE_RESULT)
        validate_same_input(metadata, baseline_result)
        metadata["comparison_baseline"] = str(BASELINE_RESULT.relative_to(PROJECT))
        metadata["comparison_baseline_sha256"] = file_sha256(BASELINE_RESULT)
    except Exception as error:
        print(f"La preparación no se completó ({type(error).__name__}); no se llamó a Gemini.")
        return 2
    if not args.run:
        print(json.dumps({**metadata, "external_calls": 0}, ensure_ascii=False, indent=2))
        return 0
    os.environ["CONTRACT_ANALYSIS_EXTERNAL_ENABLED"] = "true"
    try:
        result = execute_reference_trial(
            extracted, get_v7_model(metadata["model"]), result_path,
            metadata=metadata, evaluate=evaluate_v9_with_model,
        )
    except TrialAlreadyRecorded:
        print("Ya existe evidencia de esta corrida; no se repite la llamada.")
        return 2
    except Exception as error:
        print(f"La corrida no se completó ({type(error).__name__}); no se reintenta.")
        return 1
    print(json.dumps({
        "document": args.document, "state": result["state"],
        "adapter_invocations": result["adapter_invocations"], "model_proposals": result["model_proposals"],
        "valid_clauses": len(result["valid_clauses"]), "rejected_proposals": len(result["rejected_proposals"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
