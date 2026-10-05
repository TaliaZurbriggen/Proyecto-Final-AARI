"""Comprueba la entrada experimental v5 sin imprimir contratos ni llamar a Gemini."""

from __future__ import annotations

import argparse
import json
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
from app.services.contract_clause_v5 import (  # noqa: E402
    PROMPT_PATH,
    PROMPT_VERSION,
    SegmentedInputError,
    build_segmented_input,
    build_v5_prompt,
)
from app.services.contract_text_extraction import (  # noqa: E402
    ContractTextError,
    extract_contract_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True, help="ID del corpus conocido, por ejemplo V04.")
    parser.add_argument(
        "--manifest", type=Path,
        default=PROJECT / "docs/evaluaciones/hu30/corpus_v4_manifest.json",
    )
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()

    try:
        manifest = load_json(args.manifest)
        verify_prompt_freeze(manifest, PROJECT)
        document = get_document(manifest, args.document)
        source = verify_document(document, PROJECT)
        load_dotenv(args.env_file, override=False)
        extracted = extract_contract_text(source.read_bytes())
        prepared = build_segmented_input(extracted)
        prompt = build_v5_prompt(prepared)
    except (ContractClauseCorpusError, ContractTextError, SegmentedInputError) as error:
        print(str(error))
        return 2

    segments = {block.segment_index for block in prepared.blocks if block.segment_index is not None}
    unknown = {
        block.segment_index for block in prepared.blocks
        if block.segment_index is not None and block.label is None
    }
    cross_page = sorted(
        index for index in segments
        if len({block.page for block in prepared.blocks if block.segment_index == index}) > 1
    )
    report = {
        "document": args.document,
        "source_sha256": file_sha256(source),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": file_sha256(PROMPT_PATH),
        "pages": len(extracted.pages),
        "ocr_pages": sum(page.method == "ocr" for page in extracted.pages),
        "source_characters": sum(len(page.text) for page in extracted.pages),
        "segmented_characters": len(prepared.model_text),
        "prompt_characters": len(prompt),
        "segments": len(segments),
        "unknown_segments": len(unknown),
        "cross_page_segments": cross_page,
        "unassigned_characters": sum(
            len(block.text) for block in prepared.blocks if block.segment_index is None
        ),
        "source_preserved": prepared.reconstructed_pages() == {
            page.page: page.text for page in extracted.pages
        },
        "external_calls": 0,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
