"""HU13 en PostgreSQL local descartable: atomicidad, RLS y concurrencia reales."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.db.escalados import SqlAlchemyEscalatedClaimsRepository
from app.schemas.reclamos import AgentClassificationResult
from app.services.escalated_claims_service import (
    ManualClassificationConflictError, ManualClassificationPermissionError, ManualDecisionContext,
)
from app.services.classification_service import ClaimClassificationConflictError
from tests.test_responsible_actor_postgres import (
    MIGRATIONS, claim_case, classification, local_engine, snapshot,
)
from scripts.check_escalados_postgres import apply, installed_objects, verify


pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Requiere PostgreSQL local dedicado.")


@pytest.fixture
def escalated_case(claim_case):
    db, repo, claim_id = claim_case
    with db.connect() as connection:
        cursor = connection.connection.cursor()
        try:
            cursor.execute((MIGRATIONS / "26_resolucion_escalados.sql").read_text(encoding="utf-8"))
            connection.commit()
        finally:
            cursor.close()
    with db.begin() as connection:
        operator_id = connection.execute(text("""
            UPDATE usuarios SET primer_ingreso = false WHERE rol = 'operador' RETURNING id
        """)).scalar_one()
    result = AgentClassificationResult(
        tipo_gasto=None, confianza=0.55, fundamento="El origen del desperfecto no está confirmado.",
        debe_escalar=True, motivo_escalado="confianza_insuficiente", estado_clasificacion="escalado",
        actor_responsable=None, notificacion_responsable_requerida=False,
    )
    repo.persist_classification(claim_id, result)
    detail_repo = SqlAlchemyEscalatedClaimsRepository(repo.session_factory)
    detail = detail_repo.get(claim_id)
    decision = ManualDecisionContext(operator_id, "operador", detail.updated_at)
    return db, repo, detail_repo, claim_id, decision


def human_result(expense):
    value = classification(expense)
    return value.model_copy(update={"confianza": None, "fundamento": "La revisión manual confirma el tipo de gasto."})


@pytest.mark.parametrize("expense", ["ordinario", "extraordinario", "expensa"])
def test_manual_decision_preserves_evidence_and_starts_one_responsible_request(escalated_case, expense):
    db, repo, queries, claim_id, decision = escalated_case
    saved = repo.resolve_manual(claim_id, human_result(expense), decision)
    detail = queries.get(claim_id)
    assert saved.response.tipo_gasto == expense
    assert detail.puede_resolver is False and detail.confianza_clasificacion is None
    assert len(detail.decisiones) == 1
    audit = detail.decisiones[0]
    assert audit.usuario_id == decision.user_id and audit.usuario_nombre == "Operador Sintetico"
    assert audit.resultado_anterior["confianza"] == 0.55
    assert audit.resultado_anterior["motivo_escalado"] == "confianza_insuficiente"
    assert detail.historial[-1].origen == "operador"
    data = snapshot(db, claim_id)
    assert data["reclamos"][0]["origen_clasificacion"] == "operador"
    manual_history = [h for h in data["reclamo_historial_estados"] if h["origen"] == "operador"]
    assert len(manual_history) == 1 and manual_history[0]["usuario_id"] == decision.user_id
    assert len(data["reclamo_responsables"]) == 1
    assert len([n for n in data["notificaciones"] if n["tipo_evento"] == "responsable_inicial"]) == 1
    assert queries.list().total == 0
    original = snapshot(db, claim_id)
    with pytest.raises(ManualClassificationConflictError):
        repo.resolve_manual(claim_id, human_result("expensa"), decision)
    assert snapshot(db, claim_id) == original


def test_simultaneous_decisions_allow_exactly_one_winner(escalated_case):
    db, repo, queries, claim_id, decision = escalated_case
    barrier = Barrier(2)
    def resolve(expense):
        barrier.wait(timeout=5)
        try:
            return repo.resolve_manual(claim_id, human_result(expense), decision).response.tipo_gasto
        except ManualClassificationConflictError:
            return None
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(resolve, ["ordinario", "extraordinario"]))
    assert len([value for value in outcomes if value]) == 1
    assert len(queries.get(claim_id).decisiones) == 1
    assert len(snapshot(db, claim_id)["reclamo_responsables"]) == 1


def test_a_stale_version_does_not_write_anything(escalated_case):
    db, repo, _, claim_id, decision = escalated_case
    original = snapshot(db, claim_id)
    stale = ManualDecisionContext(decision.user_id, decision.role, decision.expected_updated_at - timedelta(seconds=1))
    with pytest.raises(ManualClassificationConflictError):
        repo.resolve_manual(claim_id, human_result("ordinario"), stale)
    assert snapshot(db, claim_id) == original


def test_deactivated_account_is_rechecked_inside_the_transaction(escalated_case):
    db, repo, _, claim_id, decision = escalated_case
    with db.begin() as connection:
        connection.execute(text("UPDATE usuarios SET activo = false WHERE id = :id"), {"id": decision.user_id})
    original = snapshot(db, claim_id)
    with pytest.raises(ManualClassificationPermissionError):
        repo.resolve_manual(claim_id, human_result("ordinario"), decision)
    assert snapshot(db, claim_id) == original


def test_failure_after_the_audit_rolls_back_state_history_and_notifications(escalated_case):
    db, repo, queries, claim_id, decision = escalated_case
    original = snapshot(db, claim_id)
    def fail(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO reclamo_responsables" in statement:
            raise RuntimeError("Fallo sintético de persistencia.")
    event.listen(db, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            repo.resolve_manual(claim_id, human_result("ordinario"), decision)
    finally:
        event.remove(db, "before_cursor_execute", fail)
    assert snapshot(db, claim_id) == original
    assert queries.get(claim_id).decisiones == []


def test_queue_notifications_use_real_active_recipient_and_are_not_duplicated(escalated_case):
    db, _, _, claim_id, _ = escalated_case
    with db.begin() as connection:
        notifications = connection.execute(text("""
            SELECT * FROM notificaciones WHERE reclamo_id = :id AND tipo_evento = 'alerta_operador'
        """), {"id": claim_id}).mappings().all()
        assert len(notifications) == 1
        assert notifications[0]["destinatario_contacto"] == "operator@example.com"
        connection.execute(text("UPDATE reclamos SET estado = estado WHERE id = :id"), {"id": claim_id})
        # Cambiar entre estados de la misma cola tampoco es una nueva entrada.
        connection.execute(text("UPDATE reclamos SET estado = 'Clasificación pendiente' WHERE id = :id"), {"id": claim_id})
    assert len([n for n in snapshot(db, claim_id)["notificaciones"] if n["tipo_evento"] == "alerta_operador"]) == 1


def test_queue_pagination_search_and_photo_ownership(escalated_case):
    db, repo, queries, claim_id, _ = escalated_case
    assert queries.list(search="sintética").total == 1
    assert queries.list(search="%" ).total == 0
    assert queries.list(page=2, page_size=1).items == []
    with db.begin() as connection:
        photo_id = connection.execute(text("""
            INSERT INTO reclamo_fotos (reclamo_id, url, formato, tamanio_bytes)
            VALUES (:id, 'synthetic/private/photo.jpg', 'JPG', 10) RETURNING id
        """), {"id": claim_id}).scalar_one()
    assert queries.photo(claim_id, photo_id)["url"] == 'synthetic/private/photo.jpg'
    from app.services.escalated_claims_service import EscalatedClaimNotFoundError
    with pytest.raises(EscalatedClaimNotFoundError):
        queries.photo(uuid4(), photo_id)


def test_audit_table_is_private_under_rls(escalated_case):
    db, *_ = escalated_case
    with db.connect() as connection:
        assert connection.execute(text("""
            SELECT relrowsecurity FROM pg_class
            WHERE oid = 'public.reclamo_decisiones_clasificacion'::regclass
        """)).scalar_one() is True
        for role in ("anon", "authenticated"):
            assert connection.execute(text("""
                SELECT has_table_privilege(:role, 'public.reclamo_decisiones_clasificacion', 'SELECT')
            """), {"role": role}).scalar_one() is False


def test_administrator_can_resolve_a_classification_pending_case(escalated_case):
    db, repo, queries, claim_id, _ = escalated_case
    with db.begin() as connection:
        admin_id = connection.execute(text("""
            INSERT INTO usuarios (email, password_hash, rol, primer_ingreso)
            VALUES ('admin@example.com', 'not-a-credential', 'administrador', false) RETURNING id
        """)).scalar_one()
        connection.execute(text("UPDATE reclamos SET estado = 'Clasificación pendiente' WHERE id = :id"), {"id": claim_id})
    pending = queries.get(claim_id)
    assert pending.puede_resolver
    context = ManualDecisionContext(admin_id, "administrador", pending.updated_at)
    repo.resolve_manual(claim_id, human_result("extraordinario"), context)
    audit = queries.get(claim_id).decisiones[0]
    assert audit.rol == "administrador" and audit.usuario_nombre == "admin@example.com"
    assert audit.resultado_anterior["estado"] == "Clasificación pendiente"


def test_automatic_and_human_decisions_cannot_overwrite_each_other(escalated_case):
    db, repo, queries, claim_id, decision = escalated_case
    barrier = Barrier(2)
    def resolve(manual):
        barrier.wait(timeout=5)
        try:
            if manual:
                repo.resolve_manual(claim_id, human_result("ordinario"), decision)
            else:
                repo.persist_classification(claim_id, classification("extraordinario"))
            return True
        except (ManualClassificationConflictError, ClaimClassificationConflictError):
            return False
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sum(workers.map(resolve, [True, False])) == 1
    data = snapshot(db, claim_id)
    assert len(data["reclamo_responsables"]) == 1
    assert len([n for n in data["notificaciones"] if n["tipo_evento"] == "responsable_inicial"]) == 1
    assert len(queries.get(claim_id).decisiones) in {0, 1}


@pytest.mark.parametrize("operator_active,expected", [(True, 'operator@example.com'), (False, 'admin@example.com')])
def test_queue_recipient_falls_back_without_broadcasting(escalated_case, operator_active, expected):
    db, _, _, claim_id, decision = escalated_case
    with db.begin() as connection:
        connection.execute(text("""
            INSERT INTO usuarios (email, password_hash, rol, primer_ingreso)
            VALUES ('admin@example.com', 'not-a-credential', 'administrador', false)
        """))
        connection.execute(text("UPDATE usuarios SET activo = :active WHERE id = :id"),
                           {"active": operator_active, "id": decision.user_id})
        connection.execute(text("UPDATE reclamos SET estado = 'Recibido' WHERE id = :id"), {"id": claim_id})
        connection.execute(text("UPDATE reclamos SET estado = 'Clasificación pendiente' WHERE id = :id"), {"id": claim_id})
        contacts = connection.execute(text("""
            SELECT destinatario_contacto FROM notificaciones
            WHERE reclamo_id = :id AND estado_reclamo = 'Clasificación pendiente'
                AND tipo_evento = 'alerta_operador'
        """), {"id": claim_id}).scalars().all()
    assert contacts == [expected]


def migration_registry(db):
    with db.begin() as connection:
        connection.execute(text("CREATE SCHEMA supabase_migrations"))
        connection.execute(text("""
            CREATE TABLE supabase_migrations.schema_migrations
                (version text PRIMARY KEY, name text, statements text[])
        """))


def test_application_script_registers_once_and_checks_real_security(claim_case):
    db, _, _ = claim_case
    migration_registry(db)
    apply(db)
    apply(db)
    with db.connect() as connection:
        verify(connection)
        assert connection.execute(text("SELECT count(*) FROM supabase_migrations.schema_migrations")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM reclamo_decisiones_clasificacion")).scalar_one() == 0


def test_application_script_rolls_back_ddl_if_registry_fails(claim_case):
    db, _, _ = claim_case
    migration_registry(db)
    def fail(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO supabase_migrations.schema_migrations" in statement:
            raise RuntimeError("Fallo sintético de registro.")
    event.listen(db, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            apply(db)
    finally:
        event.remove(db, "before_cursor_execute", fail)
    with db.connect() as connection:
        assert not any(installed_objects(connection).values())
