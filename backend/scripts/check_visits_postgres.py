"""HU20/HU23: preflight, ensayo con rollback y aplicación compartida explícita.

Sólo lee DATABASE_URL del archivo indicado. No imprime conexión, SQL, filas,
tokens ni errores del driver; no importa app.main ni activa workers/envíos.
"""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT=Path(__file__).resolve().parents[1]
MIGRATIONS=(
    ('20261029120000','hu20_seleccion_presupuesto','reclamo_selecciones_presupuesto'),
    ('20261101110000','hu23_coordinacion_visitas','aari_visita_coordinaciones'),
    ('20261102103000','hu23_seleccion_auditada',None),
)
VISIT_TABLES=('aari_visita_coordinaciones','aari_visita_opciones','aari_visita_acciones','aari_visita_avisos')


def configure(path):
    value=dotenv_values(path).get('DATABASE_URL','')
    url=make_url(value)
    if (url.get_backend_name()!='postgresql' or not url.host
        or not url.host.endswith(('.supabase.co','.supabase.com'))):
        raise ValueError('Se requiere el Supabase configurado de AARI.')
    return create_engine(url,hide_parameters=True,connect_args={'connect_timeout':10})


def body(version,name):
    sql=(ROOT/'migrations'/f'{version}_{name}.sql').read_text(encoding='utf-8')
    sql,n=re.subn(r'(?im)^\s*BEGIN;\s*$','',sql,count=1)
    sql,m=re.subn(r'(?im)^\s*COMMIT;\s*$','',sql,count=1)
    if n!=1 or m!=1: raise ValueError('Límites de transacción inesperados.')
    return sql


def exists(c,table):
    return bool(c.execute(text('SELECT to_regclass(:name) IS NOT NULL'),{'name':'public.'+table}).scalar_one())


def linked(c):
    return bool(c.execute(text("""SELECT EXISTS(SELECT 1 FROM pg_attribute
        WHERE attrelid=to_regclass('public.aari_visita_coordinaciones')
        AND attname='seleccion_id' AND NOT attisdropped)""")).scalar_one())


def states(c):
    if not c.execute(text("SELECT to_regclass('supabase_migrations.schema_migrations') IS NOT NULL")).scalar_one():
        raise RuntimeError('Falta historial de migraciones.')
    result=[]
    for version,name,table in MIGRATIONS:
        rows=c.execute(text('SELECT version,name FROM supabase_migrations.schema_migrations WHERE version=:v OR name=:n'),
                       {'v':version,'n':name}).all()
        installed=exists(c,table) if table else linked(c)
        if (bool(rows)!=installed or rows and rows!=[(version,name)]):
            raise RuntimeError('Objetos e historial inconsistentes; no se reparan automáticamente.')
        if table=='aari_visita_coordinaciones' and any(exists(c,t)!=installed for t in VISIT_TABLES):
            raise RuntimeError('Instalación parcial HU23.')
        result.append(installed)
    if result!=sorted(result,reverse=True): raise RuntimeError('Dependencias instaladas fuera de orden.')
    return result


def inventory(c):
    # Sólo conteos/estado de secuencias. Nunca guarda ni imprime filas privadas.
    tables=c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
    quote=c.dialect.identifier_preparer.quote
    counts={t:c.execute(text('SELECT count(*) FROM public.'+quote(t))).scalar_one() for t in tables}
    sequences=[tuple(r) for r in c.execute(text("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"))]
    return counts,sequences


def verify(c):
    if states(c)!=[True,True,True]: raise RuntimeError('Faltan migraciones.')
    for table in ('reclamo_selecciones_presupuesto',*VISIT_TABLES,'visitas'):
        row=c.execute(text("""SELECT relrowsecurity,
            has_table_privilege('anon',oid,'SELECT,INSERT,UPDATE,DELETE'),
            has_table_privilege('authenticated',oid,'SELECT,INSERT,UPDATE,DELETE')
            FROM pg_class WHERE oid=to_regclass(:name)"""),{'name':'public.'+table}).one()
        if tuple(row)!=(True,False,False): raise RuntimeError('Revisar RLS y permisos.')
        if c.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=:name"),{'name':table}).scalar_one():
            raise RuntimeError('Políticas públicas no previstas.')
    indexes=('uq_visita_coordinacion_activa','uq_visita_coordinacion_seleccion',
        'idx_visita_coordinacion_seleccion_auditada','uq_hu23_seleccion_reclamo_presupuesto_proveedor')
    for index in indexes:
        if not c.execute(text('SELECT indisvalid AND indisready FROM pg_index WHERE indexrelid=to_regclass(:name)'),{'name':'public.'+index}).scalar_one_or_none():
            raise RuntimeError('Falta índice válido.')
    constraints=c.execute(text("""SELECT conname,convalidated FROM pg_constraint
        WHERE conrelid='public.aari_visita_coordinaciones'::regclass
        AND conname='fk_visita_seleccion_auditada'""")).all()
    if constraints!=[('fk_visita_seleccion_auditada',True)]: raise RuntimeError('Falta FK validada.')


