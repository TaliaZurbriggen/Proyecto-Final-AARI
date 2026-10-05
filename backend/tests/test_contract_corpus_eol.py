"""Checkout LF/CRLF real de Git: hashes reproducibles y PDF sin normalización."""

import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest

from app.services.contract_clause_corpus import (
    ContractClauseCorpusError, file_sha256, load_json, verify_prompt_freeze,
)


PROJECT = Path(__file__).resolve().parents[2]
PROMPT = "backend/prompts/prompt_extraccion_clausulas_v8.md"
OCR = "backend/app/services/contract_text_extraction.py"
DIAGNOSTIC = "backend/scripts/diagnose_contract_schema_flash38.py"
EVIDENCE = "docs/evaluaciones/hu30/diagnostico_sintetico/resultado.json"


def git(directory, *args):
    return subprocess.run(
        ["git", "-C", str(directory), *args], check=True, capture_output=True,
    ).stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="Requiere Git local; no accede a red.")
@pytest.mark.parametrize("autocrlf", ["true", "false"])
def test_frozen_files_checkout_as_lf_even_from_crlf_input(tmp_path, autocrlf):
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "core.autocrlf", autocrlf)
    git(tmp_path, "config", "core.safecrlf", "false")
    (tmp_path / ".gitattributes").write_bytes((PROJECT / ".gitattributes").read_bytes())
    frozen = load_json(PROJECT / "docs/evaluaciones/hu30/corpus_v8_manifest.json")
    expected = {item["path"]: item["sha256"] for item in frozen["prompt_freeze"]["files"]}
    expected[DIAGNOSTIC] = load_json(
        PROJECT / "docs/evaluaciones/hu30/diagnostico_flash38_esquema_completo/resultado.json"
    )["script_sha256"]
    protected = (PROMPT, OCR, DIAGNOSTIC)
    for name in protected:
        canonical = (PROJECT / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(canonical).hexdigest() == expected[name]
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical.replace(b"\n", b"\r\n"))

    # Incluye CRLF y bytes no textuales: Git debe conservar el PDF exactamente.
    binary_pdf = b"%PDF-1.7\r\n\x00\xff\ncontenido\r\n%%EOF"
    (tmp_path / "contract.pdf").write_bytes(binary_pdf)
    (tmp_path / "unprotected.txt").write_bytes(b"control\n")
    raw_evidence = b'{\r\n  "state": "completed"\n}\r\n'
    evidence = tmp_path / EVIDENCE
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_bytes(raw_evidence)
    git(tmp_path, "add", ".")
    for name in (*protected, EVIDENCE, "contract.pdf", "unprotected.txt"):
        (tmp_path / name).unlink()
    git(tmp_path, "checkout-index", "--all", "--force")

    manifest = {"prompt_freeze": {"files": [
        {"path": name, "sha256": expected[name]} for name in protected
    ]}}
    assert len(verify_prompt_freeze(manifest, tmp_path)) == 3
    assert all(b"\r\n" not in (tmp_path / name).read_bytes() for name in protected)
    assert (tmp_path / "unprotected.txt").read_bytes() == (
        b"control\r\n" if autocrlf == "true" else b"control\n"
    )
    assert (tmp_path / "contract.pdf").read_bytes() == binary_pdf
    assert evidence.read_bytes() == raw_evidence
    assert file_sha256(tmp_path / "contract.pdf") == hashlib.sha256(binary_pdf).hexdigest()
    assert file_sha256(tmp_path / "contract.pdf") != hashlib.sha256(
        binary_pdf.replace(b"\r\n", b"\n")
    ).hexdigest()

    # Un cambio real no se disimula mediante normalización del hash.
    with (tmp_path / PROMPT).open("ab") as source:
        source.write(b"Cambio real\n")
    with pytest.raises(ContractClauseCorpusError, match="cambió"):
        verify_prompt_freeze(manifest, tmp_path)


def test_gitattributes_covers_all_manifest_frozen_paths():
    attributes = (PROJECT / ".gitattributes").read_text(encoding="utf-8")
    manifests = list((PROJECT / "docs/evaluaciones/hu30").glob("*manifest*.json"))
    assert manifests
    checked = set()
    for path in manifests:
        for item in load_json(path).get("prompt_freeze", {}).get("files", []):
            checked.add(item["path"])
            assert f"{item['path']} text eol=lf" in attributes.splitlines()
    assert PROMPT in checked and OCR in checked
