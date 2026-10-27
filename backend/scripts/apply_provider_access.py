"""HU32: preflight de solo lectura y aplicación compartida autorizada.

No crea usuarios/invitaciones, no inicia workers ni envía mensajes.
No imprime conexiones, tokens, correos ni filas de negocio.
"""

import argparse
import json
from pathlib import Path
import re

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url


PROJECT_REF = "kmisxmwrqthqkrbsqcfq"
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
FILES = ("20261026180000_hu32_rol_proveedor.sql", "20261026180100_hu32_acceso_proveedor.sql")


def counts(conn):
    tables = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
    return {row['tablename']: conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(
        sql.Identifier('public', row['tablename']))).fetchone()['n'] for row in tables}


def state(conn):
    return {
        'role': conn.execute("SELECT EXISTS(SELECT 1 FROM pg_enum WHERE enumtypid='public.rol_usuario'::regtype AND enumlabel='proveedor') AS ok").fetchone()['ok'],
        'columns': [r['column_name'] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='proveedores' AND column_name IN ('email','usuario_id') ORDER BY column_name")],
        'invitations': conn.execute("SELECT to_regclass('public.proveedor_invitaciones') IS NOT NULL AS ok").fetchone()['ok'],
    }


def verify(conn):
    if state(conn) != {'role': True, 'columns': ['email', 'usuario_id'], 'invitations': True}:
        raise RuntimeError('Esquema HU32 incompleto.')
    if not conn.execute("SELECT relrowsecurity AS ok FROM pg_class WHERE oid='public.proveedor_invitaciones'::regclass").fetchone()['ok']:
        raise RuntimeError('RLS no está habilitado.')
    if conn.execute("SELECT count(*) AS n FROM pg_policies WHERE schemaname='public' AND tablename='proveedor_invitaciones'").fetchone()['n']:
        raise RuntimeError('Políticas públicas inesperadas.')
    for role in ('anon', 'authenticated'):
        if conn.execute("SELECT has_table_privilege(%s,'public.proveedor_invitaciones','SELECT,INSERT,UPDATE,DELETE') AS ok", (role,)).fetchone()['ok']:
            raise RuntimeError('Permisos públicos inesperados.')
    if conn.execute("SELECT count(*) AS n FROM pg_trigger WHERE tgname IN ('hu32_proveedor_identidad','hu32_usuario_identidad')").fetchone()['n'] != 2:
        raise RuntimeError('Validaciones de identidad incompletas.')


def apply(conn):
    conn.execute('SELECT pg_advisory_lock(347,32)')
    try:
        for filename in FILES:
            version = filename.split('_')[0]
            applied = conn.execute('SELECT 1 FROM supabase_migrations.schema_migrations WHERE version=%s', (version,)).fetchone()
            if applied:
                continue
            raw = (MIGRATIONS / filename).read_text(encoding='utf-8')
            # Solo límites de transacción a nivel de línea, nunca cuerpos PL/pgSQL.
            body = re.sub(r'(?m)^(BEGIN;|COMMIT;)\s*$', '', raw)
            with conn.transaction():
                conn.execute("SET LOCAL lock_timeout='5s'")
                conn.execute("SET LOCAL statement_timeout='30s'")
                before = counts(conn)
                conn.execute(body)
                if filename == FILES[1]:
                    verify(conn)
                after = counts(conn)
                if any(after.get(table) != n for table, n in before.items()):
                    raise RuntimeError('Conteos existentes cambiaron; rollback de esta etapa.')
                conn.execute('INSERT INTO supabase_migrations.schema_migrations(version,name,statements) VALUES (%s,%s,%s)',
                             (version, filename[len(version)+1:-4], [raw]))
        verify(conn)
    finally:
        conn.execute('SELECT pg_advisory_unlock(347,32)')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-root', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--authorized', action='store_true')
    args = parser.parse_args()
    values = {}
    for path in (args.env_root / '.env', args.env_root / 'backend' / '.env'):
        if path.is_file(): values.update(dotenv_values(path))
    try:
        url = make_url(values.get('DATABASE_URL', ''))
        target = (url.host == f'db.{PROJECT_REF}.supabase.co' or
                  (url.host and url.host.endswith('.pooler.supabase.com') and url.username == f'postgres.{PROJECT_REF}'))
        if not target or url.get_backend_name() != 'postgresql':
            raise ValueError('Destino distinto al AARI autorizado.')
        if args.apply and not args.authorized:
            raise ValueError('Aplicar requiere --authorized y autorización humana.')
        options = dict(url.query)
        options.setdefault('sslmode', 'require')
        with psycopg.connect(host=url.host, port=url.port or 5432, dbname=url.database,
                             user=url.username, password=url.password, connect_timeout=10,
                             row_factory=dict_row, autocommit=True, prepare_threshold=None, **options) as conn:
            initial = state(conn)
            before = counts(conn)
            if args.apply:
                apply(conn)
            after = counts(conn)
            preserved = all(after.get(table) == n for table, n in before.items())
            if not preserved: raise RuntimeError('Los conteos variaron; revisar concurrencia antes de afirmar preservación.')
            print(json.dumps({'mode': 'apply' if args.apply else 'preflight', 'initial': initial,
                              'current': state(conn), 'old_tables_checked': len(before),
                              'existing_counts_preserved': preserved, 'outbound_messages': 0,
                              'note': 'Conteos/metadatos, no verificación fila por fila.'}))
    except Exception as error:
        print(json.dumps({'success': False, 'error_type': type(error).__name__,
                          'message': 'No se confirmó la operación. No se muestran credenciales ni SQL.'}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
