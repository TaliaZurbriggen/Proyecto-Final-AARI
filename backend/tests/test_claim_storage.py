"""Contrato HTTP del adaptador Storage sin llamadas externas."""

from uuid import uuid4

import httpx

from app.services.claim_storage import SupabaseClaimPhotoStorage


def test_upload_uses_private_backend_credentials_and_generated_path(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-for-test")
    captured = {}

    def fake_post(url, **options):
        captured.update({"url": url, **options})
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    tenant_id, claim_id, photo_id = uuid4(), uuid4(), uuid4()

    path = SupabaseClaimPhotoStorage().upload(
        claim_id=claim_id,
        tenant_id=tenant_id,
        photo_id=photo_id,
        extension=".png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\ncontenido",
    )

    assert path == f"{tenant_id}/{claim_id}/{photo_id}.png"
    assert captured["url"].endswith(f"/reclamos-fotos/{path}")
    assert captured["headers"]["Authorization"] == "Bearer service-role-for-test"
    assert captured["headers"]["x-upsert"] == "false"


def test_delete_uses_storage_api_batch_contract(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-for-test")
    captured = {}

    def fake_request(method, url, **options):
        captured.update({"method": method, "url": url, **options})
        return httpx.Response(200, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    SupabaseClaimPhotoStorage().delete("tenant/claim/photo.png")

    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/storage/v1/object/reclamos-fotos")
    assert captured["json"] == {"prefixes": ["tenant/claim/photo.png"]}
