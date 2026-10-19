"""Convivencia real HU16/HU17/HU21 en PostgreSQL local, sin canales externos.

La base HU21 puede desplegarse sin HU17. Esta regresión se habilita al combinar
los PR, sin copiar módulos productivos de una HU dentro de la otra.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from threading import Barrier
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest
from sqlalchemy import text

from app.agents.coordination.state import ResumeRequest
from app.db.coordination import PostgresCoordinationRepository
from scripts.check_coordination_postgres import apply
from tests.test_responsible_actor_postgres import local_engine, claim_case, classification, snapshot

provider_tests = pytest.importorskip(
    "tests.test_provider_choices_postgres", reason="Requiere combinar HU21 con HU16/HU17 reales."
)
choice_base = provider_tests.choice_base
ExpenseDecisionRequest = provider_tests.ExpenseDecisionRequest

pytestmark = pytest.mark.skipif(
    not os.getenv("AARI_TEST_POSTGRES_URL"), reason="PostgreSQL local dedicado."
)


@pytest.fixture
def integrated_case(choice_base):
    case = choice_base
    url = case.db.url

    def connect():
        return psycopg.connect(
            host=url.host, port=url.port, dbname=url.database, user=url.username,
            password=url.password, row_factory=dict_row, prepare_threshold=None,
        )

    with connect() as conn:
        apply(conn)
    with case.db.begin() as conn:
        conn.execute(text("UPDATE usuarios SET primer_ingreso=false WHERE rol='operador'"))
    case.now = datetime.now(timezone.utc)
    case.connect = connect
    case.coordination = PostgresCoordinationRepository(connect, clock=lambda: case.now)
    return case


def authorize_after_71_hours(case):
    case.claims.persist_classification(case.claim, classification("extraordinario"))
    case.actor = case.actors["propietario"]
    case.now -= timedelta(hours=71)
    with case.db.begin() as conn:
        conn.execute(text("""
            UPDATE reclamo_responsables SET solicitado_en=:started,
                recordatorio_programado_en=:started+interval '48 hours',
                respuesta_vence_en=:started+interval '72 hours' WHERE reclamo_id=:claim
        """), {"started": case.now, "claim": case.claim})
    first = case.coordination.resume(case.claim, ResumeRequest(
        evento_id=uuid4(), version_esperada=0,
    ), case.actor)
    assert first.contexto.etapa == "esperando_autorizacion"
    request = ExpenseDecisionRequest(
        request_id=uuid4(), expected_updated_at=case.auth.get(case.claim, case.actor).updated_at,
    )
    case.auth.decide(case.claim, case.actor, request, decision="autorizar")
    detail = case.repo.get(case.claim, case.actor)
    assert detail.puede_elegir
    assert detail.respuesta_vence_en - detail.solicitado_en == timedelta(hours=72)
    case.now = detail.solicitado_en + timedelta(hours=2)
    return detail


def coordination_state(case):
    with case.connect() as conn:
        return {
            "session": conn.execute(
                "SELECT * FROM public.sesiones_agente WHERE reclamo_id=%s", (case.claim,)
            ).fetchall(),
            "checkpoints": conn.execute(
                "SELECT * FROM aari_coordinacion.checkpoints WHERE thread_id=%s ORDER BY checkpoint_id",
                (str(case.claim),),
            ).fetchall(),
            "events": conn.execute(
                "SELECT * FROM aari_coordinacion.eventos WHERE reclamo_id=%s ORDER BY evento_id",
                (case.claim,),
            ).fetchall(),
        }


def test_authorization_opens_72_new_hours_despite_old_coordination_session(integrated_case):
    case = integrated_case
    detail = authorize_after_71_hours(case)
    before, coordination_before = snapshot(case.db, case.claim), coordination_state(case)

    # Reproducción: sesión con 73 h, pero elección nueva con 70 h por delante.
    assert case.coordination.expire_due() == 0
    assert case.coordination.expire_due() == 0
    assert snapshot(case.db, case.claim) == before
    assert coordination_state(case) == coordination_before
    assert case.repo.get(case.claim, case.actor).puede_elegir
    loaded = case.coordination.get(case.claim, case.actor)
    assert loaded.estado_reclamo_actual == "Autorizado"
    assert loaded.requiere_sincronizacion
    assert loaded.ultima_actividad == coordination_before["session"][0]["ultima_actividad"]
    with case.coordination._transaction() as conn:
        domain = case.coordination._domain(case.coordination._claim(conn, case.claim))
    assert domain.vencimiento_especifico == detail.respuesta_vence_en
    assert domain.vencimiento_especifico - case.now == timedelta(hours=70)
    # Una interacción explícita sincroniza; GET/worker no rejuvenecen la sesión.
    resumed = case.coordination.resume(case.claim, ResumeRequest(
        evento_id=uuid4(), version_esperada=loaded.contexto.version,
        intento_id=loaded.contexto.intento_id,
    ), case.actor)
    assert resumed.contexto.etapa == "esperando_eleccion_proveedor"
    assert resumed.contexto.dominio.vencimiento_especifico == detail.respuesta_vence_en


@pytest.mark.parametrize("order", ["coordination_first", "choice_first", "concurrent"])
def test_only_hu17_job_expires_choice_without_duplicate_transition_or_notice(integrated_case, order):
    case = integrated_case
    authorize_after_71_hours(case)
    with case.db.begin() as conn:
        conn.execute(text("""
            UPDATE reclamo_elecciones_proveedor SET solicitado_en=now()-interval '73 hours',
                recordatorio_programado_en=now()-interval '25 hours',
                respuesta_vence_en=now()-interval '1 hour' WHERE reclamo_id=:claim
        """), {"claim": case.claim})
    before = coordination_state(case)
    enqueue = lambda: case.claims.enqueue_due_responsible_followups(limit=20)
    if order == "concurrent":
        barrier = Barrier(2)

        def run(job):
            barrier.wait(timeout=10)
            return job()

        with ThreadPoolExecutor(max_workers=2) as pool:
            generic = pool.submit(run, case.coordination.expire_due)
            specific = pool.submit(run, enqueue)
            assert generic.result(timeout=30) == 0
            assert specific.result(timeout=30) in {0, 1}
    else:
        if order == "coordination_first":
            assert case.coordination.expire_due() == 0
        assert enqueue() == 1
    # Si un lock hizo saltar un candidato, el siguiente ciclo lo recoge.
    enqueue()
    assert case.coordination.expire_due() == 0
    assert enqueue() == 0
    assert coordination_state(case) == before
    assert case.repo.get(case.claim, case.actor).estado == "Pendiente de respuesta - vencido"
    assert not case.repo.get(case.claim, case.actor).puede_elegir
    with case.db.connect() as conn:
        assert conn.execute(text("SELECT estado FROM reclamo_elecciones_proveedor")).scalar_one() == "vencida"
        assert conn.execute(text("""
            SELECT count(*) FROM reclamo_historial_estados WHERE reclamo_id=:claim
              AND estado_nuevo='Pendiente de respuesta - vencido'
        """), {"claim": case.claim}).scalar_one() == 1
        notices = conn.execute(text("""
            SELECT tipo_evento, estado_envio FROM notificaciones WHERE reclamo_id=:claim
              AND (tipo_evento='eleccion_proveedor_vencido' OR clave_idempotencia LIKE 'hu21:%')
        """), {"claim": case.claim}).all()
        assert notices == [("eleccion_proveedor_vencido", "pendiente")]


def test_protected_choice_does_not_fill_general_expiration_batch(integrated_case):
    case = integrated_case
    authorize_after_71_hours(case)
    with case.db.begin() as conn:
        prop = conn.execute(text("""
            INSERT INTO propiedades (direccion, provincia, localidad, tipo, propietario_id)
            SELECT 'Unidad ficticia de prioridad HU17', provincia, localidad, tipo, propietario_id
            FROM propiedades LIMIT 1 RETURNING id
        """)).scalar_one()
        tenant = conn.execute(text("""
            INSERT INTO inquilinos (nombre_completo,dni,email,telefono,propiedad_id)
            VALUES ('Inquilino Ficticio Dos','10000003','second@example.com','00000000',:prop) RETURNING id
        """), {"prop": prop}).scalar_one()
        other = conn.execute(text("""
            INSERT INTO reclamos (descripcion,urgencia,inquilino_id,propiedad_id)
            VALUES ('Reclamo ficticio para el timeout general.','media',:tenant,:prop) RETURNING id
        """), {"tenant": tenant, "prop": prop}).scalar_one()
    case.claims.persist_classification(other, classification("ordinario"))
    with case.db.begin() as conn:
        conn.execute(text("UPDATE reclamos SET estado='Clasificado' WHERE id=:id"), {"id": other})
    other_repo = PostgresCoordinationRepository(case.connect, clock=lambda: case.now-timedelta(hours=72))
    other_repo.resume(other, ResumeRequest(evento_id=uuid4(), version_esperada=0), case.actor)
    assert case.coordination.expire_due(limit=1) == 1
    assert case.coordination.get(other, case.actor).estado_reclamo_actual == "Sesión expirada"
    assert case.repo.get(case.claim, case.actor).puede_elegir
    assert case.coordination.expire_due(limit=1) == 0


@pytest.mark.parametrize("mismatch", ["source", "actor", "claim_state"])
def test_non_current_phase_does_not_disable_general_timeout(integrated_case, mismatch):
    case = integrated_case
    authorize_after_71_hours(case)
    with case.db.begin() as conn:
        sql = {
            "source": "UPDATE reclamo_elecciones_proveedor SET solicitud_responsable_en=solicitud_responsable_en-interval '1 second'",
            "actor": "UPDATE reclamo_elecciones_proveedor SET actor_tipo='inquilino'",
            "claim_state": "UPDATE reclamos SET estado='Clasificado'",
        }[mismatch]
        conn.execute(text(sql + " WHERE " + ("id" if mismatch == "claim_state" else "reclamo_id") + "=:id"),
                     {"id": case.claim})
    assert case.coordination.expire_due() == 1
    assert case.coordination.expire_due() == 0
    assert case.coordination.get(case.claim, case.actor).estado_reclamo_actual == "Sesión expirada"
