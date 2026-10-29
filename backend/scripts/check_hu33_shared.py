"""Aplicación/QA autorizados HU33: destino fijo, huellas y rollback de datos ficticios.

No inicia la aplicación, workers, SMTP ni LLM. La migración puede confirmar DDL;
la validación nunca confirma sus datos. No muestra configuración ni filas.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from scripts.apply_hu21_shared import PROJECT_REF


MIGRATION = Path(__file__).resolve().parents[1] / 'migrations' / '20261028210000_hu33_conversaciones.sql'
TABLES = ('aari_conversaciones', 'aari_conversacion_mensajes', 'aari_conversacion_lecturas')


def fingerprints(connection):
    names = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars()
    quote = connection.dialect.identifier_preparer.quote
    result = {}
    for name in names:
        row = connection.execute(text(f'''SELECT count(*) AS n,
            md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' ORDER BY md5(to_jsonb(t)::text)),'')) AS digest
            FROM public.{quote(name)} t''')).mappings().one()
        result[name] = dict(row)
    return result


def verify(connection):
    for table in TABLES:
        assert connection.execute(text('''SELECT c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=:table'''), {'table': table}).scalar_one()
        assert connection.execute(text('''SELECT count(*) FROM pg_policies
            WHERE schemaname='public' AND tablename=:table'''), {'table': table}).scalar_one() == 0
        for role in ('anon', 'authenticated'):
            assert not connection.execute(text("SELECT has_table_privilege(:role,:table,'SELECT,INSERT,UPDATE,DELETE')"),
                {'role': role, 'table': 'public.' + table}).scalar_one()
    columns = set(connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='aari_conversaciones'")).scalars())
    assert {'audiencia', 'participante_usuario_id', 'apertura_request_id', 'cierre_request_id',
            'consultas_abiertas_en', 'consultas_cerradas_en'} <= columns
    assert connection.execute(text("SELECT count(*) FROM pg_trigger WHERE tgname='aari_mensaje_inmutable' AND NOT tgisinternal")).scalar_one() == 1


def apply(connection):
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('AARI-HU33-migration'))"))
    before = fingerprints(connection)
    present = set(TABLES) & before.keys()
    if present:
        assert present == set(TABLES), 'Esquema HU33 parcial: requiere revisión, no reparación automática.'
        verify(connection)
        return False, len(before) - len(TABLES)
    assert {'aari_solicitudes_presupuesto', 'aari_rondas_presupuesto', 'aari_presupuesto_eventos'} <= before.keys()
    source = MIGRATION.read_text(encoding='utf-8')
    assert source.count('\nBEGIN;') == 1 and source.rstrip().endswith('COMMIT;')
    # La transacción externa controla el commit sólo tras verificar datos/permisos.
    body = source.replace('\nBEGIN;', '', 1).rstrip().removesuffix('COMMIT;')
    connection.exec_driver_sql(body)
    verify(connection)
    after = fingerprints(connection)
    assert {name: after[name] for name in before} == before, 'Cambió un dato existente: rollback del DDL.'
    assert set(after) - set(before) == set(TABLES)
    return True, len(before)


def run_cases(connection, passed):
    from app.db.conversations import SqlAlchemyConversations
    from app.db.expense_authorizations import SqlAlchemyExpenseAuthorizationsRepository
    from app.db.provider_choices import SqlAlchemyProviderChoicesRepository
    from app.db.quote_portal import SqlAlchemyQuotePortal
    from app.db.reclamos import SqlAlchemyClaimsRepository
    from app.schemas.auth import AuthenticatedUser
    from app.schemas.conversations import ConversationActionRequest, ConversationMessageRequest
    from app.schemas.expense_authorizations import ExpenseDecisionRequest
    from app.schemas.provider_choices import ProviderChoiceRequest
    from app.schemas.quote_portal import PortalQuoteRequest
    from app.schemas.reclamos import AgentClassificationResult
    from app.services.conversations import ConversationError
    from app.services.quote_portal import QuotePortalError

    factory = sessionmaker(bind=connection, join_transaction_mode='create_savepoint')
    tag = uuid4().hex
    accounts = {}
    def execute(sql, **params):
        return connection.execute(text(sql), params)
    def user(label, role, profile=None):
        uid, email = uuid4(), f'hu33-{tag}-{label}@example.com'
        execute("INSERT INTO usuarios(id,email,password_hash,rol,primer_ingreso,nombre_completo) VALUES (:id,:email,'not-a-credential',:role,false,'Persona ficticia de prueba')", id=uid, email=email, role=role)
        accounts[label] = AuthenticatedUser(id=uid, email=email, rol=role, primer_ingreso=False, perfil_id=profile)
        return uid, email
    owner, tenant, property_id, claim, specialty = [uuid4() for _ in range(5)]
    oid, omail = user('owner', 'propietario', owner)
    tid, tmail = user('tenant', 'inquilino', tenant)
    operator, _ = user('operator', 'operador')
    user('admin', 'administrador')
    execute("INSERT INTO propietarios(id,nombre_completo,dni,email,telefono,usuario_id) VALUES (:id,'Titular ficticio de prueba',:dni,:email,'00000000',:user)", id=owner, dni=str(99000000 + uuid4().int % 400000), email=omail, user=oid)
    city = 'Localidad ficticia ' + tag
    execute("INSERT INTO propiedades(id,direccion,provincia,localidad,tipo,propietario_id) VALUES (:id,:address,'Córdoba',:city,'casa',:owner)", id=property_id, address='Unidad ficticia HU33 ' + tag, city=city, owner=owner)
    execute("INSERT INTO inquilinos(id,nombre_completo,dni,email,telefono,propiedad_id,usuario_id) VALUES (:id,'Inquilino ficticio de prueba',:dni,:email,'00000000',:property,:user)", id=tenant, dni=str(99400000 + uuid4().int % 400000), email=tmail, property=property_id, user=tid)
    execute("INSERT INTO especialidades(id,nombre) VALUES (:id,:name)", id=specialty, name='Especialidad ficticia HU33 ' + tag)
    # Número explícito: nextval de PostgreSQL no se revierte con rollback.
    execute("""INSERT INTO reclamos(id,numero,descripcion,urgencia,inquilino_id,propiedad_id,tipo_id,operador_asignado_id)
        VALUES (:id,:number,'PRUEBA HU33: texto ficticio, no es un reclamo real.','media',:tenant,:property,:specialty,:operator)""",
        id=claim, number=500_000_000_000 + uuid4().int % 1_000_000_000, tenant=tenant, property=property_id, specialty=specialty, operator=operator)
    for n in range(2):
        pid = uuid4()
        uid, email = user(f'provider{n}', 'proveedor', pid)
        execute("INSERT INTO proveedores(id,nombre_razon_social,telefono,email,usuario_id) VALUES (:id,'Proveedor ficticio HU33',:phone,:email,:user)", id=pid, phone='+1555' + str(1000000 + uuid4().int % 8999999), email=email, user=uid)
        execute("INSERT INTO proveedor_especialidades(proveedor_id,especialidad_id) VALUES (:id,:specialty)", id=pid, specialty=specialty)
        execute("INSERT INTO proveedor_coberturas(proveedor_id,provincia,localidad,cubre_toda_localidad) VALUES (:id,'Córdoba',:city,true)", id=pid, city=city)
    claims = SqlAlchemyClaimsRepository(factory)
    claims.persist_classification(claim, AgentClassificationResult(tipo_gasto='extraordinario', confianza=0.95,
        fundamento='Clasificación ficticia HU33.', debe_escalar=False, motivo_escalado=None,
        estado_clasificacion='clasificado', actor_responsable='propietario', notificacion_responsable_requerida=True))
    auth = SqlAlchemyExpenseAuthorizationsRepository(factory)
    auth.decide(claim, accounts['owner'], ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=auth.get(claim, accounts['owner']).updated_at), decision='autorizar')
    choices = SqlAlchemyProviderChoicesRepository(factory)
    detail = choices.get(claim, accounts['owner'])
    choices.choose(claim, accounts['owner'], ProviderChoiceRequest(request_id=uuid4(), solicitud_id=detail.solicitud_id,
        expected_updated_at=detail.updated_at, tipo_proveedor='fidelizado'))
    portal = SqlAlchemyQuotePortal(factory, scope_claim_id=claim)
    assert portal.publish(claim)['publicadas'] == 2
    provider = accounts['provider0']
    rid = portal.list_own(provider)['items'][0]['id']
    chat = SqlAlchemyConversations(factory)
    def action(): return ConversationActionRequest(request_id=uuid4())
    def message(value): return ConversationMessageRequest(request_id=uuid4(), texto=value)
    def denied(call, kind=ConversationError):
        try: call()
        except kind: return
        raise AssertionError('La operación debió ser rechazada.')
    notices = chat.messages(rid, provider)
    responsible = chat.messages(rid, accounts['owner'])
    assert notices['id'] != responsible['id'] and not notices['puede_enviar'] and not responsible['puede_enviar']
    denied(lambda: chat.thread_messages(notices['id'], accounts['owner']))
    denied(lambda: chat.thread_messages(responsible['id'], provider))
    passed.append('individual_agent_notices_and_privacy')
    opening = action()
    qid = chat.open_questions(rid, provider, opening)['id']
    assert chat.open_questions(rid, provider, opening)['id'] == qid
    denied(lambda: chat.thread_messages(qid, accounts['owner']))
    denied(lambda: chat.thread_messages(qid, accounts['provider1']))
    assert not chat.thread_messages(qid, accounts['admin'])['puede_enviar']
    denied(lambda: chat.thread_send(qid, accounts['admin'], message('No debe guardarse.')))
    passed.append('explicit_queries_and_role_isolation')
    quote = PortalQuoteRequest(request_id=uuid4(), monto='10000.50', moneda='ARS', tipo_importe='minimo', descripcion='Trabajo ficticio HU33 con materiales')
    denied(lambda: portal.submit(rid, provider, quote), QuotePortalError)
    passed.append('budget_blocked_while_questions_open')
    payload = message('¿La pérdida está debajo de la pileta?')
    first = chat.thread_send(qid, provider, payload)
    replay = chat.thread_send(qid, provider, payload)
    assert replay['repetido'] and replay['mensaje']['id'] == first['mensaje']['id']
    chat.thread_send(qid, accounts['tenant'], message('Sí, pierde por la unión.'))
    before = execute("SELECT count(*) FROM aari_conversacion_lecturas").scalar_one()
    assert chat.inbox(accounts['tenant'])['no_leidos'] == 2
    assert execute("SELECT count(*) FROM aari_conversacion_lecturas").scalar_one() == before
    assert chat.thread_read(qid, accounts['tenant'], first['mensaje']['numero'])['no_leidos'] == 0
    passed.append('messages_replay_and_unread_cursor')
    closing = action()
    chat.finish_questions(qid, provider, closing)
    assert chat.finish_questions(qid, provider, closing)['repetido']
    denied(lambda: chat.thread_send(qid, accounts['tenant'], message('Ya está cerrado.')))
    denied(lambda: chat.open_questions(rid, provider, action()))
    assert not chat.thread_messages(qid, provider)['puede_enviar']
    assert portal.submit(rid, provider, quote)['presupuesto']['tipo_importe'] == 'minimo'
    assert sum('presentó su presupuesto' in item['texto'] for item in chat.messages(rid, accounts['owner'])['items']) == 1
    passed.append('explicit_finish_and_structured_quote_afterwards')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized', action='store_true')
    parser.add_argument('--env-root', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    if not args.authorized or not (args.apply or args.validate):
        parser.error('Requiere autorización explícita y --apply o --validate.')
    if sys.flags.optimize:
        parser.error('No ejecutar con -O: las verificaciones deben permanecer activas.')
    values = {}
    for path in (args.env_root / '.env', args.env_root / 'backend' / '.env'):
        if path.is_file(): values.update(dotenv_values(path))
    engine, stage, passed = None, 'configuration', []
    try:
        raw = values['DATABASE_URL']
        url = make_url(raw)
        correct = url.host == f'db.{PROJECT_REF}.supabase.co' or (bool(url.host) and url.host.endswith('.pooler.supabase.com') and url.username == f'postgres.{PROJECT_REF}')
        if url.get_backend_name() != 'postgresql' or not correct:
            raise ValueError('Destino distinto del autorizado.')
        os.environ.update(PYTHON_DOTENV_DISABLED='1', DATABASE_URL=raw, AARI_CONVERSATIONS_ENABLED='true', APP_LOGIN_URL='https://aari.example/login')
        engine = create_engine(url, hide_parameters=True, connect_args={'connect_timeout': 10})
        stage = 'migration'
        applied, old_count = False, None
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout='5s'"))
            connection.execute(text("SET LOCAL statement_timeout='30s'"))
            if args.apply: applied, old_count = apply(connection)
            else: verify(connection)
        print(json.dumps({'stage': stage, 'confirmed': True, 'applied': applied, 'existing_tables_preserved': old_count}), flush=True)
        if args.validate:
            stage = 'validation'
            with engine.connect() as connection:
                outer = connection.begin()
                baseline, sequence = None, None
                try:
                    connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
                    connection.execute(text("SET LOCAL statement_timeout='30s'"))
                    connection.execute(text("SET LOCAL lock_timeout='5s'"))
                    baseline = fingerprints(connection)
                    sequence = connection.execute(text('SELECT last_value,is_called FROM public.reclamos_numero_seq')).one()
                    run_cases(connection, passed)
                    assert outer.is_active
                finally:
                    outer.rollback()
                    if baseline is not None:
                        assert fingerprints(connection) == baseline, 'Cambios concurrentes o datos no revertidos: revisar.'
                    if sequence is not None:
                        assert connection.execute(text('SELECT last_value,is_called FROM public.reclamos_numero_seq')).one() == sequence
            print(json.dumps({'stage': stage, 'success': True, 'checks': passed, 'public_tables_unchanged': len(baseline),
                'all_test_data_rolled_back': True, 'claim_sequence_preserved': True, 'outbound_messages': 0}), flush=True)
    except Exception as error:
        diagnostic = getattr(getattr(error, 'orig', None), 'diag', None)
        print(json.dumps({'stage': stage, 'success': False, 'error_type': type(error).__name__,
            'constraint': getattr(diagnostic, 'constraint_name', None), 'completed_checks': passed}), flush=True)
        raise SystemExit(1) from None
    finally:
        if engine is not None: engine.dispose()


if __name__ == '__main__':
    main()
