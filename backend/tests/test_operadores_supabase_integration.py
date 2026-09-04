"""HU7 optativa: PostgreSQL real, SMTP simulado y limpieza verificable.

Requiere RUN_OPERADORES_POSTGRES_TESTS=1 y SUPABASE_TEST_PROJECT_REF explícito.
Los casos funcionales usan rollback en public. La concurrencia usa copias vacías
en un esquema privado único, eliminado al terminar; nunca copia datos reales.
"""

import os
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.access import SqlAlchemyAccessRepository
from app.db.operadores import SqlAlchemyOperadoresRepository
from app.db.usuarios import SqlAlchemyUsuariosRepository
from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.schemas.operadores import OperadorCreate
from app.services.auth_service import AuthService, InactiveAccountError
from app.services.operadores_service import (
    DuplicateOperadorEmailError,
    OperadorAccessConflictError,
    OperadoresService,
    generate_temporary_password,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_OPERADORES_POSTGRES_TESTS") != "1",
    reason="Requiere autorización explícita para Supabase y proyecto de prueba.",
)


def checked_url():
    expected = os.environ.get("SUPABASE_TEST_PROJECT_REF", "")
    assert re.fullmatch(r"[a-z]{20}", expected), "Falta confirmar el proyecto de prueba."
    url = make_url(os.environ["DATABASE_URL"])
    assert url.get_backend_name() == "postgresql", "Se requiere PostgreSQL real."
    assert url.host == f"db.{expected}.supabase.co" or (
        (url.host or "").endswith(".pooler.supabase.com")
        and url.username == f"postgres.{expected}"
    ), "La conexión no corresponde al proyecto autorizado."
    return url


def new_engine(schema="public"):
    engine = create_engine(checked_url(), hide_parameters=True,
                           connect_args={"connect_timeout": 10})

    @event.listens_for(engine, "begin")
    def transaction_settings(connection):
        # schema solo puede ser public o un identificador generado aquí.
        assert schema == "public" or re.fullmatch(r"aari_hu7_test_[0-9a-f]{32}", schema)
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public, extensions')
        connection.exec_driver_sql("SET LOCAL lock_timeout = '8s'")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '15s'")

    return engine


@pytest.fixture
def real_transaction():
    engine = new_engine()
    marker = uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
        repository = SqlAlchemyOperadoresRepository(factory)
        sender = Mock()
        try:
            yield connection, factory, repository, sender, marker
        finally:
            transaction.rollback()
    # El rollback debe eliminar incluso los commits internos del repositorio.
    with engine.connect() as connection:
        assert connection.execute(text("""
            SELECT count(*) FROM public.usuarios WHERE email LIKE :marker
        """), {"marker": f"%{marker}%"}).scalar_one() == 0
    engine.dispose()


def test_real_hash_delivery_retry_login_and_deactivation(real_transaction):
    connection, factory, repository, sender, marker = real_transaction
    service = OperadoresService(repository, sender)
    email = f"hu7-{marker}@example.com"
    sender.send.side_effect = RuntimeError("SMTP simulado")
    created = service.create(OperadorCreate(nombre_completo="María O’Prueba", email=email))
    assert created.acceso.estado == "fallido"
    initial = sender.send.call_args.kwargs["temporary_password"]
    assert connection.execute(text("""
        SELECT password_hash <> :password AND password_hash = crypt(:password, password_hash)
        FROM public.usuarios WHERE id = :id
    """), {"password": initial, "id": str(created.id)}).scalar_one()
    with pytest.raises(DuplicateOperadorEmailError):
        repository.create({"nombre_completo": "Otro Operador", "email": email.upper()},
                          generate_temporary_password())
    sender.send.side_effect = None
    resent = service.retry_access(created.id)
    current = sender.send.call_args.kwargs["temporary_password"]
    assert resent.acceso.estado == "enviado" and resent.acceso.intentos == 2
    assert connection.execute(text("""
        SELECT password_hash <> crypt(:old, password_hash)
            AND password_hash = crypt(:new, password_hash)
        FROM public.usuarios WHERE id = :id
    """), {"old": initial, "new": current, "id": str(created.id)}).scalar_one()
    auth = AuthService(SqlAlchemyUsuariosRepository(factory), SqlAlchemyAccessRepository(factory))
    assert auth.login(LoginRequest(email=email, password=current)).primer_ingreso
    permanent = generate_temporary_password() + generate_temporary_password()
    assert not auth.change_password(created.id, ChangePasswordRequest(
        password_actual=current, password_nueva=permanent,
        confirmacion_password=permanent,
    )).primer_ingreso
    with pytest.raises(OperadorAccessConflictError):
        service.retry_access(created.id)
    assert service.list(page=1, page_size=10, search=marker).total == 1
    assert service.deactivate(created.id).reclamos_liberados == 0
    with pytest.raises(InactiveAccountError):
        auth.get_active_user(created.id)
    with pytest.raises(InactiveAccountError):
        auth.login(LoginRequest(email=email, password=permanent))


