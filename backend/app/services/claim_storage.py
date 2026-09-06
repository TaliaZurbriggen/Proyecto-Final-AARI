"""Adaptador privado para las fotos de reclamos en Supabase Storage."""

import os
from urllib.parse import quote
from uuid import UUID

import httpx

from app.services.claims_creation_service import ClaimPhotoStorageError


class SupabaseClaimPhotoStorage:
    """Usa una clave exclusiva del backend; nunca genera URLs públicas."""

    def __init__(self, *, bucket: str = "reclamos-fotos") -> None:
        self.bucket = bucket

    @staticmethod
    def _configuration() -> tuple[str, str]:
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            raise ClaimPhotoStorageError(
                "El almacenamiento privado de fotos no está configurado."
            )
        return url, key

    def upload(
        self,
        *,
        claim_id: UUID,
        tenant_id: UUID,
        photo_id: UUID,
        extension: str,
        content_type: str,
        content: bytes,
    ) -> str:
        url, key = self._configuration()
        path = f"{tenant_id}/{claim_id}/{photo_id}{extension}"
        endpoint = f"{url}/storage/v1/object/{self.bucket}/{quote(path, safe='/')}"
        try:
            response = httpx.post(
                endpoint,
                content=content,
                headers={
                    "Authorization": f"Bearer {key}",
                    "apikey": key,
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
                timeout=10,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            raise ClaimPhotoStorageError(
                "No se pudo guardar una de las fotos. Intentá nuevamente."
            ) from error
        return path

    def delete(self, path: str) -> None:
        url, key = self._configuration()
        endpoint = f"{url}/storage/v1/object/{self.bucket}"
        try:
            response = httpx.request(
                "DELETE",
                endpoint,
                headers={"Authorization": f"Bearer {key}", "apikey": key},
                json={"prefixes": [path]},
                timeout=10,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            raise ClaimPhotoStorageError(
                "No se pudo eliminar una foto temporal."
            ) from error
