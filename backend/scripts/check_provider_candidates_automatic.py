"""HU15 automático: migración incremental y QA autorizado con rollback.

No activa workers, no lee descripciones reales ni envía datos a Gemini.
Se reutiliza la configuración segura y el historial de la migración base.
"""

import argparse
import os
from pathlib import Path
import re
import sys

from sqlalchemy import text

from check_provider_candidates_postgres import ROOT, configure, counts, installation_state as base_state

VERSION = "20261011160000"
NAME = "hu15_busqueda_automatica"
MIGRATION = ROOT / "migrations" / f"{VERSION}_{NAME}.sql"


def verify(connection):
    assert tuple(connection.execute(text("""
        SELECT relrowsecurity,
            has_table_privilege('anon',oid,'SELECT,INSERT,UPDATE,DELETE'),
            has_table_privilege('authenticated',oid,'SELECT,INSERT,UPDATE,DELETE')
        FROM pg_class WHERE oid='public.reclamo_tareas_proveedores'::regclass
    """)).one()) == (True, False, False), "Revisar RLS/permisos de tareas."
    assert connection.execute(text("""
        SELECT count(*) FROM pg_policies WHERE schemaname='public'
            AND tablename='reclamo_tareas_proveedores'
    """)).scalar_one() == 0
    assert connection.execute(text("""
        SELECT indisvalid AND indisready FROM pg_index
        WHERE indexrelid='public.idx_tareas_proveedores_pendientes'::regclass
    """)).scalar_one()
    constraints = connection.execute(text("""
        SELECT contype, convalidated FROM pg_constraint
        WHERE conrelid='public.reclamo_tareas_proveedores'::regclass
    """)).all()
    assert all(valid for _, valid in constraints)
    for kind, expected in (("p",1), ("f",1), ("u",1), ("c",5)):
        assert sum(actual == kind for actual, _ in constraints) == expected


def installation_state(connection):
    assert base_state(connection), "Aplicar primero la migración base HU15."
    registered = connection.execute(text("""
        SELECT version,name FROM supabase_migrations.schema_migrations
        WHERE version=:version OR name=:name
    """), {"version": VERSION, "name": NAME}).all()
    installed, index = connection.execute(text("""
        SELECT to_regclass('public.reclamo_tareas_proveedores') IS NOT NULL,
            to_regclass('public.idx_tareas_proveedores_pendientes') IS NOT NULL
    """)).one()
    if registered:
        assert registered == [(VERSION, NAME)] and installed and index, "Historial inconsistente."
        verify(connection)
        return True
    assert not installed and not index, "Objetos sin historial; no reparar automáticamente."
    return False


def preserved_counts(connection):
    return {**counts(connection), "reclamo_busquedas_proveedores": connection.execute(text(
        "SELECT count(*) FROM public.reclamo_busquedas_proveedores")).scalar_one()}


def apply(db):
    with db.begin() as connection:
        connection.execute(text("SET LOCAL statement_timeout='30s'"))
        connection.execute(text("SET LOCAL lock_timeout='5s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('aari:hu15:migration'))"))
        if installation_state(connection):
            print("Migración automática ya instalada y verificada; no se repite.")
            return
        before = preserved_counts(connection)
        body = MIGRATION.read_text(encoding="utf-8")
        body = re.sub(r"(?im)^\s*begin;\s*$", "", body, count=1)
        body = re.sub(r"(?im)^\s*commit;\s*$", "", body, count=1)
        cursor = connection.connection.cursor()
        try:
            cursor.execute(body)
        finally:
            cursor.close()
        verify(connection)
        assert preserved_counts(connection) == before, "Los conteos variaron; revisar antes de confirmar."
        connection.execute(text("""
            INSERT INTO supabase_migrations.schema_migrations (version,name,statements)
            VALUES (:version,:name,:statements)
        """), {"version": VERSION, "name": NAME, "statements": [body]})
        assert installation_state(connection)
    print("Migración automática aplicada y registrada; datos/auditoría preservados y RLS verificado.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--mode", choices=["check", "apply", "test"], default="check")
    args = parser.parse_args()
    db = None
    try:
        db = configure(args.env_file)
        with db.connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout='15s'"))
            installed = installation_state(connection)
            print("Conexión y dependencias HU15: OK. Migración automática:", "instalada" if installed else "pendiente")
        if args.mode == "apply":
            apply(db)
        elif args.mode == "test":
            assert installed, "Aplicar antes la migración autorizada."
            os.environ["RUN_HU15_SUPABASE_INTEGRATION"] = "1"
            os.environ["RUN_HU15_AUTOMATIC_SUPABASE_INTEGRATION"] = "1"
            sys.path.insert(0, str(ROOT))
            import pytest
            return pytest.main(["-q", "-p", "no:cacheprovider", "--tb=short",
                str(ROOT / "tests/test_provider_candidates_supabase_integration.py"),
                str(ROOT / "tests/test_provider_candidates_automatic_supabase_integration.py")])
        return 0
    except Exception as error:
        print(f"Validación HU15 interrumpida ({type(error).__name__}); sin credenciales ni SQL en la salida.")
        return 1
    finally:
        if db is not None:
            db.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
