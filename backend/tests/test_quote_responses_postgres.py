"""HU19 completo en PostgreSQL local: mensajes sintéticos, sin Meta/SMTP/LLM."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.api.whatsapp import get_whatsapp_inbox, get_whatsapp_settings
from app.db.quote_responses import SqlAlchemyQuoteResponses
from app.db.quote_requests import SqlAlchemyQuoteRequests
from app.db.whatsapp import SqlAlchemyWhatsAppInbox
from app.main import app
from app.services.whatsapp_webhook import parse_events
from tests.test_quote_requests_postgres import (
    begin, choice_base, claim_case, eligible, local_engine, provider, quote_case, requests,
)
from tests.whatsapp_helpers import SETTINGS, body, message, payload, signature
from tests.test_responsible_actor_postgres import MIGRATIONS


pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Sólo PostgreSQL local descartable.")


@pytest.fixture
def response_case(quote_case, request):
    case = eligible(quote_case, expense=getattr(request, "param", "ordinario"))
    provider(case)
    case.quotes.prepare(case.claim)
    job = case.quotes.reserve_one(recipients=("15555550100",))
    assert begin(case, job)
    case.quotes.finish(job, outcome="aceptada", message_id="wamid.synthetic.outbound")
    case.responses = SqlAlchemyQuoteResponses(sessionmaker(bind=case.db), scope_claim_id=case.claim)
    case.inbox = SqlAlchemyWhatsAppInbox(sessionmaker(bind=case.db))
    return case


def inbound(case, content="ARS 12.500,50 Trabajo: reparación de la cañería.", *, external=None, context="wamid.synthetic.outbound", sender="15555550100", changes=None, persist=True):
    event = message(external or "wamid.synthetic.inbound." + uuid4().hex,
                    timestamp=str(int(datetime.now(timezone.utc).timestamp())),
                    text={"body": content}, **{"from": sender})
    if context:
        event["context"] = {"id": context}
    event.update(changes or {})
    raw = body(payload([event]))
    if not persist:
        return None, raw
    case.inbox.save_events(parse_events(raw, SETTINGS))
    with case.db.connect() as c:
        event_id = c.execute(text("SELECT id FROM whatsapp_eventos_entrada WHERE mensaje_externo_id=:id"), {"id": event["id"]}).scalar_one()
    return event_id, raw


def scalar(case, query, params=None):
    with case.db.connect() as c:
        return c.execute(text(query), params or {}).scalar_one()


def expire_round(case):
    # Viajar el reloj del caso completo, sin esperar 24 h ni tocar datos reales.
    with case.db.begin() as c:
        c.execute(text("""UPDATE proveedor_solicitudes_presupuesto SET
            intento_en=CASE WHEN intentos=1 THEN clock_timestamp()-interval '25 hours' ELSE intento_en END,
            aceptado_en=CASE WHEN aceptado_en IS NOT NULL THEN clock_timestamp()-interval '25 hours' ELSE NULL END,
            respuesta_vence_en=CASE WHEN respuesta_vence_en IS NOT NULL THEN clock_timestamp()-interval '1 hour' ELSE NULL END"""))
        c.execute(text("UPDATE reclamo_rondas_presupuesto SET iniciada_en=clock_timestamp()-interval '25 hours',respuesta_vence_en=clock_timestamp()-interval '1 hour'"))


def test_signed_webhook_to_durable_quote_and_one_notification(response_case):
    case = response_case
    _, raw = inbound(case, persist=False)
    app.dependency_overrides[get_whatsapp_settings] = lambda: SETTINGS
    app.dependency_overrides[get_whatsapp_inbox] = lambda: case.inbox
    try:
        with TestClient(app) as client:
            for _ in range(2):
                assert client.post("/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature(raw)}).status_code == 200
    finally:
        app.dependency_overrides.pop(get_whatsapp_settings, None)
        app.dependency_overrides.pop(get_whatsapp_inbox, None)
    assert case.responses.process_pending() == 1
    assert case.responses.process_pending() == 0
    with case.db.connect() as c:
        saved = c.execute(text("SELECT * FROM presupuestos")).mappings().one()
        assert str(saved["monto"]) == "12500.50" and saved["moneda"] == "ARS"
        assert saved["solicitud_presupuesto_id"] == requests(case)[0]["id"]
        assert c.execute(text("SELECT resultado FROM presupuesto_respuestas")).scalar_one() == "aceptada"
        notice = c.execute(text("SELECT * FROM notificaciones WHERE clave_idempotencia LIKE 'hu19:%'")).mappings().one()
        assert notice["destinatario_tipo"] == "inquilino" and notice["estado_envio"] == "pendiente"
        assert c.execute(text("SELECT estado FROM reclamos")).scalar_one() == "Pendiente de asignación"
        assert c.execute(text("SELECT proveedor_seleccionado_id FROM reclamos")).scalar_one() is None


@pytest.mark.parametrize("condition", ["amount", "currency", "conditional", "description", "sender", "context", "nontext", "changed", "references", "no_reference"])
def test_invalid_or_unrelated_responses_never_create_quotes(response_case, condition):
    case = response_case
    kwargs = {}
    if condition in {"amount", "currency", "conditional", "description"}:
        kwargs["content"] = {"amount": "ARS 0 Trabajo: reparación de la cañería.",
            "currency": "$12500 Trabajo: reparación de la cañería.",
            "conditional": "Desde ARS 12500 por reparación de la cañería.", "description": "ARS 12500"}[condition]
    elif condition == "sender":
        kwargs["sender"] = "15555550999"
    elif condition == "context":
        kwargs["context"] = "wamid.unknown"
    elif condition == "nontext":
        kwargs["changes"] = {"type": "audio", "audio": {"id": "synthetic_media"}}
    elif condition == "changed":
        with case.db.begin() as c:
            c.execute(text("UPDATE reclamos SET estado='Resuelto'"))
    elif condition == "references":
        kwargs["content"] = f"Solicitud {uuid4()} ARS 12500 por reparación de la cañería."
    else:
        kwargs["context"] = None
    inbound(case, **kwargs)
    assert case.responses.process_pending() == 1
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 0
    assert scalar(case, "SELECT resultado FROM presupuesto_respuestas") == "revision"


def test_reference_without_reply_context_correlates_only_the_exact_sent_request(response_case):
    case = response_case
    ref = requests(case)[0]["id"]
    inbound(case, f"Solicitud {ref}\nARS 12500 por reparación de la cañería.", context=None)
    case.responses.process_pending()
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 1


def test_different_message_cannot_overwrite_existing_quote(response_case):
    case = response_case
    inbound(case)
    case.responses.process_pending()
    inbound(case, "ARS 99999 Trabajo: reparación diferente de cañería.")
    case.responses.process_pending()
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 1
    assert str(scalar(case, "SELECT monto FROM presupuestos")) == "12500.50"
    assert scalar(case, "SELECT count(*) FROM presupuesto_respuestas") == 2
    assert scalar(case, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :pattern", {"pattern": "hu19:%:disponibles"}) == 1


def test_two_workers_same_event_create_one_quote(response_case):
    case = response_case
    event, _ = inbound(case)
    barrier = Barrier(2)
    def consume(_):
        barrier.wait(timeout=5)
        return case.responses.process_one(event)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume, range(2))) == [False, True]
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 1


def test_notification_failure_rolls_back_quote_and_processing_mark(response_case, monkeypatch):
    case = response_case
    inbound(case)
    notify = case.responses._notify
    monkeypatch.setattr(case.responses, "_notify", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("synthetic failure")))
    with pytest.raises(RuntimeError):
        case.responses.process_pending()
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 0
    assert scalar(case, "SELECT count(*) FROM presupuesto_respuestas") == 0
    monkeypatch.setattr(case.responses, "_notify", notify)
    assert case.responses.process_pending() == 1
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 1


def test_no_quotes_expires_once_changes_state_and_alerts_operator(response_case):
    case = response_case
    assert case.responses.finalize_due() == 0
    expire_round(case)
    assert case.responses.finalize_due() == 1 and case.responses.finalize_due() == 0
    assert scalar(case, "SELECT estado FROM reclamos") == "Sin presupuestos recibidos"
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "sin_presupuestos"
    assert scalar(case, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :pattern", {"pattern": "hu19:%:cierre"}) == 1
    assert scalar(case, "SELECT count(*) FROM reclamo_historial_estados WHERE estado_nuevo='Sin presupuestos recibidos'") == 1


def test_partial_quotes_become_available_without_selecting_provider(response_case):
    case = response_case
    inbound(case)
    case.responses.process_pending()
    expire_round(case)
    assert case.responses.finalize_due() == 1
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "disponibles"
    assert scalar(case, "SELECT estado FROM reclamos") == "Pendiente de asignación"
    assert scalar(case, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :pattern", {"pattern": "hu19:%:disponibles"}) == 1


@pytest.mark.parametrize("condition", ["late", "timestamp", "future"])
def test_late_or_inconsistent_time_never_creates_quote(response_case, condition):
    case = response_case
    if condition == "late":
        expire_round(case)
    kwargs = {"changes": {"timestamp": "1" if condition == "timestamp" else str(int(datetime.now(timezone.utc).timestamp()) + 3600)}} if condition != "late" else {}
    inbound(case, **kwargs)
    case.responses.process_pending()
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 0
    assert scalar(case, "SELECT resultado FROM presupuesto_respuestas") == ("tardia" if condition == "late" else "revision")


def test_delivery_failure_is_not_a_quote_or_provider_silence(response_case):
    case = response_case
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    status = {"id": "wamid.synthetic.outbound", "recipient_id": "15555550100", "timestamp": timestamp, "status": "failed", "errors": [{"code": 131031}]}
    case.inbox.save_events(parse_events(body(payload([], statuses=[status])), SETTINGS))
    case.responses.process_pending()
    expire_round(case)
    case.responses.finalize_due()
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 0
    assert scalar(case, "SELECT estado FROM reclamos") == "Pendiente de asignación"
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "revision"


def test_pending_inbox_prevents_early_expiration(response_case):
    case = response_case
    inbound(case)
    expire_round(case)
    with case.db.begin() as c:
        c.execute(text("UPDATE whatsapp_eventos_entrada SET recibido_en=clock_timestamp()-interval '2 hours',ocurrido_en=clock_timestamp()-interval '2 hours'"))
    assert case.responses.finalize_due() == 0
    case.responses.process_pending()
    assert case.responses.finalize_due() == 1
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "disponibles"


def test_two_expirers_do_not_duplicate_state_or_alert(response_case):
    case = response_case
    expire_round(case)
    barrier = Barrier(2)
    def expire(_):
        barrier.wait(timeout=5)
        return case.responses.finalize_due()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(expire, range(2))) == 1
    assert scalar(case, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :pattern", {"pattern": "hu19:%:cierre"}) == 1


def test_changed_claim_cancels_round_without_overwriting_domain(response_case):
    case = response_case
    expire_round(case)
    with case.db.begin() as c:
        c.execute(text("UPDATE reclamos SET estado='Resuelto'"))
    case.responses.finalize_due()
    assert scalar(case, "SELECT estado FROM reclamos") == "Resuelto"
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "cancelada"


def test_schema_security_and_constraints(response_case):
    case = response_case
    with case.db.connect() as c:
        for table in ("presupuestos", "presupuesto_respuestas"):
            assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:table AS regclass)"), {"table": "public." + table}).scalar_one()
            for role in ("anon", "authenticated"):
                assert not c.execute(text("SELECT has_table_privilege(:role,:table,'SELECT,INSERT,UPDATE,DELETE')"), {"role": role, "table": "public." + table}).scalar_one()
        assert c.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='presupuesto_respuestas'")).scalar_one() == 0


def test_http_rejection_alerts_operator_but_does_not_mean_provider_silence(quote_case):
    case = eligible(quote_case)
    provider(case)
    case.quotes.prepare(case.claim)
    job = case.quotes.reserve_one(recipients=("15555550100",))
    assert begin(case, job)
    case.quotes.finish(job, outcome="rechazada")
    service = SqlAlchemyQuoteResponses(sessionmaker(bind=case.db), scope_claim_id=case.claim)
    assert service.finalize_due() == 1
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "revision"
    assert scalar(case, "SELECT estado FROM reclamos") == "Pendiente de asignación"
    assert scalar(case, "SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :pattern", {"pattern": "hu19:%:cierre"}) == 1


def test_disabled_channel_does_not_start_response_timer_or_mark_silence(quote_case):
    case = eligible(quote_case)
    provider(case)
    case.quotes.prepare(case.claim)
    service = SqlAlchemyQuoteResponses(sessionmaker(bind=case.db), scope_claim_id=case.claim)
    assert service.finalize_due() == 0
    assert scalar(case, "SELECT respuesta_vence_en FROM reclamo_rondas_presupuesto") is None
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "sin_envios"
    assert scalar(case, "SELECT estado FROM reclamos") == "Pendiente de asignación"


def test_webhook_ahead_of_send_commit_waits_then_consumes(quote_case):
    case = eligible(quote_case)
    provider(case)
    case.quotes.prepare(case.claim)
    job = case.quotes.reserve_one(recipients=("15555550100",))
    assert begin(case, job)
    case.responses = SqlAlchemyQuoteResponses(sessionmaker(bind=case.db))
    case.inbox = SqlAlchemyWhatsAppInbox(sessionmaker(bind=case.db))
    inbound(case)
    assert case.responses.process_pending() == 0
    assert scalar(case, "SELECT count(*) FROM presupuesto_respuestas") == 0
    case.quotes.finish(job, outcome="aceptada", message_id="wamid.synthetic.outbound")
    assert case.responses.process_pending() == 1
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 1


def test_each_provider_keeps_24h_and_partial_quotes_close_correctly(quote_case):
    case = eligible(quote_case)
    provider(case)
    provider(case, phone="+15555550101")
    case.quotes.prepare(case.claim)
    first = case.quotes.reserve_one(recipients=("15555550100",))
    assert begin(case, first)
    case.quotes.finish(first, outcome="aceptada", message_id="wamid.synthetic.outbound")
    second = case.quotes.reserve_one(recipients=("15555550101",))
    assert begin(case, second)
    case.quotes.finish(second, outcome="aceptada", message_id="wamid.synthetic.second")
    with case.db.connect() as c:
        assert c.execute(text("SELECT bool_and(respuesta_vence_en=aceptado_en+interval '24 hours') FROM proveedor_solicitudes_presupuesto")).scalar_one()
        assert c.execute(text("SELECT respuesta_vence_en=(SELECT max(respuesta_vence_en) FROM proveedor_solicitudes_presupuesto) FROM reclamo_rondas_presupuesto")).scalar_one()
    case.responses = SqlAlchemyQuoteResponses(sessionmaker(bind=case.db))
    case.inbox = SqlAlchemyWhatsAppInbox(sessionmaker(bind=case.db))
    inbound(case)
    case.responses.process_pending()
    expire_round(case)
    assert case.responses.finalize_due() == 1
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 1
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "disponibles"


def test_round_closure_does_not_depend_on_arbitrary_first_provider(response_case):
    case = response_case
    inbound(case)
    case.responses.process_pending()
    with case.db.begin() as c:
        c.execute(text("UPDATE proveedores SET activo=false"))
    expire_round(case)
    assert case.responses.finalize_due() == 1
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "disponibles"


def test_closed_round_does_not_accept_or_dispatch_new_work(response_case):
    case = response_case
    expire_round(case)
    case.responses.finalize_due()
    inbound(case)
    case.responses.process_pending()
    assert scalar(case, "SELECT resultado FROM presupuesto_respuestas") == "tardia"
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 0
    assert case.quotes.reserve_one(recipients=("15555550100",)) is None


@pytest.mark.parametrize("response_case", ["extraordinario"], indirect=True)
def test_extraordinary_quote_notifies_authorizing_owner_not_tenant(response_case):
    case = response_case
    inbound(case, "USD 100 Trabajo: reparación de la cañería.")
    case.responses.process_pending()
    assert scalar(case, "SELECT moneda FROM presupuestos") == "USD"
    assert scalar(case, "SELECT destinatario_tipo FROM notificaciones WHERE clave_idempotencia LIKE 'hu19:%'") == "propietario"


def test_racing_different_replies_do_not_create_two_quotes(response_case):
    case = response_case
    events = [inbound(case, f"ARS {price} Trabajo: reparación de la cañería.")[0] for price in (10000, 12000)]
    barrier = Barrier(2)
    def consume(event):
        barrier.wait(timeout=5)
        return case.responses.process_one(event)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(consume, events))
    assert scalar(case, "SELECT count(*) FROM presupuestos") == 1
    assert scalar(case, "SELECT count(*) FROM presupuesto_respuestas") == 2


def test_reservation_cannot_begin_after_round_deadline(quote_case):
    case = eligible(quote_case)
    provider(case)
    provider(case, phone="+15555550101")
    case.quotes.prepare(case.claim)
    first = case.quotes.reserve_one(recipients=("15555550100",))
    assert begin(case, first)
    case.quotes.finish(first, outcome="aceptada", message_id="wamid.synthetic.first")
    second = case.quotes.reserve_one(recipients=("15555550101",))
    expire_round(case)
    assert not begin(case, second)


def test_database_rejects_quote_linked_to_another_provider(response_case):
    case = response_case
    inbound(case)
    case.responses.process_pending()
    other = provider(case, phone="+15555550101")
    with pytest.raises(IntegrityError):
        with case.db.begin() as c:
            c.execute(text("UPDATE presupuestos SET proveedor_id=:provider"), {"provider": other})
    assert scalar(case, "SELECT proveedor_id FROM presupuestos") != other


def test_migration_preserves_legacy_price_and_derives_deadline_from_old_acceptance(choice_base):
    case = eligible(choice_base)
    with case.db.connect() as c:
        cursor = c.connection.cursor()
        try:
            for filename in ("15_proveedores_cobertura_horario.sql", "16_finalizar_cobertura_proveedores.sql",
                             "20261009120000_hu15_proveedores_candidatos.sql", "20261019230000_hu19_whatsapp_base.sql",
                             "20261020120000_hu19_solicitudes_presupuesto.sql"):
                cursor.execute((MIGRATIONS / filename).read_text(encoding="utf-8"))
            c.commit()
        finally:
            cursor.close()
    with case.db.begin() as c:
        case.specialty = c.execute(text("INSERT INTO especialidades(nombre) VALUES ('Especialidad sintética antigua') RETURNING id")).scalar_one()
        c.execute(text("UPDATE reclamos SET tipo_id=:id"), {"id": case.specialty})
    prov = provider(case)
    case.quotes = SqlAlchemyQuoteRequests(sessionmaker(bind=case.db))
    case.quotes.prepare(case.claim)
    with case.db.begin() as c:
        c.execute(text("""UPDATE proveedor_solicitudes_presupuesto SET estado='aceptada',intentos=1,
            reserva_token=gen_random_uuid(),intento_en=clock_timestamp()-interval '3 hours',
            aceptado_en=clock_timestamp()-interval '3 hours',mensaje_externo_id='wamid.synthetic.legacy'"""))
        c.execute(text("""INSERT INTO presupuestos(reclamo_id,proveedor_id,monto,descripcion)
            VALUES (:claim,:provider,12345.67,'Cotización sintética histórica')"""), {"claim": case.claim, "provider": prov})
    notices = scalar(case, "SELECT count(*) FROM notificaciones")
    with case.db.connect() as c:
        cursor = c.connection.cursor()
        try:
            cursor.execute((MIGRATIONS / "20261025160000_hu19_respuestas_presupuesto.sql").read_text(encoding="utf-8"))
            c.commit()
        finally:
            cursor.close()
    assert str(scalar(case, "SELECT monto FROM presupuestos")) == "12345.67"
    assert scalar(case, "SELECT moneda FROM presupuestos") is None
    assert scalar(case, "SELECT solicitud_presupuesto_id FROM presupuestos") is None
    assert scalar(case, "SELECT respuesta_vence_en=aceptado_en+interval '24 hours' FROM proveedor_solicitudes_presupuesto")
    assert scalar(case, "SELECT respuesta_vence_en < clock_timestamp()+interval '22 hours' FROM reclamo_rondas_presupuesto")
    assert scalar(case, "SELECT recepcion_estado FROM reclamo_rondas_presupuesto") == "esperando"
    assert scalar(case, "SELECT count(*) FROM notificaciones") == notices