def seed_claim_dependencies(connection, marker):
    ids = {key: str(uuid4()) for key in ("owner", "property", "tenant", "specialty")}
    params = {**ids, "owner_email": f"owner-{marker}@example.com",
              "tenant_email": f"tenant-{marker}@example.com",
              "dni": str(10000000 + secrets.randbelow(90000000)),
              "address": f"Calle prueba HU {marker}", "specialty_name": f"Prueba HU {marker}"}
    connection.execute(text("""INSERT INTO public.propietarios
        (id,nombre_completo,dni,email,telefono) VALUES
        (:owner,'Persona Prueba',:dni,:owner_email,'0000000000')"""), params)
    connection.execute(text("""INSERT INTO public.propiedades
        (id,direccion,provincia,localidad,tipo,propietario_id) VALUES
        (:property,:address,'Córdoba','Localidad Prueba','casa',:owner)"""), params)
    connection.execute(text("""INSERT INTO public.inquilinos
        (id,nombre_completo,dni,email,telefono,propiedad_id) VALUES
        (:tenant,'Inquilino Prueba',:dni,:tenant_email,'0000000000',:property)"""), params)
    connection.execute(text("""INSERT INTO public.especialidades(id,nombre)
        VALUES (:specialty,:specialty_name)"""), params)
    return ids


def insert_claim(connection, dependencies, operator, state="Escalado"):
    claim_id = str(uuid4())
    connection.execute(text("""INSERT INTO reclamos
        (id,descripcion,urgencia,tipo_id,inquilino_id,propiedad_id,estado,operador_asignado_id)
        VALUES (:claim,'Reclamo sintético para validar HU siete','baja',:specialty,
                :tenant,:property,:state,:operator)"""),
        {**dependencies, "claim": claim_id, "operator": str(operator), "state": state})
    return claim_id


def test_real_assignment_constraints_and_atomic_release(real_transaction):
    connection, _, repository, _, marker = real_transaction
    created = repository.create({"nombre_completo": "Operador Prueba",
                                 "email": f"hu7-{marker}@example.com"},
                                generate_temporary_password())
    operator = UUID(created["id"])
    dependencies = seed_claim_dependencies(connection, marker)
    pending = insert_claim(connection, dependencies, operator)
    resolved = insert_claim(connection, dependencies, operator, "Resuelto")
    # Una baja dentro de un savepoint puede revertirse con sus liberaciones.
    savepoint = connection.begin_nested()
    assert repository.deactivate(operator) == 1
    savepoint.rollback()
    assert repository.get(operator)["activo"]
    assert connection.execute(text("SELECT operador_asignado_id FROM reclamos WHERE id=:id"),
                              {"id": pending}).scalar_one() == operator
    assert repository.deactivate(operator) == 1
    assert not repository.get(operator)["activo"]
    assert connection.execute(text("SELECT operador_asignado_id FROM reclamos WHERE id=:id"),
                              {"id": pending}).scalar_one() is None
    assert connection.execute(text("SELECT operador_asignado_id FROM reclamos WHERE id=:id"),
                              {"id": resolved}).scalar_one() == operator
    with pytest.raises(IntegrityError) as inactive:
        with connection.begin_nested():
            insert_claim(connection, dependencies, operator)
    assert inactive.value.orig.pgcode == "23514"
    # Un registro histórico permite modificar otros campos sin perder su asignación.
    connection.execute(text("UPDATE reclamos SET urgencia='media' WHERE id=:id"), {"id": resolved})
    with connection.begin_nested():
        admin_id = str(uuid4())
        connection.execute(text("""INSERT INTO usuarios(id,email,password_hash,rol)
            VALUES (:id,:email,crypt(:password,gen_salt('bf')),'administrador')"""),
            {"id": admin_id, "email": f"admin-{marker}@example.com",
             "password": generate_temporary_password()})
        with pytest.raises(IntegrityError) as wrong_role:
            with connection.begin_nested():
                insert_claim(connection, dependencies, admin_id)
        assert wrong_role.value.orig.pgcode == "23514"
    assert repository.deactivate(operator) == 0


