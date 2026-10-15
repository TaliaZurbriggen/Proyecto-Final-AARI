"""Checkpoints reales, atomicidad y recovery en bases PostgreSQL descartables."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from langgraph.checkpoint.postgres import PostgresSaver
import psycopg
from psycopg.rows import dict_row
import pytest
from sqlalchemy import text

from app.agents.coordination.graph import build_coordination_graph
from app.agents.coordination.state import ResumeRequest
from app.db.coordination import PostgresCoordinationRepository
from app.schemas.auth import AuthenticatedUser
from app.services.coordination_service import CoordinationError
from scripts.check_coordination_postgres import apply, installation_state, verify
from tests.test_responsible_actor_postgres import (
    local_engine, claim_case, classification, snapshot,
)
import os
import subprocess
import sys


pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"),
                              reason="Requiere PostgreSQL local dedicado.")


@pytest.fixture
def coordination_case(claim_case):
    db, claims, claim_id = claim_case
    url = db.url
    def connect():
        return psycopg.connect(host=url.host,port=url.port,dbname=url.database,
            user=url.username,password=url.password,row_factory=dict_row,prepare_threshold=None)
    with connect() as conn:
        apply(conn)
        verify(conn)
    with db.begin() as conn:
        operator = conn.execute(text("""UPDATE usuarios SET primer_ingreso=false
            WHERE rol='operador' RETURNING id""")).scalar_one()
    claims.persist_classification(claim_id,classification("ordinario"))
    # Evitar el vencimiento específico HU12 para probar el timeout general HU21.
    with db.begin() as conn:
        conn.execute(text("UPDATE reclamos SET estado='Autorizado' WHERE id=:id"),{"id":claim_id})
    user = AuthenticatedUser(id=operator,email="operator@example.com",rol="operador",primer_ingreso=False)
    now = datetime.now(timezone.utc)
    repo = PostgresCoordinationRepository(connect,clock=lambda:now)
    return db, repo, claim_id, user, connect, now


def initial(repo,claim_id,user):
    return repo.resume(claim_id,ResumeRequest(evento_id=uuid4(),version_esperada=0),user)


def resume(repo,claim_id,user,response,**kwargs):
    return repo.resume(claim_id,ResumeRequest(
        evento_id=kwargs.get("event_id",uuid4()),
        version_esperada=response.contexto.version,intento_id=response.contexto.intento_id),user)


def db_state(db,claim_id):
    with db.connect() as conn:
        return {
            "domain": snapshot(db,claim_id),
            "session":conn.execute(text("SELECT * FROM sesiones_agente WHERE reclamo_id=:id"),
                                   {"id":claim_id}).mappings().all(),
            "checkpoint_count":conn.execute(text("SELECT count(*) FROM aari_coordinacion.checkpoints")).scalar_one(),
            "events":conn.execute(text("SELECT * FROM aari_coordinacion.eventos ORDER BY creado_en,evento_id")).mappings().all(),
        }


def test_real_checkpoint_survives_service_recreation(coordination_case):
    db,repo,claim_id,user,connect,now = coordination_case
    first = initial(repo,claim_id,user)
    fresh = PostgresCoordinationRepository(connect,clock=lambda:now)
    loaded = fresh.get(claim_id,user)
    assert loaded.contexto == first.contexto
    second = resume(fresh,claim_id,user,loaded)
    assert second.contexto.version == 2
    with connect() as conn:
        conn.execute("SET LOCAL search_path=aari_coordinacion,pg_catalog")
        state = build_coordination_graph(PostgresSaver(conn)).get_state(
            {"configurable":{"thread_id":str(claim_id)}})
        assert state.values["contexto"] == second.contexto.model_dump(mode="json")
    # Proceso Python independiente: no conserva memoria del grafo ni del servicio.
    url = db.url
    child = subprocess.run([sys.executable,"-c", """
import sys
import psycopg
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver
from app.agents.coordination.graph import build_coordination_graph
with psycopg.connect(host=sys.argv[1],port=int(sys.argv[2]),dbname=sys.argv[3],
                     user=sys.argv[4],row_factory=dict_row) as conn:
    conn.execute('SET LOCAL search_path=aari_coordinacion,pg_catalog')
    value=build_coordination_graph(PostgresSaver(conn)).get_state(
        {'configurable':{'thread_id':sys.argv[5]}}).values['contexto']
    print(value['version'],value['etapa'])
