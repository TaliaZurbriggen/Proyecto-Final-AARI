"""HU13: preflight, aplicación explícita y QA de Supabase con rollback.

Nunca imprime variables de entorno, parámetros SQL ni datos personales.
Los modos apply/test requieren autorización previa de la persona responsable.
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
MIGRATION = ROOT / "migrations" / "26_resolucion_escalados.sql"
NAME = "hu13_resolucion_escalados"


def configure(env_file):
    # Solo la conexión; no cargar credenciales de Gemini, SMTP ni Storage.
    database_url = dotenv_values(env_file).get("DATABASE_URL", "")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or not url.host or not (
        url.host.endswith(".supabase.co") or url.host.endswith(".supabase.com")
    ):
        raise ValueError("El destino debe ser el Supabase configurado de AARI.")
    os.environ["DATABASE_URL"] = database_url
    os.environ["NOTIFICATION_WORKER_ENABLED"] = "false"
    return create_engine(url, connect_args={"connect_timeout": 10}, hide_parameters=True)


def installed_objects(connection):
    return connection.execute(text("""
        SELECT to_regclass('public.reclamo_decisiones_clasificacion') IS NOT NULL AS audit,
            to_regclass('public.idx_decisiones_clasificacion_reclamo') IS NOT NULL AS audit_index,
            to_regclass('public.idx_reclamos_cola_clasificacion') IS NOT NULL AS queue_index,
            to_regprocedure('public.notificar_clasificacion_pendiente()') IS NOT NULL AS function,
            EXISTS (SELECT 1 FROM pg_trigger
                WHERE tgrelid = 'public.reclamo_historial_estados'::regclass
                    AND tgname = 'trg_notificar_clasificacion_pendiente'
                    AND NOT tgisinternal) AS trigger
    """)).mappings().one()


def verify(connection):
    assert all(installed_objects(connection).values()), "Faltan objetos de HU13."
    security = connection.execute(text("""
        SELECT c.relrowsecurity,
            has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE'),
            has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE')
        FROM pg_class c WHERE c.oid = 'public.reclamo_decisiones_clasificacion'::regclass
    """)).one()
    assert tuple(security) == (True, False, False), "Revisar RLS/permisos."
    assert connection.execute(text("""
        SELECT count(*) FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'reclamo_decisiones_clasificacion'
    """)).scalar_one() == 0, "No se esperan políticas de acceso directo."
    for role in ("anon", "authenticated"):
        assert not connection.execute(text("""
            SELECT has_function_privilege(:role, 'public.notificar_clasificacion_pendiente()', 'EXECUTE')
        """), {"role": role}).scalar_one()
    function = connection.execute(text("""
        SELECT prosecdef, proconfig FROM pg_proc
        WHERE oid = 'public.notificar_clasificacion_pendiente()'::regprocedure
    """)).one()
    assert function.prosecdef is False and 'search_path=""' in function.proconfig
    assert connection.execute(text("""
        SELECT tgenabled FROM pg_trigger
        WHERE tgrelid = 'public.reclamo_historial_estados'::regclass
            AND tgname = 'trg_notificar_clasificacion_pendiente'
    """)).scalar_one() == "O"


def apply(db):
    body = MIGRATION.read_text(encoding="utf-8")
    body = re.sub(r"(?im)^\s*begin;\s*$", "", body, count=1)
    body = re.sub(r"(?im)^\s*commit;\s*$", "", body, count=1)
    with db.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('aari:hu13:26'))"))
        objects = installed_objects(connection)
        if all(objects.values()):
            verify(connection)
            print("Migración 26 ya instalada y verificada; no se repite.")
            return
        if any(objects.values()):
            raise RuntimeError("Instalación parcial: requiere revisión antes de aplicar.")
        if connection.execute(text("""
            SELECT EXISTS (SELECT 1 FROM supabase_migrations.schema_migrations WHERE name = :name)
        """), {"name": NAME}).scalar_one():
            raise RuntimeError("El historial y los objetos no coinciden; no se modifica el historial.")
        cursor = connection.connection.cursor()
        try:
            # Sin parámetros DBAPI: conservar los %s literales de pg_catalog.format.
            cursor.execute(body)
        finally:
            cursor.close()
        verify(connection)
        version = connection.execute(text("""
            SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISS')
        """)).scalar_one()
        connection.execute(text("""
            INSERT INTO supabase_migrations.schema_migrations (version, name, statements)
            VALUES (:version, :name, :statements)
        """), {"version": version, "name": NAME, "statements": [body]})
    print(f"Migración 26 aplicada y registrada: {version}_{NAME}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--mode", choices=["check", "apply", "test"], default="check")
    args = parser.parse_args()
    db = None
    try:
        db = configure(args.env_file)
        with db.connect() as connection:
            assert connection.execute(text("SELECT to_regclass('public.reclamo_responsables') IS NOT NULL")).scalar_one()
            objects = installed_objects(connection)
            print("Conexión Supabase y dependencia HU12: OK.")
            print("Migración HU13:", "instalada" if all(objects.values()) else "pendiente o incompleta")
            if all(objects.values()):
                verify(connection)
                print("Auditoría, índices, trigger, RLS y permisos: OK.")
        if args.mode == "apply":
            apply(db)
        elif args.mode == "test":
            with db.connect() as connection:
                verify(connection)
            os.environ["RUN_HU13_SUPABASE_INTEGRATION"] = "1"
            sys.path.insert(0, str(ROOT))
            import pytest
            return pytest.main(["-q", "-p", "no:cacheprovider", "--tb=short",
                str(ROOT / "tests" / "test_escalados_supabase_integration.py")])
        return 0
    except Exception as error:
        # No imprimir str(error), URL ni parámetros. El cambio DDL es atómico.
        print(f"Validación HU13 interrumpida ({type(error).__name__}); no se exponen datos de conexión.")
        return 1
    finally:
        if db is not None:
            db.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