def test_real_name_constraint_and_private_api_permissions(real_transaction):
    connection, _, repository, _, marker = real_transaction
    for name in (None, "12345", "A", "Ana  Prueba", "Nombre\\Apellido"):
        with pytest.raises(IntegrityError):
            repository.create({"nombre_completo": name, "email": f"hu7-{marker}@example.com"},
                              generate_temporary_password())
    repository.create({"nombre_completo": "Ana-María Prueba", "email": f"hu7-{marker}@example.com"},
                      generate_temporary_password())
    for table in ("usuarios", "reclamos"):
        for role in ("anon", "authenticated"):
            assert not connection.execute(text("SELECT has_table_privilege(:role,:table,'SELECT,INSERT,UPDATE,DELETE')"),
                                          {"role": role, "table": f"public.{table}"}).scalar_one()
    assert connection.execute(text("""SELECT NOT prosecdef
        AND NOT has_function_privilege('anon',oid,'EXECUTE')
        AND NOT has_function_privilege('authenticated',oid,'EXECUTE')
        FROM pg_proc WHERE oid='public.validar_operador_asignado()'::regprocedure""")).scalar_one()


@pytest.mark.parametrize("previous_state", ["Resuelto", "Reabierto por disconformidad"])
@pytest.mark.parametrize("assignment", ["inactive", "active", "replacement", "unassigned"])
def test_real_reopening_revalidates_operator(real_transaction, previous_state, assignment):
    connection, _, repository, _, marker = real_transaction
    created = repository.create({"nombre_completo": "Operador Histórico",
                                 "email": f"history-{marker}@example.com"},
                                generate_temporary_password())
    operator = UUID(created["id"])
    dependencies = seed_claim_dependencies(connection, marker)
    claim = insert_claim(connection, dependencies, operator, previous_state)
    if assignment != "active":
        assert repository.deactivate(operator) == 0
    # Una edición histórica (incluso SET estado=estado) sigue siendo válida.
    connection.execute(text("UPDATE reclamos SET estado=estado, urgencia='media' WHERE id=:id"),
                       {"id": claim})
    expected = operator
    if assignment == "inactive":
        with pytest.raises(IntegrityError) as failure:
            with connection.begin_nested():
                connection.execute(text("UPDATE reclamos SET estado='Escalado' WHERE id=:id"),
                                   {"id": claim})
        assert failure.value.orig.pgcode == "23514"
        assert connection.execute(text("SELECT estado FROM reclamos WHERE id=:id"),
                                  {"id": claim}).scalar_one() == previous_state
        assert connection.execute(text("""SELECT count(*) FROM reclamo_historial_estados
            WHERE reclamo_id=:id AND estado_nuevo='Escalado'"""), {"id": claim}).scalar_one() == 0
    else:
        if assignment == "replacement":
            replacement = repository.create({"nombre_completo": "Operador Reemplazo",
                                             "email": f"replacement-{marker}@example.com"},
                                            generate_temporary_password())
            expected = UUID(replacement["id"])
        elif assignment == "unassigned":
            expected = None
        if assignment == "active":
            # Solo cambia estado: la asignación no aparece en SET.
            connection.execute(text("UPDATE reclamos SET estado='Escalado' WHERE id=:id"),
                               {"id": claim})
        else:
            connection.execute(text("""UPDATE reclamos
                SET estado='Escalado', operador_asignado_id=:operator WHERE id=:id"""),
                {"id": claim, "operator": str(expected) if expected else None})
        assert connection.execute(text("SELECT estado FROM reclamos WHERE id=:id"),
                                  {"id": claim}).scalar_one() == "Escalado"
        assert connection.execute(text("""SELECT count(*) FROM reclamo_historial_estados
            WHERE reclamo_id=:id AND estado_nuevo='Escalado'"""), {"id": claim}).scalar_one() == 1
    assert connection.execute(text("SELECT operador_asignado_id FROM reclamos WHERE id=:id"),
                              {"id": claim}).scalar_one() == expected


@pytest.fixture(scope="module")
def isolated_concurrency_engine():
    schema = "aari_hu7_test_" + uuid4().hex
    engine = new_engine(schema)
    created = False
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'REVOKE ALL ON SCHEMA "{schema}" FROM PUBLIC, anon, authenticated')
            for table in ("usuarios", "entregas_credenciales", "reclamos"):
                connection.exec_driver_sql(f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING ALL)')
                connection.exec_driver_sql(f'ALTER TABLE "{schema}".{table} ENABLE ROW LEVEL SECURITY')
                connection.exec_driver_sql(f'REVOKE ALL ON "{schema}".{table} FROM PUBLIC, anon, authenticated')
            # Copiar función y trigger instalados, incluidas las columnas de 18.
            # No mantener una réplica manual que pueda ocultar regresiones del DDL.
            definition = connection.execute(text("SELECT pg_get_functiondef('public.validar_operador_asignado()'::regprocedure)")).scalar_one()
            connection.exec_driver_sql(definition.replace("public.", f'"{schema}".'))
            connection.exec_driver_sql(f'REVOKE ALL ON FUNCTION "{schema}".validar_operador_asignado() FROM PUBLIC, anon, authenticated')
            connection.exec_driver_sql(f'''ALTER TABLE "{schema}".reclamos
                ADD FOREIGN KEY (operador_asignado_id) REFERENCES "{schema}".usuarios(id)''')
            trigger_definition = connection.execute(text("""SELECT pg_get_triggerdef(oid)
                FROM pg_trigger WHERE tgrelid='public.reclamos'::regclass
                  AND tgname='trg_validar_operador_asignado' AND NOT tgisinternal""")).scalar_one()
            connection.exec_driver_sql(trigger_definition.replace("public.", f'"{schema}".'))
        created = True
        yield engine
    finally:
        if created:
            # Solo eliminar el esquema exacto generado por esta ejecución.
            assert re.fullmatch(r"aari_hu7_test_[0-9a-f]{32}", schema)
            with engine.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            with engine.connect() as connection:
                assert connection.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname=:schema"),
                                          {"schema": schema}).scalar_one() == 0
        engine.dispose()


