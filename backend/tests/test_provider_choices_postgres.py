"""HU17 integrada con HU16 y PostgreSQL local descartable. Sin SMTP/LLM."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.expense_authorizations import SqlAlchemyExpenseAuthorizationsRepository
from app.db.provider_choices import SqlAlchemyProviderChoicesRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.expense_authorizations import ExpenseDecisionRequest
from app.schemas.provider_choices import ProviderChoiceRequest
from app.services.provider_choices_service import ProviderChoiceConflict, ProviderChoiceForbidden, ProviderChoiceNotFound
from tests.test_responsible_actor_postgres import MIGRATIONS, claim_case, classification, local_engine, snapshot

pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="PostgreSQL local dedicado.")


@pytest.fixture
def choice_base(claim_case):
    db, claims, claim = claim_case
    with db.connect() as c:
        cursor = c.connection.cursor()
        try:
            for filename in ("20261015212745_hu16_autorizacion_gasto.sql", "20261018235315_hu17_eleccion_proveedor.sql"):
                cursor.execute((MIGRATIONS / filename).read_text(encoding="utf-8"))
            c.commit()
        finally:
            cursor.close()
    actors = {}
    with db.begin() as c:
        for role, table in (("inquilino", "inquilinos"), ("propietario", "propietarios")):
            user = c.execute(text("INSERT INTO usuarios(email,password_hash,rol,primer_ingreso) "
                                  "VALUES (:email,'not-a-credential',:role,false) RETURNING id"),
                             {"email": f"{role}@example.com", "role": role}).scalar_one()
            profile = c.execute(text(f"UPDATE {table} SET usuario_id=:user RETURNING id"), {"user": user}).scalar_one()
            actors[role] = AuthenticatedUser(id=user, email=f"{role}@example.com", rol=role,
                                             primer_ingreso=False, perfil_id=profile)
    return SimpleNamespace(db=db, claims=claims, claim=claim, actors=actors,
        repo=SqlAlchemyProviderChoicesRepository(sessionmaker(bind=db)),
        auth=SqlAlchemyExpenseAuthorizationsRepository(sessionmaker(bind=db)))


def prepare(case, expense="ordinario", *, authorize=True):
    case.claims.persist_classification(case.claim, classification(expense))
    case.actor = case.actors["inquilino" if expense == "ordinario" else "propietario"]
    if expense == "extraordinario" and authorize:
        request = ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=case.auth.get(case.claim, case.actor).updated_at)
        case.authorization = case.auth.decide(case.claim, case.actor, request, decision="autorizar")
    return case


def body(case, choice="fidelizado"):
    detail = case.repo.get(case.claim, case.actor)
    return ProviderChoiceRequest(request_id=uuid4(), solicitud_id=detail.solicitud_id,
        expected_updated_at=detail.updated_at, tipo_proveedor=choice)


def phase(case):
    with case.db.connect() as c:
        return dict(c.execute(text("SELECT * FROM reclamo_elecciones_proveedor WHERE reclamo_id=:id"), {"id": case.claim}).mappings().one())


@pytest.mark.parametrize("expense", ["ordinario", "extraordinario"])
@pytest.mark.parametrize("choice", ["fidelizado", "propio"])
def test_full_flow_audit_replay_no_external_derivation(choice_base, expense, choice):
    case = prepare(choice_base, expense)
    request = body(case, choice)
    result = case.repo.choose(case.claim, case.actor, request)
    assert result.tipo_proveedor == choice
    assert result.estado == ("Pendiente de asignación" if choice == "fidelizado" else "Pendiente de datos de proveedor propio")
    before, audit = snapshot(case.db, case.claim), phase(case)
    assert case.repo.choose(case.claim, case.actor, request).repetida
    assert snapshot(case.db, case.claim) == before and phase(case) == audit
    assert audit["usuario_id"] == case.actor.id and audit["decidido_en"] is not None
    assert not case.repo.get(case.claim, case.actor).puede_elegir
    assert case.repo.get(case.claim, case.actor).decision.tipo_proveedor == choice
    assert case.claims.enqueue_due_responsible_followups(limit=20) == 0
    with case.db.connect() as c:
        h = c.execute(text("SELECT * FROM reclamo_historial_estados WHERE id=:id"), {"id": audit["historial_estado_id"]}).mappings().one()
        assert h["origen"] == case.actor.rol and h["usuario_id"] == case.actor.id
        notice = c.execute(text("SELECT mensaje FROM notificaciones WHERE historial_estado_id=:id AND destinatario_tipo='inquilino'"),
                           {"id": audit["historial_estado_id"]}).scalar_one()
        if choice == "propio":
            assert "todavía no fue derivado" in notice
        assert c.execute(text("SELECT proveedor_seleccionado_id FROM reclamos WHERE id=:id"), {"id": case.claim}).scalar_one() is None


def test_owner_authorization_automatically_opens_new_stage_and_fresh_deadline(choice_base):
    case = prepare(choice_base, "extraordinario", authorize=False)
    with pytest.raises(ProviderChoiceNotFound):
        case.repo.get(case.claim, case.actor)
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamo_responsables SET solicitado_en=now()-interval '71 hours', "
                       "recordatorio_programado_en=now()-interval '23 hours',respuesta_vence_en=now()+interval '1 hour'"))
    request = ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=case.auth.get(case.claim, case.actor).updated_at)
    result = case.auth.decide(case.claim, case.actor, request, decision="autorizar")
    assert result.siguiente_paso == "eleccion_proveedor"
    assert result.siguiente_url.endswith(f"/{case.claim}/tipo-proveedor")
    detail = case.repo.get(case.claim, case.actor)
    assert detail.puede_elegir and detail.respuesta_vence_en-detail.solicitado_en == timedelta(hours=72)
    assert detail.solicitado_en > phase(case)["solicitud_responsable_en"]+timedelta(hours=70)
    case.repo.choose(case.claim, case.actor, body(case))
    assert case.auth.decide(case.claim, case.actor, request, decision="autorizar").repetida
    assert phase(case)["estado"] == "decidida"


def test_rejected_owner_and_expensa_never_enter_selection(choice_base):
    case = prepare(choice_base, "extraordinario", authorize=False)
    request = ExpenseDecisionRequest(request_id=uuid4(), expected_updated_at=case.auth.get(case.claim, case.actor).updated_at)
    case.auth.decide(case.claim, case.actor, request, decision="rechazar")
    with case.db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_elecciones_proveedor")).scalar_one() == 0


def test_get_is_read_only_and_other_profiles_have_no_access(choice_base):
    case = prepare(choice_base)
    before, audit = snapshot(case.db, case.claim), phase(case)
    assert case.repo.get(case.claim, case.actor).puede_elegir
    for actor in (case.actors["propietario"], case.actor.model_copy(update={"perfil_id": uuid4()})):
        with pytest.raises(ProviderChoiceNotFound):
            case.repo.get(case.claim, actor)
    assert snapshot(case.db, case.claim) == before and phase(case) == audit


@pytest.mark.parametrize("change", ["inactive", "first_login", "tenant_moved", "stale_version", "wrong_phase", "expired", "stage_changed"])
def test_invalid_decision_makes_no_writes(choice_base, change):
    case = prepare(choice_base)
    request = body(case)
    with case.db.begin() as c:
        if change == "inactive":
            c.execute(text("UPDATE usuarios SET activo=false WHERE id=:id"), {"id": case.actor.id})
        elif change == "first_login":
            c.execute(text("UPDATE usuarios SET primer_ingreso=true WHERE id=:id"), {"id": case.actor.id})
        elif change == "tenant_moved":
            c.execute(text("UPDATE inquilinos SET propiedad_id=NULL,estado='sin_propiedad_asignada' WHERE id=:id"), {"id": case.actor.perfil_id})
        elif change == "stage_changed":
            c.execute(text("UPDATE reclamos SET estado='Escalado' WHERE id=:id"), {"id": case.claim})
        elif change == "expired":
            c.execute(text("UPDATE reclamo_elecciones_proveedor SET solicitado_en=now()-interval '73 hours', "
                           "recordatorio_programado_en=now()-interval '25 hours',respuesta_vence_en=now()-interval '1 hour'"))
        elif change == "stale_version":
            request = request.model_copy(update={"expected_updated_at": request.expected_updated_at-timedelta(seconds=1)})
        elif change == "wrong_phase":
            request = request.model_copy(update={"solicitud_id": uuid4()})
    before, audit = snapshot(case.db, case.claim), phase(case)
    with pytest.raises((ProviderChoiceConflict, ProviderChoiceForbidden, ProviderChoiceNotFound)):
        case.repo.choose(case.claim, case.actor, request)
    assert snapshot(case.db, case.claim) == before and phase(case) == audit


def test_concurrent_opposite_choices_commit_exactly_one(choice_base):
    case = prepare(choice_base)
    first, second = body(case), body(case, "propio")
    barrier = Barrier(2)
    def choose(request):
        barrier.wait(timeout=5)
        try:
            return case.repo.choose(case.claim, case.actor, request)
        except ProviderChoiceConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(choose, (first, second)))
    assert len([r for r in results if r is not None]) == 1
    assert phase(case)["estado"] == "decidida"


def test_reused_uuid_cannot_change_choice_or_version(choice_base):
    case = prepare(choice_base)
    request = body(case)
    case.repo.choose(case.claim, case.actor, request)
    for update in ({"tipo_proveedor": "propio"}, {"solicitud_id": uuid4()},
                   {"expected_updated_at": request.expected_updated_at-timedelta(seconds=1)}):
        with pytest.raises(ProviderChoiceConflict):
            case.repo.choose(case.claim, case.actor, request.model_copy(update=update))


@pytest.mark.parametrize("expense", ["ordinario", "extraordinario"])
def test_48h_reminder_72h_timeout_no_legacy_duplicates(choice_base, expense):
    case = prepare(choice_base, expense)
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamo_elecciones_proveedor SET solicitado_en=now()-interval '49 hours', "
                       "recordatorio_programado_en=now()-interval '1 hour',respuesta_vence_en=now()+interval '23 hours'"))
    assert case.claims.enqueue_due_responsible_followups(limit=20) == 1
    assert case.claims.enqueue_due_responsible_followups(limit=20) == 0
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamo_elecciones_proveedor SET solicitado_en=now()-interval '73 hours', "
                       "recordatorio_programado_en=now()-interval '25 hours',respuesta_vence_en=now()-interval '1 hour'"))
    assert case.claims.enqueue_due_responsible_followups(limit=20) == 1
    assert case.claims.enqueue_due_responsible_followups(limit=20) == 0
    claimed = case.claims.claim_due_notifications(limit=50)
    assert all("espera tu elección" not in n.message for n in claimed)
    assert phase(case)["estado"] == "vencida"
    assert case.repo.get(case.claim, case.actor).estado == "Pendiente de respuesta - vencido"
    with case.db.connect() as c:
        events = c.execute(text("SELECT tipo_evento FROM notificaciones WHERE tipo_evento LIKE 'eleccion_%' ORDER BY tipo_evento")).scalars().all()
        assert events == ["eleccion_proveedor_recordatorio", "eleccion_proveedor_vencido"]


def test_schema_private_and_rejects_incomplete_audit(choice_base):
    case = prepare(choice_base)
    with case.db.connect() as c:
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.reclamo_elecciones_proveedor'::regclass")).scalar_one()
        for role in ("anon", "authenticated"):
            assert not c.execute(text("SELECT has_table_privilege(:role,'public.reclamo_elecciones_proveedor','SELECT')"), {"role": role}).scalar_one()
        assert not c.execute(text("SELECT prosecdef FROM pg_proc WHERE oid='public.abrir_eleccion_proveedor()'::regprocedure")).scalar_one()
    with pytest.raises(IntegrityError), case.db.begin() as c:
        c.execute(text("UPDATE reclamo_elecciones_proveedor SET estado='decidida'"))


@pytest.mark.parametrize("expense", ["ordinario", "extraordinario"])
def test_legacy_stage_discovery_is_not_a_get_side_effect_and_keeps_dates(choice_base, expense):
    case = prepare(choice_base, expense)
    original = phase(case)
    with case.db.begin() as c:
        # Simula un caso anterior al despliegue HU17, sólo en la base descartable.
        c.execute(text("DELETE FROM reclamo_elecciones_proveedor"))
    before = snapshot(case.db, case.claim)
    with pytest.raises(ProviderChoiceNotFound):
        case.repo.get(case.claim, case.actor)
    assert snapshot(case.db, case.claim) == before
    assert case.claims.enqueue_due_responsible_followups(limit=20) == 0
    discovered = phase(case)
    if expense == "ordinario":
        assert discovered["solicitado_en"] == original["solicitado_en"]
    else:
        # La auditoría HU16 conserva el instante original; no usar "ahora".
        assert discovered["solicitado_en"] == case.authorization.decidido_en
    assert discovered["respuesta_vence_en"]-discovered["solicitado_en"] == timedelta(hours=72)
    assert case.repo.get(case.claim, case.actor).puede_elegir


def test_graph_failure_rolls_back_every_business_write(choice_base, monkeypatch):
    case = prepare(choice_base)
    request = body(case)
    before, audit = snapshot(case.db, case.claim), phase(case)
    def fail(*args, **kwargs):
        raise RuntimeError("Fallo sintético de enrutamiento")
    monkeypatch.setattr("app.db.provider_choices.provider_choice_graph.invoke", fail)
    with pytest.raises(RuntimeError):
        case.repo.choose(case.claim, case.actor, request)
    assert snapshot(case.db, case.claim) == before and phase(case) == audit


def test_concurrent_reminders_enqueue_once(choice_base):
    case = prepare(choice_base)
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamo_elecciones_proveedor SET solicitado_en=now()-interval '49 hours', "
                       "recordatorio_programado_en=now()-interval '1 hour',respuesta_vence_en=now()+interval '23 hours'"))
    barrier = Barrier(2)
    def tick(_):
        barrier.wait(timeout=5)
        return case.claims.enqueue_due_responsible_followups(limit=20)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(tick, (1, 2))) == 1
    with case.db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM notificaciones WHERE tipo_evento='eleccion_proveedor_recordatorio'")).scalar_one() == 1


def test_expensa_has_no_provider_choice_stage(choice_base):
    case = choice_base
    case.claims.persist_classification(case.claim, classification("expensa"))
    with case.db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_elecciones_proveedor")).scalar_one() == 0
    assert case.claims.enqueue_due_responsible_followups(limit=20) == 0


def test_processed_reminder_is_cancelled_after_choice_and_cannot_be_reactivated(choice_base):
    case = prepare(choice_base)
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamo_elecciones_proveedor SET solicitado_en=now()-interval '49 hours', "
                       "recordatorio_programado_en=now()-interval '1 hour',respuesta_vence_en=now()+interval '23 hours'"))
    case.claims.enqueue_due_responsible_followups(limit=20)
    notices = case.claims.claim_due_notifications(limit=50)
    reminder = next(n for n in notices if "espera tu elección" in n.message)
    case.repo.choose(case.claim, case.actor, body(case))
    assert not case.claims.mark_notification_result(reminder.id, attempt_number=reminder.attempt_number, sent=False, safe_error="Fallo sintético")
    assert all(n.id != reminder.id for n in case.claims.claim_due_notifications(limit=50))
