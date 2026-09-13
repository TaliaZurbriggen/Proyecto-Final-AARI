"""Prueba optativa de Storage real: PDF sintético, sin tocar contratos ni personas."""
import argparse
from io import BytesIO
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.contract_storage import BUCKET, SupabaseContractStorage


def probe(storage, request, base_url, path, content):
    """Elimina solo la ruta UUID de esta prueba, incluso ante una falla parcial."""
    if not re.fullmatch(r"qa-hu29/[0-9a-f]{32}/synthetic\.pdf", path):
        raise ValueError("Ruta de prueba no permitida")
    signed = None
    try:
        storage.upload(path, content)
        signed = storage.signed_url(path)
        response = request(signed)
        if response.status_code != 200 or response.content != content:
            raise RuntimeError("La descarga no coincide con el PDF subido")
        print("Subida y descarga firmada: OK (bytes idénticos).")
        for prefix in ("object/public", "object"):
            response = request(f"{base_url}/storage/v1/{prefix}/{BUCKET}/{quote(path, safe='/')}")
            if response.status_code not in (400, 401, 403, 404):
                raise RuntimeError("Revisar privacidad del objeto")
        print("Acceso público y acceso sin credenciales: rechazados.")
    finally:
        # Un timeout de subida también puede haber persistido el objeto.
        # La ruta es exclusiva de esta ejecución; no se enumeran ni borran otros archivos.
        try:
            storage.delete(path)
        except Exception:
            print(f"REVISAR LIMPIEZA del objeto sintético: {BUCKET}/{path}")
            raise
    # La URL recién descargada puede seguir en CDN después del DELETE. Un nonce
    # nuevo evita comprobar esa copia en caché en lugar del objeto de origen.
    if signed:
        separator = "&" if "?" in signed else "?"
        uncached = f"{signed}{separator}cacheNonce={uuid4().hex}"
        if request(uncached).status_code not in (400, 401, 403, 404):
            print(f"REVISAR AUSENCIA del objeto sintético: {BUCKET}/{path}")
            raise RuntimeError("No se pudo verificar la eliminación del objeto")
    print("Objeto sintético eliminado y ausencia comprobada.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--run", action="store_true", help="Solo después de autorización explícita para usar Storage real.")
    args = parser.parse_args()
    if not args.run:
        print("No se contactó Storage. Requiere autorización y el indicador --run.")
        return 2
    load_dotenv(args.env_file, override=True)
    base_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    if not base_url or not os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip():
        print("Faltan SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY en el .env del worktree.")
        return 2
    if not base_url.startswith("https://"):
        print("La URL del proyecto debe usar HTTPS.")
        return 2
    pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(pdf)
    path = f"qa-hu29/{uuid4().hex}/synthetic.pdf"
    try:
        # Cliente sin cabeceras ni cookies de autenticación: la URL firmada autoriza
        # la descarga, mientras que las otras rutas deben permanecer inaccesibles.
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            probe(SupabaseContractStorage(), client.get, base_url, path, pdf.getvalue())
        print("Storage real: aprobado. No se modificaron registros del sistema.")
        return 0
    except Exception as error:
        # Nunca imprimir una excepción HTTP: puede contener la URL firmada/token.
        print(f"Storage real: no aprobado ({type(error).__name__}). Revisar configuración o disponibilidad.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
