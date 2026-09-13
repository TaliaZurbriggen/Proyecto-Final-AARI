"""HU29: preflight, prueba PostgreSQL aislada o aplicación explícita de la migración."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--mode", choices=["check", "test", "apply"], default="check")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL no está configurada.")
        return 2
    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 10})
    try:
        with engine.connect() as connection:
            present = connection.execute(text("SELECT to_regclass('public.contratos') IS NOT NULL")).scalar_one()
            print("Conexión PostgreSQL: OK.")
            print("Esquema de contratos:", "presente" if present else "pendiente de migración 20")
            print("Configuración Storage:", "presente" if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY") else "incompleta")
            if present:
                rows = connection.execute(text("""
                    SELECT c.relname, c.relrowsecurity,
                        has_table_privilege('anon', c.oid, 'SELECT'),
                        has_table_privilege('authenticated', c.oid, 'SELECT')
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public'
                      AND c.relname IN ('contratos','contrato_documentos','contrato_eventos')
                    ORDER BY c.relname
                """)).all()
                print("Seguridad tablas (RLS / sin lectura pública):",
                      "OK" if len(rows) == 3 and all(r[1:] == (True, False, False) for r in rows) else "REVISAR")
                bucket = connection.execute(text("SELECT public, file_size_limit FROM storage.buckets WHERE id='contratos-alquiler'")).first()
                print("Bucket privado de 10 MB:", "OK" if bucket == (False, 10485760) else "REVISAR")
                policies = connection.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND tablename='objects'")).scalar_one()
                print("Políticas de Storage a revisar:", policies)
        if args.mode == "test":
            os.environ["RUN_CONTRATOS_POSTGRES_TESTS"] = "1"
            import pytest
            return pytest.main(["-q", "-p", "no:cacheprovider", "--tb=short", str(ROOT / "tests" / "test_contratos_postgres.py")])
        if args.mode == "apply":
            if present:
                print("No se repite la migración. Revisar el esquema instalado antes de cambiarlo.")
                return 2
            raw = engine.raw_connection()
            try:
                with raw.cursor() as cursor:
                    cursor.execute((ROOT / "migrations" / "20_contratos_alquiler.sql").read_text(encoding="utf-8"))
                raw.commit()
                print("Migración 20 aplicada. No se crearon cuentas ni contratos.")
            finally:
                raw.close()
        return 0
    except Exception as error:
        # No imprimir excepciones con URL de conexión, parámetros o credenciales.
        print(f"No se pudo completar la validación PostgreSQL ({type(error).__name__}). Revisar disponibilidad/configuración.")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