def wait_for_blocked_worker(engine, worker_pid):
    deadline = monotonic() + 6
    with engine.connect() as observer:
        while monotonic() < deadline:
            blocked = observer.execute(text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                                       {"pid": worker_pid}).scalar_one()
            if blocked:
                return
            sleep(0.05)
    raise AssertionError("La operación concurrente no esperó el bloqueo de fila.")


@pytest.mark.parametrize("scenario", [
    "retry_after_activation", "assign_after_deactivation", "deactivate_after_assignment",
    "reopen_after_deactivation", "deactivate_after_reopening",
])
def test_real_concurrency_serializes_operator_actions(isolated_concurrency_engine, scenario):
    engine = isolated_concurrency_engine
    repository = SqlAlchemyOperadoresRepository(sessionmaker(bind=engine))
    created = repository.create({"nombre_completo": "Operador Concurrente",
                                 "email": f"hu7-{uuid4().hex}@example.com"},
                                generate_temporary_password())
    operator = UUID(created["id"])
    dependencies = {key: str(uuid4()) for key in ("tenant", "property", "specialty")}
    pids = Queue()
    claim = None
    if scenario in {"reopen_after_deactivation", "deactivate_after_reopening"}:
        with engine.begin() as connection:
            claim = insert_claim(connection, dependencies, operator, "Resuelto")

    def worker():
        with engine.connect() as connection:
            pids.put(connection.execute(text("SELECT pg_backend_pid()")).scalar_one())
            # Mantener esta transacción fija durante la espera (compatible con pooler).
            factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
            worker_repository = SqlAlchemyOperadoresRepository(factory)
            if scenario == "retry_after_activation":
                with pytest.raises(OperadorAccessConflictError):
                    worker_repository.prepare_retry(operator, generate_temporary_password())
                return "rejected"
            if scenario == "assign_after_deactivation":
                with pytest.raises(IntegrityError) as failure:
                    insert_claim(connection, dependencies, operator)
                assert failure.value.orig.pgcode == "23514"
                return "rejected"
            if scenario == "reopen_after_deactivation":
                with pytest.raises(IntegrityError) as failure:
                    connection.execute(text("UPDATE reclamos SET estado='Escalado' WHERE id=:id"),
                                       {"id": claim})
                assert failure.value.orig.pgcode == "23514"
                return "rejected"
            count = worker_repository.deactivate(operator)
            connection.commit()  # Solo confirma datos del esquema temporal.
            return count

    with ThreadPoolExecutor(max_workers=1) as pool:
        with engine.connect() as blocker:
            if scenario == "retry_after_activation":
                blocker.execute(text("UPDATE usuarios SET primer_ingreso=false WHERE id=:id"), {"id": str(operator)})
            elif scenario in {"assign_after_deactivation", "reopen_after_deactivation"}:
                blocker.execute(text("UPDATE usuarios SET activo=false WHERE id=:id"), {"id": str(operator)})
            elif scenario == "deactivate_after_reopening":
                blocker.execute(text("UPDATE reclamos SET estado='Escalado' WHERE id=:id"),
                                {"id": claim})
            else:
                insert_claim(blocker, dependencies, operator)
            future = pool.submit(worker)
            try:
                wait_for_blocked_worker(engine, pids.get(timeout=10))
            finally:
                blocker.commit()  # Libera el bloqueo para que el worker revalide.
        outcome = future.result(timeout=15)
    deactivating = scenario in {"deactivate_after_assignment", "deactivate_after_reopening"}
    assert outcome == (1 if deactivating else "rejected")
    if deactivating:
        assert not repository.get(operator)["activo"]
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM reclamos WHERE operador_asignado_id=:id"),
                                      {"id": str(operator)}).scalar_one() == 0
    if scenario == "reopen_after_deactivation":
        with engine.connect() as connection:
            assert connection.execute(text("SELECT estado FROM reclamos WHERE id=:id"),
                                      {"id": claim}).scalar_one() == "Resuelto"
