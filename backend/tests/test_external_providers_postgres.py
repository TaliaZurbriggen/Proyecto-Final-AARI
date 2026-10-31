"""HU18 con PostgreSQL local descartable y módulos reales HU17/19/33. Sin envíos."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.conversations import SqlAlchemyConversations
from app.db.external_providers import SqlAlchemyExternalProvidersRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.conversations import ConversationActionRequest, ConversationMessageRequest
from app.schemas.external_providers import ExternalProviderRequest
from app.services.conversations import ConversationError
from app.services.external_providers_service import ExternalProviderError
from app.services.quote_portal import QuotePortalError
from tests.test_provider_choices_postgres import choice_base
from tests.test_quote_portal_postgres import portal_case, active_provider, budget, eligible, scalar
from tests.test_responsible_actor_postgres import MIGRATIONS, claim_case, local_engine

pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Sólo PostgreSQL local descartable.")
MIGRATION = "20261029235000_hu18_proveedor_externo.sql"


def apply(case, name):
    with case.db.connect() as c:
        cursor = c.connection.cursor()
        try:
            cursor.execute((MIGRATIONS / name).read_text(encoding="utf-8"))
            c.connection.commit()
        finally: cursor.close()


@pytest.fixture
def external_case(portal_case, monkeypatch):
    apply(portal_case, MIGRATION)
    apply(portal_case, "20261028210000_hu33_conversaciones.sql")
    monkeypatch.setenv("AARI_CONVERSATIONS_ENABLED", "true")
    portal_case.external = SqlAlchemyExternalProvidersRepository(sessionmaker(bind=portal_case.db))
    return portal_case


def body(case, **changes):
    detail = case.external.get(case.claim, case.actor)
    return ExternalProviderRequest(request_id=uuid4(), eleccion_id=detail.eleccion_id,
        expected_updated_at=detail.updated_at, nombre="Persona Sintética", telefono="+54 (11) 5555-0100", **changes)


def agency(case):
    with case.db.begin() as c:
        uid = c.execute(text("INSERT INTO usuarios(email,password_hash,rol,primer_ingreso) VALUES ('admin-external@example.com','unused','administrador',false) RETURNING id")).scalar_one()
    return AuthenticatedUser(id=uid, email="admin-external@example.com", rol="administrador", primer_ingreso=False)


@pytest.mark.parametrize("expense", ["ordinario", "extraordinario"])
def test_own_contact_derivation_audit_replay_and_private_history(external_case, expense):
    case = eligible(external_case, expense, choice="propio")
    data = body(case)
    before = scalar(case, "SELECT count(*) FROM proveedores")
    first = case.external.register(case.claim, case.actor, data)
    assert first.estado == "Derivado a proveedor externo" and first.registro.telefono == "541155550100"
    assert case.external.register(case.claim, case.actor, data).repetida
    assert scalar(case, "SELECT count(*) FROM proveedores_externos") == 1
    assert scalar(case, "SELECT count(*) FROM proveedores") == before
    assert scalar(case, "SELECT count(*) FROM reclamo_historial_estados WHERE estado_nuevo='Derivado a proveedor externo'") == 1
    assert scalar(case, "SELECT usuario_id FROM proveedores_externos") == case.actor.id
    assert not case.external.get(case.claim, case.actor).puede_registrar
    assert case.external.get(case.claim, agency(case)).registros[0].id == first.registro.id
    assert case.repo.get(case.claim, case.actor).decision.tipo_proveedor == "propio"
    with pytest.raises(ExternalProviderError): case.external.register(case.claim, case.actor, body(case))


@pytest.mark.parametrize("change", ["inactive", "first_login", "moved", "different_user", "other_profile", "stale", "other_choice", "closed"])
def test_revalidates_identity_stage_and_version_without_writes(external_case, change):
    case = eligible(external_case, choice="propio")
    data = body(case)
    with case.db.begin() as c:
        if change == "inactive": c.execute(text("UPDATE usuarios SET activo=false WHERE id=:id"), {"id":case.actor.id})
        elif change == "first_login": c.execute(text("UPDATE usuarios SET primer_ingreso=true WHERE id=:id"), {"id":case.actor.id})
        elif change == "moved": c.execute(text("UPDATE inquilinos SET propiedad_id=NULL,estado='sin_propiedad_asignada'"))
        elif change == "different_user": case.actor = case.actor.model_copy(update={"id": uuid4()})
        elif change == "other_profile": case.actor = case.actor.model_copy(update={"perfil_id": uuid4()})
        elif change == "stale": data = data.model_copy(update={"expected_updated_at":data.expected_updated_at - timedelta(seconds=1)})
        elif change == "other_choice": data = data.model_copy(update={"eleccion_id":uuid4()})
        elif change == "closed": c.execute(text("UPDATE reclamos SET estado='Resuelto'"))
    with pytest.raises(ExternalProviderError): case.external.register(case.claim, case.actor, data)
    assert scalar(case, "SELECT count(*) FROM proveedores_externos") == 0
    assert scalar(case, "SELECT count(*) FROM reclamo_historial_estados WHERE estado_nuevo='Derivado a proveedor externo'") == 0


def test_confirmed_choice_deadline_is_not_reused_for_contact_entry(external_case):
    case = eligible(external_case, choice="propio")
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamo_elecciones_proveedor SET solicitado_en=now()-interval '100 hours',recordatorio_programado_en=now()-interval '52 hours',respuesta_vence_en=now()-interval '28 hours',decidido_en=now()-interval '99 hours'"))
    assert case.external.register(case.claim, case.actor, body(case)).estado == "Derivado a proveedor externo"


def test_quote_alternative_cancels_requests_and_mail_without_erasing_quotes_or_messages(external_case):
    case = eligible(external_case)
    first, second = active_provider(case), active_provider(case, 1)
    case.portal.publish(case.claim)
    first_id = case.portal.list_own(first)["items"][0]["id"]
    second_id = case.portal.list_own(second)["items"][0]["id"]
    chat = SqlAlchemyConversations(sessionmaker(bind=case.db))
    technical = chat.open_questions(second_id, second, ConversationActionRequest(request_id=uuid4()))["id"]
    chat.thread_send(technical, second, ConversationMessageRequest(request_id=uuid4(), texto="¿Dónde está la pérdida?"))
    case.portal.submit(first_id, first, budget())
    messages = scalar(case, "SELECT count(*) FROM aari_conversacion_mensajes")
    assert case.external.get(case.claim, case.actor).puede_registrar
    case.external.register(case.claim, case.actor, body(case))
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 1
    assert scalar(case, "SELECT estado FROM aari_rondas_presupuesto") == "cancelada"
    assert scalar(case, "SELECT count(*) FROM aari_conversacion_mensajes") >= messages
    assert scalar(case, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE 'aari-quote:%' AND estado_envio IN ('pendiente','procesando')") == 0
    assert not chat.thread_messages(technical, second)["puede_enviar"]
    with pytest.raises(ConversationError): chat.thread_send(technical, second, ConversationMessageRequest(request_id=uuid4(),texto="Mensaje tardío"))
    with pytest.raises(QuotePortalError): case.portal.submit(second_id, second, budget())
    assert case.repo.get(case.claim, case.actor).decision.tipo_proveedor == "fidelizado"


def test_without_quote_or_with_stale_round_cannot_skip_provider_selection(external_case):
    case = eligible(external_case)
    provider = active_provider(case)
    case.portal.publish(case.claim)
    assert not case.external.get(case.claim, case.actor).puede_registrar
    rid = case.portal.list_own(provider)["items"][0]["id"]
    case.portal.submit(rid, provider, budget())
    with case.db.begin() as c: c.execute(text("UPDATE propiedades SET direccion='Otra dirección de prueba'"))
    assert not case.external.get(case.claim, case.actor).puede_registrar
    with pytest.raises(ExternalProviderError): case.external.register(case.claim, case.actor, body(case))


def test_simultaneous_registrations_have_one_winner_and_one_history(external_case):
    case = eligible(external_case, choice="propio")
    first, second = body(case), body(case).model_copy(update={"nombre":"Otra Persona"})
    barrier = Barrier(2)
    def register(data):
        barrier.wait(timeout=5)
        try: return case.external.register(case.claim, case.actor, data)
        except ExternalProviderError: return None
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(register,(first,second)))
    assert sum(value is not None for value in results) == 1
    assert scalar(case, "SELECT count(*) FROM proveedores_externos") == 1
    assert scalar(case, "SELECT count(*) FROM reclamo_historial_estados WHERE estado_nuevo='Derivado a proveedor externo'") == 1


def test_lost_response_uuid_cannot_be_reused_with_other_payload(external_case):
    case = eligible(external_case, choice="propio")
    data = body(case)
    case.external.register(case.claim, case.actor, data)
    with pytest.raises(ExternalProviderError): case.external.register(case.claim, case.actor, data.model_copy(update={"nombre":"Otra Persona"}))
    assert scalar(case, "SELECT nombre FROM proveedores_externos") == "Persona Sintética"


def test_simultaneous_same_uuid_returns_the_original_result(external_case):
    case=eligible(external_case,choice="propio")
    data=body(case)
    barrier=Barrier(2)
    def register(_):
        barrier.wait(timeout=5)
        return case.external.register(case.claim,case.actor,data)
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(register,range(2)))
    assert sorted(result.repetida for result in results)==[False,True]
    assert results[0].registro.id==results[1].registro.id
    assert scalar(case,"SELECT count(*) FROM proveedores_externos")==1


def test_a_new_owner_does_not_inherit_the_previous_owners_contact(external_case):
    case=eligible(external_case,"extraordinario",choice="propio")
    case.external.register(case.claim,case.actor,body(case))
    with case.db.begin() as c:
        uid=c.execute(text("INSERT INTO usuarios(email,password_hash,rol,primer_ingreso) VALUES ('new-owner-external@example.com','unused','propietario',false) RETURNING id")).scalar_one()
        c.execute(text("UPDATE propietarios SET usuario_id=:id"),{'id':uid})
    for user in (case.actor,case.actor.model_copy(update={'id':uid,'email':'new-owner-external@example.com'})):
        with pytest.raises(ExternalProviderError): case.external.get(case.claim,user)
    assert case.external.get(case.claim,agency(case)).registros


def test_selected_quote_cannot_be_replaced_by_this_form(external_case):
    case=eligible(external_case)
    provider=active_provider(case)
    case.portal.publish(case.claim)
    rid=case.portal.list_own(provider)['items'][0]['id']
    case.portal.submit(rid,provider,budget())
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamos SET proveedor_seleccionado_id=:provider,presupuesto_seleccionado_id=(SELECT id FROM presupuestos LIMIT 1),estado='Proveedor seleccionado' WHERE id=:claim"),{'provider':provider.perfil_id,'claim':case.claim})
    assert not case.external.get(case.claim,case.actor).puede_registrar
    with pytest.raises(ExternalProviderError): case.external.register(case.claim,case.actor,body(case))
    assert scalar(case,'SELECT count(*) FROM proveedores_externos')==0


def test_a_late_failure_also_rolls_back_quote_cancellation(external_case,monkeypatch):
    case=eligible(external_case)
    provider=active_provider(case)
    case.portal.publish(case.claim)
    case.portal.submit(case.portal.list_own(provider)['items'][0]['id'],provider,budget())
    data=body(case)
    before=scalar(case,"SELECT count(*) FROM aari_conversacion_mensajes")
    original=case.external._cancel_rounds
    def fail(*args):
        original(*args)
        raise RuntimeError('Fallo sintético posterior a la cancelación')
    monkeypatch.setattr(case.external,'_cancel_rounds',fail)
    with pytest.raises(RuntimeError): case.external.register(case.claim,case.actor,data)
    assert scalar(case,'SELECT count(*) FROM proveedores_externos')==0
    assert scalar(case,'SELECT estado FROM reclamos WHERE id=:id',id=case.claim)=='Pendiente de asignación'
    assert scalar(case,'SELECT estado FROM aari_rondas_presupuesto')=='esperando'
    assert scalar(case,'SELECT count(*) FROM aari_conversacion_mensajes')==before


def test_a_concurrent_quote_cannot_reactivate_the_external_derivation(external_case):
    case=eligible(external_case)
    first,second=active_provider(case),active_provider(case,1)
    case.portal.publish(case.claim)
    case.portal.submit(case.portal.list_own(first)['items'][0]['id'],first,budget())
    rid=case.portal.list_own(second)['items'][0]['id']
    data=body(case)
    barrier=Barrier(2)
    def external():
        barrier.wait(timeout=5)
        return case.external.register(case.claim,case.actor,data)
    def quote():
        barrier.wait(timeout=5)
        try: return case.portal.submit(rid,second,budget())
        except QuotePortalError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        f=pool.submit(external); q=pool.submit(quote)
        assert f.result(timeout=15).estado=='Derivado a proveedor externo'
        result=q.result(timeout=15)
    assert scalar(case,'SELECT count(*) FROM presupuestos')==(2 if result else 1)
    assert scalar(case,'SELECT estado FROM aari_rondas_presupuesto')=='cancelada'
    assert scalar(case,'SELECT count(*) FROM proveedores_externos')==1
    assert not case.portal.get_own(rid,second)['puede_responder']


def test_failure_rolls_back_contact_state_history_and_notifications(external_case):
    case = eligible(external_case, choice="propio")
    data=body(case)
    def fail(_conn,_cursor,statement,*_args):
        if statement.startswith("INSERT INTO proveedores_externos"): raise RuntimeError("Fallo sintético")
    event.listen(case.db,"before_cursor_execute",fail)
    try:
        with pytest.raises(RuntimeError): case.external.register(case.claim,case.actor,data)
    finally: event.remove(case.db,"before_cursor_execute",fail)
    assert scalar(case,"SELECT estado FROM reclamos WHERE id=:id",id=case.claim)=="Pendiente de datos de proveedor propio"
    assert scalar(case,"SELECT count(*) FROM proveedores_externos")==0
    assert scalar(case,"SELECT count(*) FROM reclamo_historial_estados WHERE estado_nuevo='Derivado a proveedor externo'")==0


def test_migration_preserves_legacy_and_enforces_private_immutable_audit(portal_case):
    case = portal_case
    with case.db.begin() as c:
        before = dict(c.execute(text("INSERT INTO proveedores_externos(reclamo_id,propiedad_id,nombre,telefono) SELECT id,propiedad_id,'Contacto Histórico','12345678' FROM reclamos RETURNING *")).mappings().one())
        c.execute(text("GRANT SELECT(nombre) ON proveedores_externos TO anon"))
    apply(case,MIGRATION)
    with case.db.connect() as c:
        after=dict(c.execute(text("SELECT * FROM proveedores_externos")).mappings().one())
        assert {key:after[key] for key in before}==before
        assert after['usuario_id'] is None and after['eleccion_id'] is None
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='proveedores_externos'::regclass")).scalar_one()
        for role in ('anon','authenticated'):
            assert not c.execute(text("SELECT has_any_column_privilege(:role,'proveedores_externos','SELECT')"),{'role':role}).scalar_one()
    case.external=SqlAlchemyExternalProvidersRepository(sessionmaker(bind=case.db))
    eligible(case,choice="propio")
    saved=case.external.register(case.claim,case.actor,body(case))
    with pytest.raises(DBAPIError),case.db.begin() as c: c.execute(text("UPDATE proveedores_externos SET nombre='Otro Contacto' WHERE id=:id"),{'id':saved.registro.id})
    with pytest.raises(DBAPIError),case.db.begin() as c: c.execute(text("DELETE FROM proveedores_externos WHERE id=:id"),{'id':saved.registro.id})
    with pytest.raises(DBAPIError),case.db.begin() as c:
        c.execute(text("INSERT INTO proveedores_externos(reclamo_id,propiedad_id,nombre,telefono) SELECT id,propiedad_id,'Contacto Sin Auditoría','12345678' FROM reclamos"))
    assert len(case.external.get(case.claim,agency(case)).registros)==2
