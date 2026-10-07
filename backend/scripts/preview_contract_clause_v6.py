"""Verifica v6 localmente; puede repetir una salida archivada sin llamar a Gemini."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.schemas.clausulas_contrato import ExtractedClauseBatch  # noqa: E402
from app.services.contract_clause_corpus import (  # noqa: E402
    ContractClauseCorpusError,
    file_sha256,
    get_document,
    load_json,
    verify_document,
    verify_prompt_freeze,
)
from app.services.contract_clause_v5 import build_segmented_input  # noqa: E402
from app.services.contract_clause_v6 import (  # noqa: E402
    PROMPT_PATH,
    PROMPT_VERSION,
    build_v6_prompt,
    validate_v6_batch,
)
from app.services.contract_text_extraction import (  # noqa: E402
    ContractTextError,
    extract_contract_text,
)


MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v4_manifest.json"
V5_V04 = PROJECT / "docs/evaluaciones/hu30/resultados_v5/resultado_v04_v5.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", choices=("V01", "V02", "V03", "V04"), required=True)
    parser.add_argument("--replay-v5-v04", action="store_true")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    if args.replay_v5_v04 and args.document != "V04":
        parser.error("El replay archivado sólo corresponde a V04.")

    try:
        manifest = load_json(MANIFEST)
        verify_prompt_freeze(manifest, PROJECT)
        source = verify_document(get_document(manifest, args.document), PROJECT)
        load_dotenv(args.env_file, override=False)
        extracted = extract_contract_text(source.read_bytes())
        prepared = build_segmented_input(extracted)
        prompt = build_v6_prompt(prepared)
        report = {
            "document": args.document,
            "source_sha256": file_sha256(source),
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": file_sha256(PROMPT_PATH),
            "pages": len(extracted.pages),
            "segments": len({item.segment_index for item in prepared.blocks if item.segment_index}),
            "source_preserved": prepared.reconstructed_pages() == {
                page.page: page.text for page in extracted.pages
            },
            "prompt_characters": len(prompt),
            "external_calls": 0,
        }
        if args.replay_v5_v04:
            archived = load_json(V5_V04)
            if archived.get("state") != "completed" or archived.get("source_sha256") != report["source_sha256"]:
                raise ContractClauseCorpusError("El resultado v5 no coincide con la fuente V04.")
            batch = ExtractedClauseBatch.model_validate({"clausulas": archived["proposals"]})
            accepted, rejected, _ = validate_v6_batch(
                batch, {page.page: page.text for page in extracted.pages}
            )
            report["replay_v5_v04"] = {
                "proposals": len(batch.clausulas),
                "accepted": len(accepted),
                "rejected_ordinals": [item.ordinal for item in rejected],
                "rejection_reasons": [
                    {"ordinal": item.ordinal, "reason": item.motivo}
                    for item in rejected
                ],
                "historical_result_unchanged": True,
            }
    except ContractTextError as error:
        print(f"La lectura local del PDF no pudo completarse: {error}")
        return 2
    except (ContractClauseCorpusError, ValueError, KeyError) as error:
        print(f"La comprobación local no pudo completarse ({type(error).__name__}).")
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
