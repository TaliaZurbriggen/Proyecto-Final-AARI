"""Aplicación autorizada HU21: destino verificado y preservación transaccional.

No inicia FastAPI/workers, no crea datos de prueba y no transmite mensajes.
Requiere --authorized explícito. No imprime conexiones ni valores de filas.
"""

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from scripts.check_coordination_postgres import VERSION, apply, verify


PROJECT_REF = "kmisxmwrqthqkrbsqcfq"
SESSION_OLD_COLUMNS = (
    "id", "reclamo_id", "estado_grafo", "ultima_actividad", "created_at", "updated_at",
)


def fingerprints(conn):
    names = [r["tablename"] for r in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )]
    result = {}
    for name in names:
        if name == "sesiones_agente":
            pairs = []
            for column in SESSION_OLD_COLUMNS:
                pairs.extend([sql.Literal(column), sql.Identifier("t", column)])
            row = sql.SQL("jsonb_build_object({})").format(sql.SQL(",").join(pairs))
        else:
            row = sql.SQL("to_jsonb(t)")
        statement = sql.SQL("""
            SELECT count(*) AS n,
                   md5(coalesce(string_agg(md5({row}::text),''
                        ORDER BY md5({row}::text)),'')) AS digest
            FROM {table} t
        """).format(row=row, table=sql.Identifier("public", name))
        result[name] = conn.execute(statement).fetchone()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--env-root", required=True, type=Path)
    args = parser.parse_args()
    if not args.authorized:
        raise SystemExit("Se requiere autorización humana y --authorized explícito.")
    values = {}
    for path in (args.env_root / ".env", args.env_root / "backend" / ".env"):
        if path.is_file():
            values.update(dotenv_values(path))
    raw = values.get("DATABASE_URL")
    if not raw:
        raise SystemExit("DATABASE_URL no disponible.")
    try:
        url = make_url(raw)
    except Exception:
        raise SystemExit("DATABASE_URL no válida; el valor no se muestra.") from None
    direct_host = f"db.{PROJECT_REF}.supabase.co"
    correct_target = (
        url.host == direct_host
        or (bool(url.host) and url.host.endswith(".pooler.supabase.com")
            and url.username == f"postgres.{PROJECT_REF}")
    )
    if (url.get_backend_name() != "postgresql" or
            not correct_target):
        raise SystemExit("El destino no coincide con el proyecto AARI autorizado.")
    kwargs = dict(
        host=url.host, port=url.port or 5432, dbname=url.database, user=url.username,
        password=url.password, row_factory=dict_row, connect_timeout=10,
        prepare_threshold=None,
    )
    kwargs.update(url.query)
    try:
        with psycopg.connect(**kwargs) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                before = fingerprints(conn)
                applied = apply(conn)
                verify(conn)
                after = fingerprints(conn)
                if before != after:
                    raise RuntimeError("Cambió un dato existente: se revierte toda la aplicación.")
            # La salida sucede solo después del commit.
            session_count = after["sesiones_agente"]["n"]
        print(json.dumps({
            "project": "AARI", "version": VERSION, "applied": applied,
            "public_tables_checked": len(before), "existing_rows_preserved": True,
            "session_count": session_count, "outbound_messages": 0,
        }))
    except Exception as error:
        # No incluir cadenas de conexión, SQL ni filas en errores.
        print(json.dumps({"success": False, "error_type": type(error).__name__,
                          "message": "Aplicación no confirmada; verificar esquema e historial."}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
