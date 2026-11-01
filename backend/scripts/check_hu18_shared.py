"""HU18: preflight, DDL autorizado y validación ficticia con rollback.

No inicia FastAPI/workers ni muestra conexiones, huellas o datos personales.
La validación no confirma datos ni consume la secuencia de reclamos.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from scripts.apply_hu21_shared import PROJECT_REF

MIGRATION = Path(__file__).resolve().parents[1] / 'migrations' / '20261029235000_hu18_proveedor_externo.sql'
VERSION = '20261029235000'
NAME = 'hu18_proveedor_externo'
ADDED = {'eleccion_id', 'usuario_id', 'actor_nombre', 'request_id', 'expected_updated_at', 'historial_estado_id'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def target_url(raw):
    url = make_url(raw)
    correct = url.host == f'db.{PROJECT_REF}.supabase.co' or (
        bool(url.host) and url.host.endswith('.pooler.supabase.com')
        and url.username == f'postgres.{PROJECT_REF}')
    require(url.get_backend_name() == 'postgresql' and correct, 'Destino distinto al AARI autorizado.')
    return url


def installation_state(connection):
    columns = set(connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='proveedores_externos'")).scalars())
    require({'id', 'reclamo_id', 'propiedad_id', 'nombre', 'telefono', 'created_at'} <= columns, 'Falta la tabla de contactos existente.')
    require(connection.execute(text("SELECT to_regclass('supabase_migrations.schema_migrations') IS NOT NULL")).scalar_one(), 'Falta el historial esperado.')
    history = connection.execute(text('SELECT name FROM supabase_migrations.schema_migrations WHERE version=:version'), {'version': VERSION}).scalar_one_or_none()
    present = columns & ADDED
    require(present in (set(), ADDED), 'Esquema HU18 parcial; no se repara automáticamente.')
    require(bool(present) == bool(history) and (not history or history == NAME), 'Esquema e historial HU18 no coinciden.')
    for table in ('reclamo_elecciones_proveedor', 'reclamo_autorizaciones', 'aari_rondas_presupuesto', 'aari_solicitudes_presupuesto'):
        require(connection.execute(text('SELECT to_regclass(:name) IS NOT NULL'), {'name': 'public.' + table}).scalar_one(), 'Falta una dependencia de HU18.')
    return bool(present)


def fingerprints(connection):
    names = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
    quote = connection.dialect.identifier_preparer.quote
    result = {}
    for name in names:
        excluded = sorted(ADDED) if name == 'proveedores_externos' else []
        row = '(to_jsonb(t) - CAST(:excluded AS text[]))'
        result[name] = dict(connection.execute(text(f"""SELECT count(*) AS n,
            md5(coalesce(string_agg(md5({row}::text),'' ORDER BY md5({row}::text)),'')) AS digest
            FROM public.{quote(name)} t"""), {'excluded': excluded}).mappings().one())
    return result


def verify(connection):
    require(installation_state(connection), 'HU18 no está aplicada.')
    require(connection.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.proveedores_externos'::regclass")).scalar_one(), 'RLS no habilitado.')
    require(connection.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='proveedores_externos' AND roles && ARRAY['public','anon','authenticated']::name[]")).scalar_one() == 0, 'Hay políticas públicas inesperadas.')
    for role in ('anon', 'authenticated'):
        require(not connection.execute(text("SELECT has_table_privilege(:role,'public.proveedores_externos','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"), {'role': role}).scalar_one(), 'Permisos públicos de tabla inesperados.')
        require(not connection.execute(text("SELECT has_any_column_privilege(:role,'public.proveedores_externos','SELECT,INSERT,UPDATE,REFERENCES')"), {'role': role}).scalar_one(), 'Permisos públicos de columnas inesperados.')
        require(not connection.execute(text("SELECT has_function_privilege(:role,'public.proteger_registro_proveedor_externo()','EXECUTE')"), {'role': role}).scalar_one(), 'Función pública inesperada.')
    require(connection.execute(text("SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relname IN ('uq_externo_eleccion','uq_externo_request','idx_externo_usuario','idx_externo_historial') AND i.indisvalid AND i.indisready")).scalar_one() == 4, 'Índices incompletos.')
    require(connection.execute(text("SELECT count(*) FROM pg_constraint WHERE conrelid='public.proveedores_externos'::regclass AND conname IN ('fk_externo_eleccion','chk_externo_auditoria','proveedores_externos_usuario_id_fkey','proveedores_externos_historial_estado_id_fkey') AND convalidated")).scalar_one() == 4, 'Restricciones incompletas.')
    require(connection.execute(text("SELECT count(*) FROM pg_trigger WHERE tgrelid='public.proveedores_externos'::regclass AND tgname='proteger_registro_proveedor_externo' AND NOT tgisinternal AND tgenabled='O'")).scalar_one() == 1, 'Falta el trigger de auditoría.')
    function = connection.execute(text("SELECT prosecdef,proconfig FROM pg_proc WHERE oid='public.proteger_registro_proveedor_externo()'::regprocedure")).mappings().one()
    require(not function['prosecdef'] and any(item.replace(' ', '').replace('"', '') == 'search_path=' for item in function['proconfig'] or []), 'Función sin aislamiento esperado.')


def apply(connection):
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('AARI-HU18-migration'))"))
    if installation_state(connection):
        verify(connection)
        return False
    before = fingerprints(connection)
    source = MIGRATION.read_text(encoding='utf-8')
    require(source.count('\nBEGIN;') == 1 and source.rstrip().endswith('COMMIT;'), 'Límites SQL inesperados.')
    body = source.replace('\nBEGIN;', '', 1).rstrip().removesuffix('COMMIT;')
    # Sin parámetros DBAPI: el SQL contiene format('%I') de PostgreSQL y no debe
    # interpretarse como placeholders del driver. La transacción sigue afuera.
    cursor = connection.connection.cursor()
    try:
        cursor.execute(body)
    finally:
        cursor.close()
    connection.execute(text('INSERT INTO supabase_migrations.schema_migrations(version,name,statements) VALUES (:version,:name,:statements)'), {'version': VERSION, 'name': NAME, 'statements': [source]})
    verify(connection)
    require(fingerprints(connection) == before, 'Cambió un dato existente; rollback del DDL.')
    return True


def run_cases(connection, passed):
    from app.db.external_providers import SqlAlchemyExternalProvidersRepository
    from app.db.expense_authorizations import SqlAlchemyExpenseAuthorizationsRepository
    from app.db.provider_choices import SqlAlchemyProviderChoicesRepository
    from app.db.reclamos import SqlAlchemyClaimsRepository
    from app.schemas.auth import AuthenticatedUser
    from app.schemas.expense_authorizations import ExpenseDecisionRequest
    from app.schemas.external_providers import ExternalProviderRequest
    from app.schemas.provider_choices import ProviderChoiceRequest
    from app.schemas.reclamos import AgentClassificationResult
    from app.services.external_providers_service import ExternalProviderError

    factory = sessionmaker(bind=connection, join_transaction_mode='create_savepoint')
    execute = lambda statement, **params: connection.execute(text(statement), params)
    external = SqlAlchemyExternalProvidersRepository(factory)
    for expense in ('ordinario', 'extraordinario'):
        tag = uuid4().hex
        owner, tenant, property_id, claim = [uuid4() for _ in range(4)]
        actors = {}
        for role, profile in (('propietario', owner), ('inquilino', tenant), ('administrador', None)):
            uid, email = uuid4(), f'hu18-{tag}-{role}@example.com'
            execute("INSERT INTO usuarios(id,email,password_hash,rol,primer_ingreso) VALUES (:id,:email,'not-a-credential',:role,false)", id=uid, email=email, role=role)
            actors[role] = AuthenticatedUser(id=uid, email=email, rol=role, primer_ingreso=False, perfil_id=profile)
        execute("INSERT INTO propietarios(id,nombre_completo,dni,email,telefono,usuario_id) VALUES (:id,'Titular Ficticio',:dni,:email,'00000000',:user)", id=owner, dni=str(99000000 + uuid4().int % 400000), email=actors['propietario'].email, user=actors['propietario'].id)
        execute("INSERT INTO propiedades(id,direccion,provincia,localidad,tipo,propietario_id) VALUES (:id,:address,'Córdoba',:city,'casa',:owner)", id=property_id, address='Unidad ficticia HU18 ' + tag, city='Localidad ficticia ' + tag, owner=owner)
        execute("INSERT INTO inquilinos(id,nombre_completo,dni,email,telefono,propiedad_id,usuario_id) VALUES (:id,'Inquilino Ficticio',:dni,:email,'00000000',:property,:user)", id=tenant, dni=str(99400000 + uuid4().int % 400000), email=actors['inquilino'].email, property=property_id, user=actors['inquilino'].id)
        # nextval no se revierte: se usa un número explícito sólo en esta transacción.
        execute("INSERT INTO reclamos(id,numero,descripcion,urgencia,inquilino_id,propiedad_id) VALUES (:id,:number,'PRUEBA HU18: texto ficticio, no es un reclamo real.','media',:tenant,:property)", id=claim, number=500_000_000_000 + uuid4().int % 1_000_000_000, tenant=tenant, property=property_id)
        SqlAlchemyClaimsRepository(factory).persist_classification(claim, AgentClassificationResult(tipo_gasto=expense, confianza=0.95, fundamento='Clasificación ficticia HU18.', debe_escalar=False, motivo_escalado=None, estado_clasificacion='clasificado', actor_responsable='inquilino' if expense == 'ordinario' else 'propietario', notificacion_responsable_requerida=True))
        actor = actors['inquilino' if expense == 'ordinario' else 'propietario']
        if expense == 'extraordinario':
            auth = SqlAlchemyExpenseAuthorizationsRepository(factory)
            auth.decide(claim, actor, ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=auth.get(claim, actor).updated_at), decision='autorizar')
        choices = SqlAlchemyProviderChoicesRepository(factory)
        choice = choices.get(claim, actor)
        choices.choose(claim, actor, ProviderChoiceRequest(request_id=uuid4(), solicitud_id=choice.solicitud_id, expected_updated_at=choice.updated_at, tipo_proveedor='propio'))
        detail = external.get(claim, actor)
        payload = ExternalProviderRequest(request_id=uuid4(), eleccion_id=detail.eleccion_id, expected_updated_at=detail.updated_at, nombre='Persona Ficticia', telefono='+54 (11) 5555-0100')
        first = external.register(claim, actor, payload)
        require(first.estado == 'Derivado a proveedor externo' and first.registro.telefono == '541155550100', 'Derivación no confirmada.')
        require(external.register(claim, actor, payload).repetida, 'Reintento no idempotente.')
        require(execute('SELECT count(*) FROM proveedores_externos WHERE reclamo_id=:id', id=claim).scalar_one() == 1, 'Contacto duplicado.')
        require(execute("SELECT count(*) FROM reclamo_historial_estados WHERE reclamo_id=:id AND estado_nuevo='Derivado a proveedor externo'", id=claim).scalar_one() == 1, 'Historial duplicado.')
        require(external.get(claim, actors['administrador']).registros[0].id == first.registro.id, 'Historial administrativo no disponible.')
        try:
            external.register(claim, actors['administrador'], payload)
        except ExternalProviderError as error:
            require(error.status == 403, 'Respuesta inesperada para administrador.')
        else:
            raise RuntimeError('El administrador no debe registrar contactos.')
        passed.append(expense + '_contact_state_replay_history_admin_readonly')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized', action='store_true')
    parser.add_argument('--env-root', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    if not args.authorized:
        parser.error('Requiere autorización humana explícita y --authorized.')
    if sys.flags.optimize:
        parser.error('No ejecutar con -O.')
    engine, stage, passed = None, 'configuration', []
    try:
        values = {}
        for path in (args.env_root / '.env', args.env_root / 'backend' / '.env'):
            if path.is_file():
                values.update(dotenv_values(path))
        url = target_url(values['DATABASE_URL'])
        # Los imports de repositorios de la prueba usan este destino; no .env implícitos.
        os.environ.update(PYTHON_DOTENV_DISABLED='1', DATABASE_URL=values['DATABASE_URL'], AARI_CONVERSATIONS_ENABLED='false')
        engine = create_engine(url, hide_parameters=True, connect_args={'connect_timeout': 10, 'sslmode': 'require'})
        stage = 'migration' if args.apply else 'preflight'
        with engine.begin() as connection:
            connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            connection.execute(text("SET LOCAL lock_timeout='5s'"))
            connection.execute(text("SET LOCAL statement_timeout='30s'"))
            before = fingerprints(connection)
            installed = installation_state(connection)
            applied = apply(connection) if args.apply else False
            if installed or applied:
                verify(connection)
            require(fingerprints(connection) == before, 'Los datos existentes cambiaron.')
        print(json.dumps({'stage': stage, 'confirmed': True, 'installed': installed or applied, 'applied': applied, 'tables_checked': len(before), 'existing_rows_preserved': True}), flush=True)
        if args.validate:
            stage = 'validation'
            with engine.connect() as connection:
                outer = connection.begin()
                baseline = sequence = None
                try:
                    connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
                    connection.execute(text("SET LOCAL statement_timeout='30s'"))
                    connection.execute(text("SET LOCAL lock_timeout='5s'"))
                    verify(connection)
                    baseline = fingerprints(connection)
                    sequence = connection.execute(text('SELECT last_value,is_called FROM public.reclamos_numero_seq')).one()
                    run_cases(connection, passed)
                    require(outer.is_active, 'Se perdió la transacción externa de prueba.')
                finally:
                    outer.rollback()
                    if baseline is not None:
                        require(fingerprints(connection) == baseline, 'Datos no revertidos o cambios concurrentes; revisar.')
                    if sequence is not None:
                        require(connection.execute(text('SELECT last_value,is_called FROM public.reclamos_numero_seq')).one() == sequence, 'La numeración cambió.')
            print(json.dumps({'stage': stage, 'success': True, 'checks': passed, 'all_test_data_rolled_back': True, 'claim_sequence_preserved': True, 'outbound_messages': 0}), flush=True)
    except Exception as error:
        diagnostic = getattr(getattr(error, 'orig', None), 'diag', None)
        print(json.dumps({'stage': stage, 'success': False, 'error_type': type(error).__name__,
            'constraint': getattr(diagnostic, 'constraint_name', None), 'completed_checks': passed}), flush=True)
        raise SystemExit(1) from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    main()
