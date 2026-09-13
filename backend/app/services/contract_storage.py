"""PDFs privados. Las credenciales solo se usan en el backend."""

import os
from urllib.parse import quote

import httpx

from app.services.contract_errors import ContractError

BUCKET = "contratos-alquiler"
DOWNLOAD_TTL = 300


class SupabaseContractStorage:
    def _config(self):
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            raise ContractError(
                "El almacenamiento de contratos no está configurado.",
                code="contract_storage_unavailable", status=503,
            )
        return url, {"Authorization": f"Bearer {key}", "apikey": key}

    def _request(self, method, suffix, **kwargs):
        url, headers = self._config()
        headers.update(kwargs.pop("headers", {}))
        try:
            response = httpx.request(
                method, f"{url}/storage/v1/{suffix}",
                headers=headers, timeout=20, **kwargs,
            )
            response.raise_for_status()
            return response, url
        except (httpx.HTTPError, OSError) as error:
            raise ContractError(
                "No pudimos acceder al archivo. Intentá nuevamente.",
                code="contract_storage_unavailable", status=503,
            ) from error

    def upload(self, path: str, content: bytes) -> None:
        self._request(
            "POST", f"object/{BUCKET}/{quote(path, safe='/')}", content=content,
            headers={"Content-Type": "application/pdf", "x-upsert": "false"},
        )

    def delete(self, path: str) -> None:
        self._request("DELETE", f"object/{BUCKET}", json={"prefixes": [path]})

    def signed_url(self, path: str) -> str:
        response, url = self._request(
            "POST", f"object/sign/{BUCKET}/{quote(path, safe='/')}",
            json={"expiresIn": DOWNLOAD_TTL},
        )
        try:
            signed = response.json()["signedURL"]
            if not isinstance(signed, str) or not signed.startswith(f"/object/sign/{BUCKET}/"):
                raise ValueError("Ruta inesperada")
        except (ValueError, KeyError, TypeError) as error:
            raise ContractError("No pudimos generar la descarga temporal.",
                                code="contract_storage_unavailable", status=503) from error
        return f"{url}/storage/v1{signed}"
