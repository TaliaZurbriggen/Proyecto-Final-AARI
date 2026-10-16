"""HU16 contra PostgreSQL local descartable; ninguna llamada externa."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker

from app.db.admin_home import SqlAlchemyAdminHomeRepository
from app.db.expense_authorizations import SqlAlchemyExpenseAuthorizationsRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.expense_authorizations import ExpenseDecisionRequest
from app.services.expense_authorizations_service import (
    ExpenseAuthorizationConflict, ExpenseAuthorizationForbidden, ExpenseAuthorizationNotFound,
)
from tests.test_responsible_actor_postgres import (
    MIGRATIONS, claim_case, classification, local_engine, make_due, snapshot,
)

pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="PostgreSQL local dedicado.")


@pytest.fixture
def ready(claim_case):
    db, claims, claim = claim_case
    with db.connect() as connection:
        cursor = connection.connection.cursor()
        try:
            cursor.execute((MIGRATIONS / "20261015212745_hu16_autorizacion_gasto.sql").read_text(encoding="utf-8"))
            connection.commit()
        finally:
            cursor.close()
    with db.begin() as c:
        user = c.execute(text("""
            INSERT INTO usuarios (email,password_hash,rol,primer_ingreso)
            VALUES ('owner@example.com','not-a-credential','propietario',false) RETURNING id
        """)).scalar_one()
        owner = c.execute(text("UPDATE propietarios SET usuario_id=:id RETURNING id"), {"id": user}).scalar_one()
    claims.persist_classification(claim, classification("extraordinario"))
    repo = SqlAlchemyExpenseAuthorizationsRepository(sessionmaker(bind=db))
    actor = AuthenticatedUser(id=user, email="owner@example.com", rol="propietario",
                              primer_ingreso=False, perfil_id=owner)
    return db, claims, repo, claim, actor


def request(case):
    _, _, repo, claim, actor = case
    return ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=repo.get(claim, actor).updated_at)


def decide(case, body=None, decision="autorizar"):
    _, _, repo, claim, actor = case
    return repo.decide(claim, actor, body or request(case), decision=decision)


def test_read_has_no_writes_and_is_scoped_to_owner(ready):
    db, _, repo, claim, actor = ready
    before = snapshot(db, claim)
    assert repo.list(actor).total == 1
    assert repo.get(claim, actor).puede_decidir
    other = actor.model_copy(update={"perfil_id": uuid4()})
    assert repo.list(other).total == 0
    with pytest.raises(ExpenseAuthorizationNotFound):
        repo.get(claim, other)
    assert before == snapshot(db, claim)


@pytest.mark.parametrize("action", ["autorizar", "rechazar"])
def test_decision_replay_audit_notifications_and_closed_cycle(ready, action):
    db, claims, repo, claim, actor = ready
    body = request(ready)
    result = decide(ready, body, action)
    assert result.decision == action and result.propietario_nombre == "Titular Sintetico"
    before = snapshot(db, claim)
    assert decide(ready, body, action).repetida
    assert snapshot(db, claim) == before
    with pytest.raises(ExpenseAuthorizationConflict):
        decide(ready, body, "rechazar" if action == "autorizar" else "autorizar")
    assert not repo.get(claim, actor).puede_decidir
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_autorizaciones")).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM reclamo_historial_estados WHERE origen='propietario' AND usuario_id=:id"), {"id": actor.id}).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM notificaciones WHERE estado_reclamo=:state AND estado_envio='pendiente'"), {"state": result.estado}).scalar_one() == 2
        ids = c.execute(text("SELECT inquilino_id,propiedad_id FROM reclamos WHERE id=:id"), {"id": claim}).one()
    assert claims.has_active_claim(tenant_id=ids[0], property_id=ids[1]) == (action == "autorizar")
    summary = SqlAlchemyAdminHomeRepository(sessionmaker(bind=db)).get_summary()
    assert summary.reclamos.activos == (1 if action == "autorizar" else 0)
    if action == "rechazar":
        with db.begin() as c:
            c.execute(text("INSERT INTO reclamos(descripcion,urgencia,inquilino_id,propiedad_id) VALUES ('Otro problema sintético','media',:tenant,:property)"), {"tenant": ids[0], "property": ids[1]})


def test_stale_version_and_inactive_owner_make_no_writes(ready):
    db, _, _, claim, actor = ready
    body = request(ready)
    before = snapshot(db, claim)
    with pytest.raises(ExpenseAuthorizationConflict):
        decide(ready, body.model_copy(update={"expected_updated_at": body.expected_updated_at - timedelta(seconds=1)}))
    assert snapshot(db, claim) == before
    with db.begin() as c:
        c.execute(text("UPDATE usuarios SET activo=false WHERE id=:id"), {"id": actor.id})
    with pytest.raises(ExpenseAuthorizationForbidden):
        decide(ready, body)
    assert snapshot(db, claim) == before


def test_concurrent_opposite_decisions_have_one_winner(ready):
    db, _, _, claim, _ = ready
    version = request(ready).expected_updated_at
    start = Barrier(2)
    def run(action):
        start.wait(timeout=5)
        try:
            return decide(ready, ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=version), action).decision
        except ExpenseAuthorizationConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["autorizar", "rechazar"]))
    assert len([r for r in results if r]) == 1
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_autorizaciones")).scalar_one() == 1


def test_failure_after_audit_rolls_everything_back(ready):
    db, _, _, claim, _ = ready
    body = request(ready)
    before = snapshot(db, claim)
    def fail(conn, cursor, statement, parameters, context, many):
        if "INSERT INTO notificaciones" in statement:
            raise RuntimeError("Fallo sintético de outbox")
    event.listen(db, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            decide(ready, body)
    finally:
        event.remove(db, "before_cursor_execute", fail)
    assert snapshot(db, claim) == before
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_autorizaciones")).scalar_one() == 0


def test_reminder_and_timeout_reuse_jobs_and_prevent_late_decision(ready):
    db, claims, repo, claim, actor = ready
    make_due(db, claim, expired=False)
    assert claims.enqueue_due_responsible_followups(limit=10) == 1
    assert claims.enqueue_due_responsible_followups(limit=10) == 0
    body = request(ready)
    make_due(db, claim, expired=True)
    assert not repo.get(claim, actor).puede_decidir
    with pytest.raises(ExpenseAuthorizationConflict):
        decide(ready, body)
    assert claims.enqueue_due_responsible_followups(limit=10) == 1
    assert claims.enqueue_due_responsible_followups(limit=10) == 0
    assert repo.get(claim, actor).estado == "Pendiente de autorización - vencido"


def test_no_followup_after_decision_and_private_audit_table(ready):
    db, claims, _, claim, _ = ready
    decide(ready)
    make_due(db, claim)
    assert claims.enqueue_due_responsible_followups(limit=10) == 0
    with db.connect() as c:
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='reclamo_autorizaciones'::regclass")).scalar_one()
        for role in ('anon', 'authenticated'):
            for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
                assert not c.execute(text("SELECT has_table_privilege(:role,'reclamo_autorizaciones',:privilege)"), {"role":role,"privilege":privilege}).scalar_one()


def test_expired_owner_request_is_not_delivered_by_outbox(ready):
    db, claims, _, claim, _ = ready
    with db.connect() as c:
        initial = c.execute(text("SELECT id FROM notificaciones WHERE reclamo_id=:id AND tipo_evento='responsable_inicial'"), {"id":claim}).scalar_one()
    make_due(db, claim)
    assert claims.claim_notification(initial) is None
    with db.connect() as c:
        assert c.execute(text("SELECT estado_envio FROM notificaciones WHERE id=:id"), {"id":initial}).scalar_one() == 'fallido'


def test_http_flow_uses_real_repository_and_never_sends_email(ready):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.auth import get_current_user
    from app.api.expense_authorizations import get_expense_authorizations_repository
    _, _, repo, claim, actor = ready
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_expense_authorizations_repository] = lambda: repo
    try:
        with TestClient(app) as client:
            listed = client.get('/propietario/reclamos')
            assert listed.status_code == 200 and listed.json()['total'] == 1
            detail = client.get(f'/reclamos/{claim}/autorizacion').json()
            body = {'request_id':str(uuid4()), 'expected_updated_at':detail['updated_at']}
            assert client.post(f'/reclamos/{claim}/autorizar', json=body).status_code == 200
            assert client.post(f'/reclamos/{claim}/autorizar', json=body).json()['repetida']
            after = client.get(f'/reclamos/{claim}/autorizacion').json()
            assert after['estado'] == 'Autorizado' and not after['puede_decidir']
            assert after['decision']['propietario_nombre'] == 'Titular Sintetico'
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_expense_authorizations_repository, None)


def test_same_event_in_parallel_returns_one_original_and_one_replay(ready):
    db, _, _, _, _ = ready
    body = request(ready)
    barrier = Barrier(2)
    def run(_):
        barrier.wait(timeout=5)
        return decide(ready, body).repetida
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == [False, True]
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_autorizaciones")).scalar_one() == 1


def test_smtp_failure_does_not_undo_the_confirmed_decision(ready):
    from app.services.claim_notifications import ClaimNotificationService, ClaimEmailDeliveryError
    db, claims, repo, claim, actor = ready
    decide(ready)
    class FailingSender:
        def send(self, **kwargs):
            raise ClaimEmailDeliveryError('Fallo SMTP sintético')
    service = ClaimNotificationService(claims, FailingSender())
    assert service.deliver_due(limit=10) >= 2
    assert repo.get(claim, actor).estado == 'Autorizado'
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_autorizaciones")).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM notificaciones WHERE estado_reclamo='Autorizado' AND estado_envio='pendiente' AND intentos=1")).scalar_one() == 2
