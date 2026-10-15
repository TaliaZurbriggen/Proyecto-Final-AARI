"""Preflight HU21: solo lectura por defecto, aplicación local explícita."""

import argparse
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url
from dotenv import load_dotenv


MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "20261011222710_hu21_contexto_persistente.sql"
VERSION = "20261011222710"
NAME = "hu21_contexto_persistente"
TABLES = {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes", "eventos"}


def installation_state(conn):
    history_exists = conn.execute(
        "SELECT to_regclass('supabase_migrations.schema_migrations') AS value"
    ).fetchone()["value"] is not None
    history = bool(history_exists and conn.execute(
        "SELECT 1 FROM supabase_migrations.schema_migrations WHERE version=%s", (VERSION,)
    ).fetchone())
    installed = {row["tablename"] for row in conn.execute("""
        SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='aari_coordinacion'
    """)}
    if installed and installed != TABLES or bool(installed) != history:
        raise RuntimeError("Deriva entre objetos e historial HU21. No se repara automáticamente.")
    return history


def verify(conn):
    if not installation_state(conn):
        raise RuntimeError("La migración HU21 no está aplicada.")
    for row in conn.execute("""
        SELECT schemaname, tablename, rowsecurity FROM pg_catalog.pg_tables
        WHERE schemaname='aari_coordinacion'
           OR (schemaname='public' AND tablename='sesiones_agente')
    """):
        if not row["rowsecurity"]:
            raise RuntimeError("Hay una tabla de contexto sin RLS.")
        for role in ("anon", "authenticated"):
            if conn.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE') AS allowed",
                            (role, f"{row['schemaname']}.{row['tablename']}")).fetchone()["allowed"]:
                raise RuntimeError("Permisos públicos inesperados en el contexto.")
    versions = [r["v"] for r in conn.execute(
        "SELECT v FROM aari_coordinacion.checkpoint_migrations ORDER BY v"
    )]
    if versions != list(range(10)):
        raise RuntimeError("La versión del esquema de checkpoints no coincide con 3.1.2.")


def apply(conn):
    with conn.transaction():
        if installation_state(conn):
            verify(conn)
            return False
        conn.execute("CREATE SCHEMA IF NOT EXISTS supabase_migrations")
        conn.execute("""CREATE TABLE IF NOT EXISTS supabase_migrations.schema_migrations(
            version text primary key, statements text[], name text
        )""")
        # Transacción exterior integra DDL e historial; quitar solo los límites del archivo.
        sql = MIGRATION.read_text(encoding="utf-8")
        sql = sql.replace("\nbegin;\n", "\n").replace("\ncommit;\n", "\n")
        conn.execute(sql)
        conn.execute("""INSERT INTO supabase_migrations.schema_migrations(version,name,statements)
                        VALUES (%s,%s,%s)""", (VERSION, NAME, [sql]))
        verify(conn)
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("check", "apply"), default="check")
    parser.add_argument("--allow-shared", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() != "postgresql":
        raise SystemExit("Se requiere PostgreSQL.")
    if url.host not in {"localhost", "127.0.0.1", "::1"} and not args.allow_shared:
        raise SystemExit("Destino no local: requiere autorización y --allow-shared explícito.")
    with psycopg.connect(host=url.host, port=url.port or 5432, dbname=url.database,
                         user=url.username, password=url.password, row_factory=dict_row,
                         **dict(url.query)) as conn:
        if args.mode == "apply":
            apply(conn)
        else:
            verify(conn)
    print("HU21: esquema, historial y permisos verificados.")


if __name__ == "__main__":
    main()
