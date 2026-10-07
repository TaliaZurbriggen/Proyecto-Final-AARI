"""Una llamada optativa de HU30 sobre la copia anonimizada verificada."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.services.contract_clause_evidence import validate_and_anchor_evidence
from app.services.contract_clause_llm import (
    DEFAULT_MODEL, EXTRACTOR_VERSION, PROMPT_VERSION,
    build_clause_prompt, get_clause_model, parse_batch,
)
from app.services.contract_text_extraction import extract_contract_text, minimize_personal_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("No se llamó a Gemini. Requiere autorización y el indicador --run.")
        return 2
    pdf_path = PROJECT / "output" / "pdf" / "hu30_contrato_anonimizado.pdf"
    verification_path = pdf_path.with_suffix(".verificacion.json")
    output = (
        PROJECT / "docs" / "evaluaciones" / "hu30"
        / f"resultado_gemini_ejemplo_01_{PROMPT_VERSION}.json"
    )
    if output.exists():
        print("Ya existe una evaluación real. No se repite la llamada automáticamente.")
        return 2
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if verification.get("visual_review") != "passed_all_13_pages":
        print("La copia anonimizada no tiene revisión visual aprobada.")
        return 2
    if verification.get("residual_identifier_matches") != 0:
        print("La copia anonimizada tiene identificadores residuales detectados.")
        return 2
    pdf_bytes = pdf_path.read_bytes()
    source_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if source_sha256 != verification.get("output_sha256"):
        print("El hash de la copia anonimizada no coincide con su verificación.")
        return 2
    load_dotenv(args.env_file, override=True)
    os.environ["CONTRACT_ANALYSIS_EXTERNAL_ENABLED"] = "true"
    model_name = os.getenv("CONTRACT_CLAUSE_MODEL", DEFAULT_MODEL)
    extracted = extract_contract_text(pdf_bytes)
    batch = parse_batch(get_clause_model().invoke(
        build_clause_prompt(minimize_personal_data(extracted.model_text))
    ))
    clauses, rejected, incidents = validate_and_anchor_evidence(
        batch, {page.page: page.text for page in extracted.pages}
    )
    output.write_text(json.dumps({
        "fuente": "hu30_contrato_anonimizado.pdf",
        "fuente_sha256": source_sha256,
        "ejecutado_en": datetime.now(timezone.utc).isoformat(),
        "modelo": model_name,
        "prompt_version": PROMPT_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "llamadas_externas": 1,
        "paginas": len(extracted.pages),
        "extraccion_local_completa": extracted.complete,
        "clausulas_validas": [clause.model_dump(mode="json") for clause in clauses],
        "propuestas_rechazadas": [
            item.model_dump(mode="json") for item in rejected
        ],
        "incidencias_evidencia": incidents,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "paginas": len(extracted.pages), "propuestas_modelo": len(batch.clausulas),
        "clausulas_validas": len(clauses), "propuestas_rechazadas": len(rejected),
        "incidencias_evidencia": len(incidents),
        "resultado": str(output.relative_to(PROJECT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