def backup(db,executable,directory):
    directory=directory.resolve()
    if directory!=ROOT/'tmp': raise ValueError('El respaldo privado debe quedar en backend/tmp (ignorado por Git).')
    directory.mkdir(exist_ok=True)
    destination=directory/f'hu23-before-{datetime.now():%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.dump'
    url=db.url
    env=os.environ.copy()
    for key in tuple(env):
        if key.startswith('PG'): env.pop(key)
    env.update(PGHOST=url.host,PGPORT=str(url.port or 5432),PGDATABASE=url.database,
               PGUSER=url.username,PGPASSWORD=url.password or '',PGSSLMODE=url.query.get('sslmode','require'),
               PGCONNECT_TIMEOUT='10')
    with db.connect() as c:
        schemas=c.execute(text("SELECT nspname FROM pg_namespace WHERE nspname IN ('public','supabase_migrations','aari_coordinacion') ORDER BY nspname")).scalars().all()
    args=[str(executable),'--format=custom','--no-owner','--no-acl','--file',str(destination)]
    args.extend('--schema='+schema for schema in schemas)
    result=subprocess.run(args,env=env,capture_output=True,timeout=180,check=False)
    if result.returncode or not destination.exists() or destination.stat().st_size==0:
        raise RuntimeError('El respaldo no terminó; no se aplican migraciones.')
    print('Respaldo privado completado:',destination.name,'(ignorado por Git).')
    return destination


def migrate(db,*,dry_run):
    with db.connect() as c:
        transaction=c.begin()
        try:
            c.execute(text("SET LOCAL lock_timeout='5s'"))
            c.execute(text("SET LOCAL statement_timeout='30s'"))
            c.execute(text("SELECT pg_advisory_xact_lock(hashtext('aari:hu20-hu23:migrations'))"))
            installed=states(c)
            before,sequences=inventory(c)
            for (version,name,_),present in zip(MIGRATIONS,installed):
                if present: continue
                sql=body(version,name)
                cursor=c.connection.cursor()
                try: cursor.execute(sql)
                finally: cursor.close()
                c.execute(text('INSERT INTO supabase_migrations.schema_migrations(version,name,statements) VALUES (:v,:n,:s)'),
                          {'v':version,'n':name,'s':[sql]})
            verify(c)
            after,sequences_after=inventory(c)
            if any(after.get(t)!=count for t,count in before.items()) or sequences_after!=sequences:
                raise RuntimeError('Cambió el inventario previo; se revierte esta operación.')
            if dry_run: transaction.rollback()
            else: transaction.commit()
            print('Ensayo revertido correctamente.' if dry_run else 'Migraciones aplicadas y registradas.')
            print('Tablas previas y secuencias conservadas:',len(before))
        except BaseException:
            transaction.rollback()
            raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--mode',choices=('check','dry-run','apply','test'),default='check')
    parser.add_argument('--pg-dump',type=Path)
    args=parser.parse_args()
    db=None
    try:
        db=configure(args.env_file)
        with db.connect() as c:
            c.execute(text("SET LOCAL statement_timeout='15s'"))
            current=states(c)
            print('Supabase configurado: conexión e historial OK.')
            for (version,_,_),present in zip(MIGRATIONS,current):
                print(version+':','instalada' if present else 'pendiente')
            if all(current): verify(c)
        if args.mode=='dry-run': migrate(db,dry_run=True)
        elif args.mode=='apply':
            if not all(current):
                if not args.pg_dump or not args.pg_dump.is_file(): raise ValueError('Falta pg_dump para respaldo previo.')
                backup(db,args.pg_dump,ROOT/'tmp')
                migrate(db,dry_run=True)
                migrate(db,dry_run=False)
            else: print('Instalación ya verificada; no se repiten migraciones.')
        elif args.mode=='test':
            if not all(current): raise RuntimeError('Falta aplicar el esquema autorizado.')
            os.environ['DATABASE_URL']=db.url.render_as_string(hide_password=False)
            os.environ['PYTHON_DOTENV_DISABLED']='1'
            os.environ['JWT_SECRET']=secrets.token_urlsafe(48)
            os.environ['ENVIRONMENT']='test'
            os.environ['RUN_HU23_SUPABASE_INTEGRATION']='1'
            for flag in ('NOTIFICATION_WORKER_ENABLED','CONTRACT_ANALYSIS_WORKER_ENABLED',
                         'COORDINATION_WORKER_ENABLED','PROVIDER_CANDIDATES_WORKER_ENABLED',
                         'QUOTE_REQUESTS_WORKER_ENABLED','QUOTE_RESPONSES_WORKER_ENABLED',
                         'AARI_QUOTE_WORKER_ENABLED','AARI_VISITS_WORKER_ENABLED'):
                os.environ[flag]='false'
            sys.path.insert(0,str(ROOT))
            from app.db.database import engine as test_engine
            test_engine.hide_parameters=True
            import pytest
            return pytest.main(['-q','-p','no:cacheprovider','--tb=short',
                str(ROOT/'tests'/'test_visits_supabase_integration.py')])
        return 0
    except Exception as error:
        print('Validación HU20/HU23 interrumpida:',type(error).__name__,'; sin exponer conexión, SQL o datos.')
        return 1
    finally:
        if db is not None: db.dispose()


if __name__=='__main__': raise SystemExit(main())
