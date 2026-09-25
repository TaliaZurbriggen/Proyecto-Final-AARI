"""Corpus de contratos HU30: congelación, permisos de corrida y métricas."""

import hashlib

import pytest

from app.services.contract_clause_corpus import (
    ContractClauseCorpusError,
    calculate_review_metrics,
    get_expected_controls,
    verify_document,
    verify_prompt_freeze,
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_verifies_frozen_prompt_files_and_detects_changes(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_bytes(b"prompt v2")
    manifest = {"prompt_freeze": {"files": [{
        "path": "prompt.md", "sha256": digest(b"prompt v2"),
    }]}}

    assert verify_prompt_freeze(manifest, tmp_path)[0]["sha256"] == digest(b"prompt v2")

    prompt.write_bytes(b"prompt modificado")
    with pytest.raises(ContractClauseCorpusError, match="cambió"):
        verify_prompt_freeze(manifest, tmp_path)


def test_blocks_draft_expectations_and_reserved_holdouts(tmp_path):
    document = tmp_path / "contract.pdf"
    document.write_bytes(b"public contract")
    draft = {
        "id": "V01", "role": "validation", "path": "contract.pdf",
        "sha256": digest(b"public contract"), "expectations_state": "draft",
    }
    with pytest.raises(ContractClauseCorpusError, match="aún no fueron validados"):
        verify_document(draft, tmp_path)

    holdout = {"id": "H01", "role": "holdout", "expectations_state": "withheld"}
    with pytest.raises(ContractClauseCorpusError, match="permanecen reservados"):
        verify_document(holdout, tmp_path)

    controls_file = {"documents": {"V01": {
        "state": "draft", "controls": [{"id": "V01-E01"}],
    }}}
    with pytest.raises(ContractClauseCorpusError, match="continúan en borrador"):
        get_expected_controls(controls_file, "V01")
    assert get_expected_controls(
        controls_file, "V01", require_validated=False
    )[0]["id"] == "V01-E01"


def test_review_metrics_keep_omissions_in_the_denominator():
    controls = [
        {"id": "E01", "critical": True},
        {"id": "E02", "critical": False},
        {"id": "E03", "critical": False},
    ]
    review = {
        "controls": [
            {"id": "E01", "state": "completo"},
            {"id": "E02", "state": "completo"},
            {"id": "E03", "state": "omitido"},
        ],
        "accepted_hallucinations": 0,
    }
    metrics = calculate_review_metrics(controls, review, {
        "minimum_general_coverage": 0.85,
        "minimum_critical_recall": 1.0,
        "maximum_accepted_hallucinations": 0,
    })

    assert metrics["controls_total"] == 3
    assert metrics["controls_complete"] == 2
    assert metrics["general_coverage"] == pytest.approx(2 / 3)
    assert metrics["controls_located"] == 2
    assert metrics["content_recall"] == pytest.approx(2 / 3)
    assert metrics["critical_recall"] == 1.0
    assert metrics["passed"] is False


def test_review_requires_every_control_and_rejects_accepted_hallucinations():
    controls = [{"id": "E01", "critical": True}]
    thresholds = {
        "minimum_general_coverage": 0.85,
        "minimum_critical_recall": 1.0,
        "maximum_accepted_hallucinations": 0,
    }
    with pytest.raises(ContractClauseCorpusError, match="incluir todos"):
        calculate_review_metrics(
            controls, {"controls": [], "accepted_hallucinations": 0}, thresholds
        )

    metrics = calculate_review_metrics(controls, {
        "controls": [{"id": "E01", "state": "completo"}],
        "accepted_hallucinations": 1,
    }, thresholds)
    assert metrics["general_coverage"] == 1.0
    assert metrics["critical_recall"] == 1.0
    assert metrics["passed"] is False
