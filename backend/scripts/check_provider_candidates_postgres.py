"""HU15: preflight, migración autorizada y QA aislado con rollback en Supabase.

No imprime secretos, parámetros SQL ni datos personales. Los modos apply/test
requieren autorización explícita. No activa ningún worker externo.
"""

import argparse
import os
from pathlib import Path
import re
import sys

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[1]
VERSION = "20261009120000"
NAME = "hu15_proveedores_candidatos"
MIGRATION = ROOT / "migrations" / f"{VERSION}_{NAME}.sql"
TABLES = (
    "usuarios", "propietarios", "propiedades", "inquilinos", "proveedores",
    "especialidades", "proveedor_especialidades", "proveedor_coberturas",
    "proveedor_cobertura_barrios", "reclamos", "reclamo_responsables",
    "reclamo_historial_estados", "notificaciones",
)
INDEXES = (
    "idx_busquedas_proveedores_reclamo", "idx_busquedas_proveedores_usuario",
    "idx_busquedas_proveedores_especialidad", "idx_busquedas_proveedores_especialidad_anterior",
    "idx_reclamos_pendientes_asignacion",
)


def configure(env_file):
    database_url = dotenv_values(env_file).get("DATABASE_URL", "")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or not url.host or not (
        url.host.endswith(".supabase.co") or url.host.endswith(".supabase.com")
    ):
        raise ValueError("Se requiere la conexión Supabase de AARI configurada localmente.")
    os.environ["DATABASE_URL"] = database_url
    os.environ["NOTIFICATION_WORKER_ENABLED"] = "false"
    os.environ["CONTRACT_ANALYSIS_WORKER_ENABLED"] = "false"
    os.environ["PROVIDER_CANDIDATES_WORKER_ENABLED"] = "false"
    os.environ["PROVIDER_SPECIALTY_EXTERNAL_ENABLED"] = "false"
    return create_engine(url, connect_args={"connect_timeout": 10}, hide_parameters=True)


def counts(connection):
    return {table: connection.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one()
            for table in TABLES}


def verify(connection):
    security = connection.execute(text("""
        SELECT relrowsecurity,
            has_table_privilege('anon', oid, 'SELECT,INSERT,UPDATE,DELETE'),
            has_table_privilege('authenticated', oid, 'SELECT,INSERT,UPDATE,DELETE')
        FROM pg_class WHERE oid='public.reclamo_busquedas_proveedores'::regclass
    """)).one()
    assert tuple(security) == (True, False, False), "Revisar RLS/permisos."
    assert connection.execute(text("""
        SELECT count(*) FROM pg_policies WHERE schemaname='public'
        AND tablename='reclamo_busquedas_proveedores'
    """)).scalar_one() == 0, "No se esperan políticas públicas."
    for index in INDEXES:
        assert connection.execute(text("""
            SELECT indisvalid AND indisready FROM pg_index WHERE indexrelid=to_regclass(:name)
        """), {"name": "public." + index}).scalar_one(), "Falta un índice válido."
    constraints = connection.execute(text("""
        SELECT contype, convalidated FROM pg_constraint
        WHERE conrelid='public.reclamo_busquedas_proveedores'::regclass
    """)).all()
    assert all(valid for _, valid in constraints)
    assert sum(kind == "f" for kind, _ in constraints) == 4
    assert sum(kind == "u" for kind, _ in constraints) == 1
    assert sum(kind == "c" for kind, _ in constraints) == 7


def installation_state(connection):
    assert all(connection.execute(text("SELECT to_regclass(:name) IS NOT NULL"),
        {"name": "public." + table}).scalar_one() for table in TABLES), "Faltan dependencias."
    registered = connection.execute(text("""
        SELECT version, name FROM supabase_migrations.schema_migrations
        WHERE version=:version OR name=:name
    """), {"version": VERSION, "name": NAME}).all()
    installed = connection.execute(text("""
        SELECT to_regclass('public.reclamo_busquedas_proveedores') IS NOT NULL
    """)).scalar_one()
    indices = [connection.execute(text("SELECT to_regclass(:name) IS NOT NULL"),
                                  {"name": "public." + name}).scalar_one() for name in INDEXES]
    if registered:
        if registered != [(VERSION, NAME)] or not installed or not all(indices):
            raise RuntimeError("Historial o instalación inconsistentes; no se reparan automáticamente.")
        verify(connection)
        return True
    if installed or any(indices):
        raise RuntimeError("Objetos sin historial; detener antes de aplicar.")
    return False


def migration_body():
    sql = MIGRATION.read_text(encoding="utf-8")
    sql = re.sub(r"(?im)^\s*begin;\s*$", "", sql, count=1)
    return re.sub(r"(?im)^\s*commit;\s*$", "", sql, count=1)


def apply(db):
    with db.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout='5s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('aari:hu15:migration'))"))
        if installation_state(connection):
            print("Migración ya instalada y verificada: no se repite.")
            return
        before = counts(connection)
        body = migration_body()
        cursor = connection.connection.cursor()
        try:
            cursor.execute(body)
        finally:
            cursor.close()
        verify(connection)
        assert counts(connection) == before, "Los conteos variaron durante la operación; requiere revisión."
        connection.execute(text("""
            INSERT INTO supabase_migrations.schema_migrations (version, name, statements)
            VALUES (:version, :name, :statements)
        """), {"version": VERSION, "name": NAME, "statements": [body]})
        assert installation_state(connection)
    print("HU15 aplicada y registrada; conteos previos preservados, RLS/FK/índices verificados.")


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
            print("Conexión Supabase y dependencias HU15: OK.")
            print("Migración HU15:", "instalada" if installed else "pendiente")
            print("Reclamos existentes en Pendiente de asignación:", connection.execute(text(
                "SELECT count(*) FROM public.reclamos WHERE estado='Pendiente de asignación'"
            )).scalar_one())
        if args.mode == "apply":
            apply(db)
        elif args.mode == "test":
            if not installed:
                raise RuntimeError("Aplicar antes la migración autorizada.")
            os.environ["RUN_HU15_SUPABASE_INTEGRATION"] = "1"
            sys.path.insert(0, str(ROOT))
            import pytest
            return pytest.main(["-q", "-p", "no:cacheprovider", "--tb=short",
                str(ROOT / "tests" / "test_provider_candidates_supabase_integration.py")])
        return 0
    except Exception as error:
        print(f"Validación HU15 interrumpida ({type(error).__name__}); no se exponen credenciales ni SQL.")
        return 1
    finally:
        if db is not None:
            db.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
