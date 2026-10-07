"""Reprocesa localmente los descartes v2 con el anclaje conservador de v3."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.schemas.clausulas_contrato import ExtractedClauseBatch, RejectedClause
from app.services.contract_clause_corpus import get_document, load_json, verify_document
from app.services.contract_clause_evidence import validate_and_anchor_evidence
from app.services.contract_text_extraction import extract_contract_text


MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v2_manifest.json"
RESULTS = PROJECT / "docs/evaluaciones/hu30/resultados_corpus_v2"
OUTPUT = PROJECT / "docs/evaluaciones/hu30/reanclaje_v3_sobre_descartes_v2.json"


def main() -> int:
    manifest = load_json(MANIFEST)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Propuestas rechazadas de V01-V04 con prompt v2",
        "external_calls": 0,
        "documents": [],
    }
    recovered_total = 0
    rejected_total = 0
    for document_id in ("V01", "V02", "V03", "V04"):
        document = get_document(manifest, document_id)
        pdf_path = verify_document(document, PROJECT)
        result_path = RESULTS / f"resultado_{document_id.lower()}_v2.json"
        result = load_json(result_path)
        extracted = extract_contract_text(pdf_path.read_bytes())
        pages = {page.page: page.text for page in extracted.pages}
        recovered = []
        still_rejected = []
        for raw in result.get("rejected_proposals") or []:
            previous = RejectedClause.model_validate(raw)
            batch = ExtractedClauseBatch(clausulas=[previous.propuesta])
            valid, rejected, _ = validate_and_anchor_evidence(batch, pages)
            if valid:
                recovered.append({
                    "original_ordinal": previous.ordinal,
                    "clause": valid[0].model_dump(mode="json"),
                })
            else:
                still_rejected.append({
                    "original_ordinal": previous.ordinal,
                    "reason": rejected[0].motivo,
                    "proposal": previous.propuesta.model_dump(mode="json"),
                })
        recovered_total += len(recovered)
        rejected_total += len(still_rejected)
        report["documents"].append({
            "document": document_id,
            "v2_rejected": len(result.get("rejected_proposals") or []),
            "recovered_by_v3_anchor": len(recovered),
            "still_rejected": len(still_rejected),
            "recovered": recovered,
            "remaining": still_rejected,
        })

    report["summary"] = {
        "v2_rejected": recovered_total + rejected_total,
        "recovered_by_v3_anchor": recovered_total,
        "still_rejected": rejected_total,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report["summary"], "external_calls": 0,
                      "output": str(OUTPUT.relative_to(PROJECT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