""",str(url.host),str(url.port),str(url.database),str(url.username),str(claim_id)],
        capture_output=True,text=True,timeout=30,check=True)
    assert child.stdout.strip() == "2 esperando_eleccion_proveedor"


def test_get_and_duplicate_do_not_refresh_activity(coordination_case):
    db,repo,claim_id,user,connect,now = coordination_case
    request = ResumeRequest(evento_id=uuid4(),version_esperada=0)
    original = repo.resume(claim_id,request,user)
    before = db_state(db,claim_id)
    late = PostgresCoordinationRepository(connect,clock=lambda:now+timedelta(hours=10))
    assert late.get(claim_id,user).ultima_actividad == original.ultima_actividad
    assert late.resume(claim_id,request,user).duplicado
    assert db_state(db,claim_id) == before


def test_reused_event_id_with_different_input_is_rejected(coordination_case):
    _,repo,claim_id,user,_,_ = coordination_case
    event_id = uuid4()
    first = repo.resume(claim_id,ResumeRequest(evento_id=event_id,version_esperada=0),user)
    with pytest.raises(CoordinationError):
        resume(repo,claim_id,user,first,event_id=event_id)


def test_stale_version_and_attempt_do_not_write(coordination_case):
    db,repo,claim_id,user,_,_ = coordination_case
    first = initial(repo,claim_id,user)
    before = db_state(db,claim_id)
    for version,attempt in [(0,first.contexto.intento_id),(1,uuid4())]:
        with pytest.raises(CoordinationError):
            repo.resume(claim_id,ResumeRequest(evento_id=uuid4(),
                version_esperada=version,intento_id=attempt),user)
        assert db_state(db,claim_id) == before


def test_concurrent_resume_accepts_one_version(coordination_case):
    _,repo,claim_id,user,_,_ = coordination_case
    first = initial(repo,claim_id,user)
    barrier = Barrier(2)
    def run(_):
        barrier.wait(timeout=10)
        try:
            return resume(repo,claim_id,user,first).contexto.version
        except CoordinationError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run,range(2)),key=lambda x:x or 0) == [None,2]


def test_failure_after_checkpoint_rolls_back_everything(coordination_case):
    db,repo,claim_id,user,connect,_ = coordination_case
    first = initial(repo,claim_id,user)
    with connect() as conn:
        conn.execute("""CREATE FUNCTION aari_coordinacion.fail_session() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic failure'; END $$""")
        conn.execute("""CREATE TRIGGER fail_session BEFORE UPDATE ON public.sesiones_agente
            FOR EACH ROW EXECUTE FUNCTION aari_coordinacion.fail_session()""")
    before = db_state(db,claim_id)
    with pytest.raises(psycopg.Error):
        resume(repo,claim_id,user,first)
    assert db_state(db,claim_id) == before


def test_expiration_updates_domain_checkpoint_and_unique_outbox(coordination_case):
    db,repo,claim_id,user,connect,now = coordination_case
    first = initial(repo,claim_id,user)
    later = PostgresCoordinationRepository(connect,clock=lambda:now+timedelta(hours=72))
    assert later.expire_due() == 1
    assert later.expire_due() == 0
    loaded = later.get(claim_id,user)
    assert loaded.contexto.etapa == "expirada"
    assert loaded.contexto.version == first.contexto.version+1
    data = db_state(db,claim_id)
    assert data["domain"]["reclamos"][0]["estado"] == "Sesión expirada"
    alerts = [n for n in data["domain"]["notificaciones"] if n["clave_idempotencia"]
              and n["clave_idempotencia"].startswith("hu21:")]
    assert len(alerts) == 1
    assert alerts[0]["estado_envio"] == "pendiente"


