"""Regresiones de reservas: API simulada, sin cuotas ni servicios externos."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.clausulas_contrato import AnalysisJob
from app.services.contract_clause_service import ContractClauseService
from app.services.contract_text_extraction import ContractText, PageText


def worker(monkeypatch, repository):
    monkeypatch.setattr(
        "app.services.contract_clause_service.extract_contract_text",
        lambda *_: ContractText([PageText(1, "PRIMERA: Texto sintético.", "digital", True)], True),
    )
    model = Mock()
    model.invoke.return_value = {"clausulas": []}
    storage = Mock()
    storage.download.return_value = b"synthetic"
    service = ContractClauseService(repository, storage, model_factory=lambda: model)
    return service, model, storage


def job():
    return AnalysisJob(uuid4(), uuid4(), uuid4(), "private/synthetic.pdf", 1,
                       execution_id=uuid4())


def test_each_job_is_reserved_only_when_it_will_be_processed(monkeypatch):
    jobs = [job() for _ in range(3)]
    repository = Mock()
    repository.renew_lease.return_value = True
    events = []
    repository.claim_due.side_effect = lambda **kwargs: (
        events.append(("claim", kwargs["limit"])) or [jobs.pop(0)]
    )
    service, model, _ = worker(monkeypatch, repository)
    model.invoke.side_effect = lambda _: events.append(("model", None)) or {"clausulas": []}

    assert service.process_due(limit=3) == 3
    assert events == [("claim", 1), ("model", None)] * 3
    assert model.invoke.call_count == repository.complete.call_count == 3


@pytest.mark.parametrize("lost_before", ["download", "model", "complete"])
def test_a_lost_reservation_stops_processing_without_touching_the_new_owner(monkeypatch, lost_before):
    repository = Mock()
    repository.claim_due.side_effect = [[job()], []]
    renewals = {"download": [False], "model": [True, False], "complete": [True, True, False]}
    repository.renew_lease.side_effect = renewals[lost_before]
    service, model, storage = worker(monkeypatch, repository)

    assert service.process_due() == 1
    assert storage.download.call_count == (0 if lost_before == "download" else 1)
    assert model.invoke.call_count == (1 if lost_before == "complete" else 0)
    repository.complete.assert_not_called()
    repository.fail.assert_not_called()


def test_database_error_before_sending_text_does_not_consume_model_quota(monkeypatch):
    repository = Mock()
    repository.claim_due.side_effect = [[job()], []]
    repository.renew_lease.side_effect = [True, RuntimeError("private details")]
    service, model, _ = worker(monkeypatch, repository)

    service.process_due()
    model.invoke.assert_not_called()
    repository.fail.assert_not_called()


@pytest.mark.parametrize("interval", [0, -1, 180, 181])
def test_renewal_interval_must_fit_within_the_lease(interval):
    with pytest.raises(ValueError):
        ContractClauseService(None, None, lease_interval_seconds=interval)
