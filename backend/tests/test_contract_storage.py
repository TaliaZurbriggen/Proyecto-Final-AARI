"""Contrato HTTP del almacenamiento privado. No usa red ni credenciales reales."""
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from app.services.contract_errors import ContractError
from app.services.contract_storage import BUCKET, SupabaseContractStorage
from app.services.contracts_service import today_ar


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-placeholder")
    return SupabaseContractStorage()


def test_upload_and_delete_http_contract(storage, monkeypatch):
    request = Mock(return_value=httpx.Response(200, request=httpx.Request("POST", "https://example.invalid")))
    monkeypatch.setattr(httpx, "request", request)
    storage.upload("contract/document.pdf", b"%PDF-synthetic")
    args, kwargs = request.call_args
    assert args == ("POST", f"https://example.invalid/storage/v1/object/{BUCKET}/contract/document.pdf")
    assert kwargs["headers"]["x-upsert"] == "false"
    assert kwargs["headers"]["Content-Type"] == "application/pdf"
    assert kwargs["headers"]["Authorization"] == "Bearer test-placeholder"
    storage.delete("contract/document.pdf")
    assert request.call_args.args[0] == "DELETE"
    assert request.call_args.kwargs["json"] == {"prefixes": ["contract/document.pdf"]}


def test_download_uses_short_lived_private_signed_url(storage, monkeypatch):
    request = Mock(return_value=httpx.Response(200, json={"signedURL": f"/object/sign/{BUCKET}/contract/doc.pdf?token=fake"}, request=httpx.Request("POST", "https://example.invalid")))
    monkeypatch.setattr(httpx, "request", request)
    url = storage.signed_url("contract/doc.pdf")
    assert url == f"https://example.invalid/storage/v1/object/sign/{BUCKET}/contract/doc.pdf?token=fake"
    assert request.call_args.kwargs["json"] == {"expiresIn": 300}


@pytest.mark.parametrize("payload", [{}, {"signedURL": None}, {"signedURL": "https://other.invalid"}, {"signedURL": "/object/public/anything"}])
def test_malformed_signed_url_rejected(storage, monkeypatch, payload):
    monkeypatch.setattr(httpx, "request", Mock(return_value=httpx.Response(200, json=payload, request=httpx.Request("POST", "https://example.invalid"))))
    with pytest.raises(ContractError) as err:
        storage.signed_url("contract/doc.pdf")
    assert err.value.status == 503


def test_missing_config_and_storage_outage_are_sanitized(storage, monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")
    with pytest.raises(ContractError) as err:
        storage.upload("x.pdf", b"pdf")
    assert err.value.status == 503
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-placeholder")
    monkeypatch.setattr(httpx, "request", Mock(side_effect=httpx.ConnectError("internal details")))
    with pytest.raises(ContractError) as err:
        storage.upload("x.pdf", b"pdf")
    assert "internal details" not in str(err.value)


def test_argentina_clock_available_on_windows():
    assert isinstance(today_ar(), date)


def test_migration_explicitly_secures_tables_and_pdf_bucket():
    sql = (Path(__file__).parents[1] / "migrations" / "20_contratos_alquiler.sql").read_text(encoding="utf-8").lower()
    for table in ("contratos", "contrato_documentos", "contrato_eventos"):
        assert f"alter table public.{table} enable row level security" in sql
    assert "from public, anon, authenticated" in sql
    assert "false, 10485760, array['application/pdf']" in sql
    assert "exclude using gist" in sql
    assert "fecha_finalizacion is not null" in sql
    assert "fecha_firma" not in sql