@pytest.mark.parametrize("state", ["Autorizado", "Clasificado"])
@pytest.mark.parametrize("batch_limit", [1, 20])
@pytest.mark.parametrize("empty_older", [True, False])
def test_expiration_mixed_batch_preserves_empty_legacy_session(
    coordination_case, claim_case, state, batch_limit, empty_older,
):
    db, repo, claim_id, user, connect, now = coordination_case
    _, claims, _ = claim_case
    with db.begin() as conn:
        empty_property = conn.execute(text("""
            INSERT INTO propiedades (direccion, provincia, localidad, tipo, propietario_id)
            SELECT 'Unidad ficticia de lote mixto HU21.',
                   p.provincia, p.localidad, p.tipo, p.propietario_id
            FROM propiedades p JOIN reclamos r ON r.propiedad_id=p.id
            WHERE r.id=:id RETURNING id
        """), {"id": claim_id}).scalar_one()
        empty_tenant = conn.execute(text("""
            INSERT INTO inquilinos
                (nombre_completo, dni, email, telefono, propiedad_id)
            VALUES ('Inquilino Sintetico Dos', '10000003', 'mixed@example.com',
                    '00000000', :property) RETURNING id
        """), {"property": empty_property}).scalar_one()
        empty_claim = conn.execute(text("""
            INSERT INTO reclamos (descripcion, urgencia, inquilino_id, propiedad_id)
            VALUES ('Reclamo ficticio con contexto anterior vacío.',
                    'media', :tenant, :property) RETURNING id
        """), {"tenant": empty_tenant, "property": empty_property}).scalar_one()
    claims.persist_classification(empty_claim, classification("ordinario"))
    with db.begin() as conn:
        conn.execute(text("UPDATE reclamos SET estado=:state WHERE id IN (:valid, :empty)"),
                     {"state": state, "valid": claim_id, "empty": empty_claim})
        # También probar la vacía al final: antes revertía lo ya procesado.
        activity = now - timedelta(days=1) if empty_older else now + timedelta(minutes=30)
        empty_session = conn.execute(text("""
            INSERT INTO sesiones_agente (reclamo_id, ultima_actividad)
            VALUES (:id, :activity) RETURNING *
        """), {"id": empty_claim, "activity": activity}).mappings().one()
    first = initial(repo, claim_id, user)
    empty_domain = snapshot(db, empty_claim)
    later = PostgresCoordinationRepository(connect, clock=lambda: now + timedelta(hours=73))

    assert later.expire_due(limit=batch_limit) == 1
    assert later.expire_due(limit=batch_limit) == 0
    loaded = later.get(claim_id, user)
    assert loaded.contexto.etapa == "expirada"
    assert loaded.contexto.version == first.contexto.version + 1
    assert snapshot(db, empty_claim) == empty_domain
    with db.connect() as conn:
        preserved = conn.execute(text("""
            SELECT * FROM sesiones_agente WHERE reclamo_id=:id
        """), {"id": empty_claim}).mappings().one()
        assert preserved == empty_session
        assert preserved["estado_grafo"] == {} and preserved["version"] == 0
        assert conn.execute(text("""
            SELECT count(*) FROM aari_coordinacion.checkpoints WHERE thread_id=:thread
        """), {"thread": str(empty_claim)}).scalar_one() == 0
        assert conn.execute(text("""
            SELECT count(*) FROM aari_coordinacion.eventos WHERE reclamo_id=:id
        """), {"id": empty_claim}).scalar_one() == 0
    alerts = [item for item in snapshot(db, claim_id)["notificaciones"]
              if (item["clave_idempotencia"] or "").startswith("hu21:")]
    assert len(alerts) == 1 and alerts[0]["estado_envio"] == "pendiente"
    # Se conserva el bootstrap normal: no borrar ni inicializar desde el worker.
    initialized = initial(later, empty_claim, user)
    assert initialized.contexto.version == 1
    assert initialized.contexto.etapa == "esperando_eleccion_proveedor"
    assert later.expire_due(limit=batch_limit) == 0


@pytest.mark.parametrize("state",[
    "Visita programada","Derivado a proveedor externo","Rechazado por propietario",
    "Pendiente de respuesta del responsable","Pendiente de autorización - vencido",
    "Pendiente de respuesta - vencido","Pendiente de asignación","Proveedor seleccionado",
])
def test_general_expiration_does_not_override_other_modules(coordination_case,state):
    db,repo,claim_id,user,connect,now = coordination_case
    initial(repo,claim_id,user)
    with db.begin() as conn:
        conn.execute(text("UPDATE reclamos SET estado=:state WHERE id=:id"),
                     {"id":claim_id,"state":state})
    before = db_state(db,claim_id)
    assert PostgresCoordinationRepository(connect,
        clock=lambda:now+timedelta(days=5)).expire_due() == 0
    assert db_state(db,claim_id) == before
    loaded = repo.get(claim_id,user)
    assert loaded.requiere_sincronizacion
    assert loaded.estado_reclamo_actual == state


def test_outsider_and_inactive_account_cannot_read_or_resume(coordination_case):
    db,repo,claim_id,user,_,_ = coordination_case
    initial(repo,claim_id,user)
    outsider = AuthenticatedUser(id=uuid4(),email="outsider@example.com",
                                rol="propietario",primer_ingreso=False)
    with pytest.raises(CoordinationError) as error:
        repo.get(claim_id,outsider)
    assert error.value.status == 403
    with db.begin() as conn:
        conn.execute(text("UPDATE usuarios SET activo=false WHERE id=:id"),{"id":user.id})
    before = db_state(db,claim_id)
    with pytest.raises(CoordinationError):
        repo.get(claim_id,user)
    assert db_state(db,claim_id) == before


def test_empty_legacy_session_bootstraps_without_erasing_data(coordination_case):
    db,repo,claim_id,user,_,_ = coordination_case
    with db.begin() as conn:
        conn.execute(text("INSERT INTO sesiones_agente(reclamo_id) VALUES (:id)"),{"id":claim_id})
    assert initial(repo,claim_id,user).contexto.version == 1


def test_preflight_is_idempotent_and_detects_missing_history(coordination_case):
    _,_,_,_,connect,_ = coordination_case
    with connect() as conn:
        assert apply(conn) is False
        conn.execute("DELETE FROM supabase_migrations.schema_migrations WHERE version='20261011222710'")
        with pytest.raises(RuntimeError,match="Deriva"):
            installation_state(conn)
        conn.rollback()


