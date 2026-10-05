"""HU30: preflight, prueba aislada o aplicación explícita de migraciones 23/24/25."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
TABLES = ("contrato_analisis", "contrato_clausulas", "contrato_clausula_eventos", "contrato_analisis_intentos")


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
            contracts = connection.execute(text(
                "SELECT to_regclass('public.contrato_documentos') IS NOT NULL"
            )).scalar_one()
            present = connection.execute(text(
                "SELECT to_regclass('public.contrato_analisis') IS NOT NULL"
            )).scalar_one()
            evidence = connection.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='contrato_analisis'
                      AND column_name='propuestas_rechazadas'
                ) AND EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='contrato_clausulas'
                      AND column_name='evidencias'
                )
            """)).scalar_one()
            assisted = connection.execute(text("""
                SELECT to_regclass('public.contrato_analisis_intentos') IS NOT NULL
                  AND EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='contrato_analisis' AND column_name='modo')
                  AND EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='contrato_clausulas' AND column_name='origen')
            """)).scalar_one()
            print("Conexión PostgreSQL: OK.")
            print("Migración 20:", "presente" if contracts else "FALTA")
            print("Migración 23:", "presente" if present else "pendiente")
            print("Migración 24:", "presente" if evidence else "pendiente")
            print("Migración 25:", "presente" if assisted else "pendiente")
        if args.mode == "test":
            os.environ["RUN_CLAUSES_POSTGRES_TESTS"] = "1"
            import pytest
            return pytest.main([
                "-q", "-p", "no:cacheprovider", "--tb=short",
                str(ROOT / "tests" / "test_contract_clauses_postgres.py"),
            ])
        if args.mode == "apply":
            if not contracts:
                print("No se aplica: primero debe existir la migración 20.")
                return 2
            migrations = []
            if not present:
                migrations.append("23_clausulas_contractuales.sql")
            if not evidence:
                if not present and "23_clausulas_contractuales.sql" not in migrations:
                    print("No se aplica 24: primero debe existir la migración 23.")
                    return 2
                migrations.append("24_evidencia_clausulas_contractuales.sql")
            if not assisted:
                migrations.append("25_extraccion_asistida_literal.sql")
            if not migrations:
                print("No se repiten las migraciones 23/24/25.")
                return 0
            raw = engine.raw_connection()
            try:
                with raw.cursor() as cursor:
                    for migration in migrations:
                        cursor.execute((ROOT / "migrations" / migration).read_text(encoding="utf-8"))
                raw.commit()
                print("Migraciones aplicadas:", ", ".join(migrations))
                print("No se analizaron contratos ni se llamó a Gemini.")
            finally:
                raw.close()
        if args.mode in {"check", "apply"}:
            with engine.connect() as connection:
                rows = connection.execute(text("""
                    SELECT c.relname, c.relrowsecurity,
                        has_table_privilege('anon', c.oid, 'SELECT'),
                        has_table_privilege('authenticated', c.oid, 'SELECT')
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND c.relname = ANY(:tables)
                """), {"tables": list(TABLES)}).all()
                if rows:
                    print("RLS y ausencia de lectura pública:",
                          "OK" if len(rows) == len(TABLES) and all(row[1:] == (True, False, False) for row in rows) else "REVISAR")
        return 0
    except Exception as error:
        print(f"No se pudo completar la validación HU30 ({type(error).__name__}).")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
