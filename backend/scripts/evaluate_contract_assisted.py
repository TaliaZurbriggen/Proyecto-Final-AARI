"""Verificación local V01–V04 o una llamada explícita a Gemini para el V04 público."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services import contract_clause_assisted as assisted  # noqa: E402
from app.services.contract_clause_corpus import get_document, load_json, verify_document  # noqa: E402
from app.services.contract_clause_service import ContractClauseService  # noqa: E402
from app.services.contract_clause_windows import write_json_atomically  # noqa: E402
from app.services.contract_text_extraction import extract_contract_text  # noqa: E402

RESULT = PROJECT / "docs/evaluaciones/hu30/asistida_2026-10-05.json"


def local_corpus():
    manifest = load_json(PROJECT / "docs/evaluaciones/hu30/corpus_v2_manifest.json")
    checks = []
    for name in ("V01", "V02", "V03", "V04"):
        document = get_document(manifest, name)
        path = verify_document(document, PROJECT)
        extracted = extract_contract_text(path.read_bytes())
        clauses = assisted.literal_clauses(extracted)
        # Comparar por página sin espacios: el esquema separa y normaliza extremos,
        # pero no debe perder palabras ni recuperar texto desde otra página.
        preserved = True
        for page in extracted.pages:
            parts = [e.texto for clause in clauses for e in clause.evidencias if e.pagina == page.page]
            expected = "".join(page.text.split())
            actual = "".join("".join(parts).split())
            preserved = preserved and expected == actual
        checks.append({"document": name, "complete_reading": extracted.complete,
            "pages": len(extracted.pages), "methods": [page.method for page in extracted.pages],
            "literal_records": len(clauses), "all_page_text_preserved": preserved,
            "external_calls": 0})
    return checks


def run_public_v04(output=RESULT):
    manifest = load_json(PROJECT / "docs/evaluaciones/hu30/corpus_v2_manifest.json")
    document = get_document(manifest, "V04")
    path = verify_document(document, PROJECT)
    record = {"document": "V04", "source_url": document["source_url"], "source_sha256": document["sha256"],
              "model": assisted.DEFAULT_MODEL, "prompt_version": assisted.PROMPT_VERSION,
              "prompt_sha256": hashlib.sha256(assisted.PROMPT_PATH.read_bytes()).hexdigest(),
              "state": "started", "maximum_http_requests": 1, "started_at": datetime.now(timezone.utc).isoformat(),
              "semantic_review": "pending", "private_contracts_sent": 0, "supabase_writes": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as checkpoint:
        json.dump(record, checkpoint, ensure_ascii=False, indent=2)
        checkpoint.flush()
        os.fsync(checkpoint.fileno())
    # La habilitación es sólo del proceso autorizado, no cambia el .env ni producción.
    model = assisted.JsonClauseModel(os.environ["GEMINI_API_KEY"], assisted.DEFAULT_MODEL)

    class Repository:
        def claim_due(self, **_):
            return [SimpleNamespace(id=uuid4(), contract_id=uuid4(), document_id=uuid4(),
                storage_path="public/V04.pdf", attempt_number=1, mode="ia", execution_id=uuid4(),
                model_name=assisted.DEFAULT_MODEL, prompt_version=assisted.PROMPT_VERSION)]
        def complete(self, _id, **data):
            record.update(state="completed", clauses=[item.model_dump(mode="json") for item in data["clauses"]],
                origins=data["origins"], source_rejected=data["source_rejected"],
                complete_reading=data["complete"], pages=data["pages"], incidents=data["incidents"])
            return True
        def fail(self, _id, _attempt, message, **_):
            record.update(state="failed", safe_error=message)
            return True

    service = ContractClauseService(Repository(), SimpleNamespace(download=lambda _: path.read_bytes()),
                                    model_factory=lambda: model)
    try:
        service.process_due(limit=1)
    finally:
        record.update(http_requests=model.http_requests, http_statuses=model.http_statuses,
                      finished_at=datetime.now(timezone.utc).isoformat())
        write_json_atomically(output, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-public-v04", action="store_true")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    if not args.run_public_v04:
        checks = local_corpus()
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 0 if all(item["all_page_text_preserved"] and item["complete_reading"] for item in checks) else 1
    if not os.getenv("GEMINI_API_KEY", "").strip():
        print("Gemini no está configurado; no se realiza ninguna llamada.")
        return 2
    try:
        record = run_public_v04()
    except FileExistsError:
        print("Ya hay evidencia de esta prueba; no se repite la llamada.")
        return 2
    print(json.dumps({"state": record["state"], "http_requests": record["http_requests"],
        "http_statuses": record["http_statuses"], "ai_proposals": record.get("origins", []).count("ia"),
        "literal_records": record.get("origins", []).count("literal"),
        "semantic_review": record["semantic_review"]}, ensure_ascii=False, indent=2))
    return 0 if record["state"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