def test_private_checkpoint_tables_have_no_client_grants(coordination_case):
    _,_,_,_,connect,_ = coordination_case
    with connect() as conn:
        verify(conn)
        for role in ("anon","authenticated"):
            assert not conn.execute("SELECT has_schema_privilege(%s,'aari_coordinacion','USAGE') AS ok",
                                    (role,)).fetchone()["ok"]


@pytest.mark.parametrize("role",["inquilino","propietario"])
def test_active_participant_can_only_access_linked_claim(coordination_case,role):
    db,repo,claim_id,user,_,_ = coordination_case
    initial(repo,claim_id,user)
    with db.begin() as conn:
        account = conn.execute(text("""INSERT INTO usuarios(
            email,password_hash,rol,primer_ingreso)
            VALUES (:email,'not-a-credential',cast(:role as rol_usuario),false)
            RETURNING id"""),{"email":f"{role}@example.com","role":role}).scalar_one()
        table = {"inquilino":"inquilinos","propietario":"propietarios"}[role]
        # Tabla elegida por constante de prueba, no por una entrada HTTP.
        conn.execute(text(f"UPDATE {table} SET usuario_id=:user_id"),
                     {"user_id":account})
    actor = AuthenticatedUser(id=account,email=f"{role}@example.com",
                              rol=role,primer_ingreso=False)
    assert repo.get(claim_id,actor).contexto.reclamo_id == claim_id
    with db.begin() as conn:
        conn.execute(text(f"UPDATE {table} SET usuario_id=null"))
    with pytest.raises(CoordinationError) as error:
        repo.get(claim_id,actor)
    assert error.value.status == 404


def test_expiration_competing_with_resume_has_one_consistent_outcome(coordination_case):
    db,repo,claim_id,user,connect,now = coordination_case
    first = initial(repo,claim_id,user)
    barrier = Barrier(2)
    def renew():
        barrier.wait(timeout=10)
        try:
            return resume(PostgresCoordinationRepository(connect,
                clock=lambda:now+timedelta(hours=71)),claim_id,user,first)
        except CoordinationError:
            return None
    def expire():
        barrier.wait(timeout=10)
        return PostgresCoordinationRepository(connect,
            clock=lambda:now+timedelta(hours=72)).expire_due()
    with ThreadPoolExecutor(max_workers=2) as pool:
        renewal = pool.submit(renew)
        expiration = pool.submit(expire)
        renewed, expired = renewal.result(), expiration.result()
    assert (renewed is None and expired==1) or (renewed is not None and expired==0)
    loaded = repo.get(claim_id,user)
    assert loaded.contexto.etapa == ("expirada" if expired else "esperando_eleccion_proveedor")
    assert loaded.contexto.version == 2


def test_no_enabled_operator_does_not_enqueue_placeholder_contact(coordination_case):
    db,repo,claim_id,user,connect,now = coordination_case
    initial(repo,claim_id,user)
    with db.begin() as conn:
        conn.execute(text("UPDATE usuarios SET primer_ingreso=true WHERE rol='operador'"))
    before = db_state(db,claim_id)
    later = PostgresCoordinationRepository(connect,clock=lambda:now+timedelta(hours=73))
    assert later.expire_due() == 0
    assert db_state(db,claim_id) == before


def test_expensa_cannot_be_taken_over_by_hu21(coordination_case):
    db,repo,claim_id,user,_,_ = coordination_case
    with db.begin() as conn:
        conn.execute(text("UPDATE reclamos SET tipo_gasto='expensa' WHERE id=:id"),{"id":claim_id})
    before = db_state(db,claim_id)
    with pytest.raises(CoordinationError,match="HU14"):
        initial(repo,claim_id,user)
    assert db_state(db,claim_id) == before


def test_manual_domain_reopening_starts_new_attempt_not_old_callbacks(coordination_case):
    db,repo,claim_id,user,connect,now = coordination_case
    first = initial(repo,claim_id,user)
    later = PostgresCoordinationRepository(connect,clock=lambda:now+timedelta(hours=72))
    assert later.expire_due() == 1
    expired = later.get(claim_id,user)
    with db.begin() as conn:
        # Simula la decisión confirmada de otro módulo, no una acción de HU21.
        conn.execute(text("UPDATE reclamos SET estado='Autorizado' WHERE id=:id"),{"id":claim_id})
    reopened = resume(later,claim_id,user,expired)
    assert reopened.contexto.intento_id != first.contexto.intento_id
    before = db_state(db,claim_id)
    with pytest.raises(CoordinationError):
        resume(later,claim_id,user,expired)
    assert db_state(db,claim_id) == before
