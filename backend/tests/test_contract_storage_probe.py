"""Prueba el verificador externo con dobles: nunca consume Storage real."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.check_contracts_storage import probe

PATH = "qa-hu29/00000000000000000000000000000001/synthetic.pdf"


def test_probe_checks_bytes_privacy_and_cleanup():
    storage = Mock()
    storage.signed_url.return_value = "https://example.invalid/signed"
    request = Mock(side_effect=[
        SimpleNamespace(status_code=200, content=b"synthetic"),
        SimpleNamespace(status_code=404), SimpleNamespace(status_code=401),
        SimpleNamespace(status_code=404),
    ])
    probe(storage, request, "https://example.invalid", PATH, b"synthetic")
    storage.upload.assert_called_once_with(PATH, b"synthetic")
    storage.delete.assert_called_once_with(PATH)
    assert request.call_count == 4
    assert 'cacheNonce=' in request.call_args.args[0]


def test_probe_does_not_report_success_if_fresh_download_survives_delete():
    storage = Mock()
    storage.signed_url.return_value = "https://example.invalid/signed?token=fake"
    request = Mock(side_effect=[
        SimpleNamespace(status_code=200, content=b"synthetic"),
        SimpleNamespace(status_code=404), SimpleNamespace(status_code=401),
        SimpleNamespace(status_code=200, content=b"synthetic"),
    ])
    with pytest.raises(RuntimeError):
        probe(storage, request, "https://example.invalid", PATH, b"synthetic")
    storage.delete.assert_called_once_with(PATH)


@pytest.mark.parametrize("failure", ["timeout", "wrong_bytes", "public_object"])
def test_probe_cleans_up_after_failure(failure):
    storage = Mock()
    request = Mock()
    if failure == "timeout":
        storage.upload.side_effect = RuntimeError("timeout")
    elif failure == "wrong_bytes":
        request.return_value = SimpleNamespace(status_code=200, content=b"wrong")
    else:
        request.return_value = SimpleNamespace(status_code=200, content=b"synthetic")
    with pytest.raises(RuntimeError):
        probe(storage, request, "https://example.invalid", PATH, b"synthetic")
    storage.delete.assert_called_once_with(PATH)


def test_probe_rejects_non_test_path_without_calls():
    storage = Mock()
    request = Mock()
    with pytest.raises(ValueError):
        probe(storage, request, "https://example.invalid", "real/contract.pdf", b"pdf")
    assert not storage.mock_calls and not request.mock_calls
