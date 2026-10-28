"""HU19 con HU15/16/17 reales en PostgreSQL LOCAL descartable, sin Meta."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.quote_requests import SqlAlchemyQuoteRequests
from app.services.quote_requests import QuoteRequestsWorker
from app.services.whatsapp_sender import MetaWhatsAppSender
from tests.test_provider_choices_postgres import choice_base, prepare, body as choice_body
from tests.test_responsible_actor_postgres import claim_case, local_engine, snapshot, MIGRATIONS
from tests.whatsapp_helpers import SETTINGS


pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Sólo PostgreSQL local descartable.")


@pytest.fixture
def quote_case(choice_base):
    case = choice_base
    with case.db.connect() as connection:
        cursor = connection.connection.cursor()
        try:
            for filename in ("15_proveedores_cobertura_horario.sql", "16_finalizar_cobertura_proveedores.sql",
                             "20261009120000_hu15_proveedores_candidatos.sql", "20261019230000_hu19_whatsapp_base.sql",
                             "20261020120000_hu19_solicitudes_presupuesto.sql", "20261025160000_hu19_respuestas_presupuesto.sql"):
                cursor.execute((MIGRATIONS / filename).read_text(encoding="utf-8"))
            connection.commit()
        finally:
            cursor.close()
    with case.db.begin() as c:
        case.specialty = c.execute(text("INSERT INTO especialidades(nombre) VALUES ('HU19 Sintetica') RETURNING id")).scalar_one()
        c.execute(text("UPDATE reclamos SET tipo_id=:s WHERE id=:id"), {"s": case.specialty, "id": case.claim})
        c.execute(text("UPDATE propiedades SET barrio='Centro'"))
    case.quotes = SqlAlchemyQuoteRequests(sessionmaker(bind=case.db), scope_claim_id=case.claim)
    return case


def eligible(case, expense="ordinario", choice="fidelizado"):
    prepare(case, expense)
    case.repo.choose(case.claim, case.actor, choice_body(case, choice))
    return case


def provider(case, *, phone="+15555550100", active=True, city="Localidad de prueba", province="Córdoba", area=None, specialty=True):
    with case.db.begin() as c:
        value = c.execute(text("""INSERT INTO proveedores(nombre_razon_social,telefono,activo)
            VALUES ('Proveedor Sintetico',:phone,:active) RETURNING id"""), {"phone": phone, "active": active}).scalar_one()
        if specialty:
            c.execute(text("INSERT INTO proveedor_especialidades(proveedor_id,especialidad_id) VALUES (:p,:s)"), {"p": value, "s": case.specialty})
        coverage = c.execute(text("""INSERT INTO proveedor_coberturas(proveedor_id,provincia,localidad,cubre_toda_localidad)
            VALUES (:p,:province,:city,:all) RETURNING id"""), {"p": value, "province": province, "city": city, "all": area is None}).scalar_one()
        if area:
            c.execute(text("INSERT INTO proveedor_cobertura_barrios(cobertura_id,barrio) VALUES (:c,:area)"), {"c": coverage, "area": area})
        return value


def requests(case):
    with case.db.connect() as c:
        return c.execute(text("SELECT * FROM proveedor_solicitudes_presupuesto ORDER BY id")).mappings().all()


def expire(case):
    with case.db.begin() as c:
        c.execute(text("UPDATE proveedor_solicitudes_presupuesto SET reserva_hasta=clock_timestamp()-interval '1 second' WHERE estado IN ('reservada','enviando')"))


def begin(case, job):
    return case.quotes.begin_send(job, template_name="synthetic_quote", language="es_AR", waba_id=SETTINGS.waba_id, phone_id=SETTINGS.phone_number_id)


@pytest.mark.parametrize("expense", ["ordinario", "extraordinario"])
def test_prepares_compatible_candidates_once_and_preserves_domain(quote_case, expense):
    case = eligible(quote_case, expense)
    expected = {provider(case), provider(case, phone="+15555550101", area="Centro")}
    for phone, changes in [("+15555550102", {"active": False}), ("+15555550103", {"city": "Otra ciudad"}),
        ("+15555550104", {"province": "Santa Fe"}), ("+15555550105", {"area": "Norte"}), ("+15555550106", {"specialty": False})]:
        provider(case, phone=phone, **changes)
    before = snapshot(case.db, case.claim)
    result = case.quotes.prepare(case.claim)
    assert result.count == 2 and not result.repeated
    assert case.quotes.prepare(case.claim).repeated
    assert {row["proveedor_id"] for row in requests(case)} == expected
    assert all(row["estado"] == "pendiente" and row["intentos"] == 0 and row["aceptado_en"] is None for row in requests(case))
    assert snapshot(case.db, case.claim) == before


@pytest.mark.parametrize("condition", ["not_chosen", "own", "pending_authorization", "closed", "changed_actor", "inactive", "first_login", "tenant_left"])
def test_not_eligible_never_creates_request(quote_case, condition):
    case = quote_case
    if condition == "pending_authorization":
        prepare(case, "extraordinario", authorize=False)
    elif condition == "not_chosen":
        prepare(case)
    else:
        eligible(case, choice="propio" if condition == "own" else "fidelizado")
    provider(case)
    with case.db.begin() as c:
        if condition == "closed":
            c.execute(text("UPDATE reclamos SET estado='Resuelto' WHERE id=:id"), {"id": case.claim})
        elif condition in {"inactive", "first_login"}:
            c.execute(text("UPDATE usuarios SET " + ("activo=false" if condition == "inactive" else "primer_ingreso=true") + " WHERE id=:id"), {"id": case.actor.id})
        elif condition == "changed_actor":
            c.execute(text("UPDATE inquilinos SET usuario_id=null"))
        elif condition == "tenant_left":
            c.execute(text("UPDATE inquilinos SET propiedad_id=null,estado='sin_propiedad_asignada'"))
    assert case.quotes.prepare(case.claim).round_id is None and requests(case) == []


def test_no_candidates_is_audited_without_changing_claim_or_sending(quote_case):
    case = eligible(quote_case)
    result = case.quotes.prepare(case.claim)
    assert result.count == 0 and result.reason == "sin_candidatos_vigentes"
    assert case.quotes.prepare(case.claim).repeated
    with case.db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_rondas_presupuesto")).scalar_one() == 1


def test_two_discoverers_do_not_duplicate_round_or_requests(quote_case):
    case = eligible(quote_case)
    provider(case)
    barrier = Barrier(2)
    def discover(_):
        barrier.wait(timeout=5)
        return case.quotes.discover()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(discover, range(2)))
    assert len(requests(case)) == 1


@pytest.mark.parametrize("change", ["claim", "phone", "inactive", "specialty", "coverage", "description", "owner"])
def test_changes_after_preparing_prevent_http(quote_case, change):
    case = eligible(quote_case)
    p = provider(case)
    case.quotes.prepare(case.claim)
    job = case.quotes.reserve_one(recipients=("15555550100",))
    with case.db.begin() as c:
        if change == "claim":
            c.execute(text("UPDATE reclamos SET estado='Resuelto' WHERE id=:id"), {"id": case.claim})
        elif change == "phone":
            c.execute(text("UPDATE proveedores SET telefono='+15555550102' WHERE id=:id"), {"id": p})
        elif change == "inactive":
            c.execute(text("UPDATE proveedores SET activo=false WHERE id=:id"), {"id": p})
        elif change == "specialty":
            c.execute(text("DELETE FROM proveedor_especialidades WHERE proveedor_id=:id"), {"id": p})
        elif change == "coverage":
            c.execute(text("UPDATE proveedor_coberturas SET localidad='Otra ciudad' WHERE proveedor_id=:id"), {"id": p})
        elif change == "description":
            c.execute(text("UPDATE reclamos SET descripcion='Otro problema sintético suficientemente largo' WHERE id=:id"), {"id": case.claim})
        elif change == "owner":
            new_owner = c.execute(text("""INSERT INTO propietarios(nombre_completo,dni,email,telefono)
                VALUES ('Otra Persona Sintetica','10000003','other@example.com','00000000') RETURNING id""")).scalar_one()
            c.execute(text("UPDATE propiedades SET propietario_id=:id"), {"id": new_owner})
    assert not begin(case, job) and requests(case)[0]["estado"] == "omitida"


def test_expired_reservation_is_reclaimed_only_before_any_http(quote_case):
    case = eligible(quote_case)
    provider(case)
    case.quotes.prepare(case.claim)
    old = case.quotes.reserve_one(recipients=("15555550100",))
    expire(case)
    assert case.quotes.recover_expired() == 1
    new = case.quotes.reserve_one(recipients=("15555550100",))
    assert new.token != old.token and not begin(case, old) and begin(case, new)
    expire(case)
    assert case.quotes.recover_expired() == 1
    assert requests(case)[0]["estado"] == "desconocida"
    assert case.quotes.reserve_one(recipients=("15555550100",)) is None
    assert case.quotes.finish(new, outcome="aceptada", message_id="wamid.late")
    assert requests(case)[0]["estado"] == "aceptada"


def test_two_workers_with_mock_http_send_exactly_once(quote_case):
    case = eligible(quote_case)
    provider(case)
    calls = []
    def sent(request):
        calls.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.synthetic.quote"}]})
    sender = MetaWhatsAppSender(SETTINGS, transport=httpx.MockTransport(sent))
    barrier = Barrier(2)
    def tick(_):
        barrier.wait(timeout=5)
        return QuoteRequestsWorker(case.quotes, sender, settings=SETTINGS, template_name="synthetic_quote").tick()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(tick, range(2)))
    assert len(calls) == 1 and requests(case)[0]["estado"] == "aceptada"
    for _ in range(3):
        tick_worker = QuoteRequestsWorker(case.quotes, sender, settings=SETTINGS, template_name="synthetic_quote")
        tick_worker.tick()
    assert len(calls) == 1 and requests(case)[0]["intentos"] == 1


def test_timeout_is_durable_and_restart_does_not_resend(quote_case):
    case = eligible(quote_case)
    provider(case)
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("private synthetic failure", request=request)
    sender = MetaWhatsAppSender(SETTINGS, transport=httpx.MockTransport(timeout))
    for _ in range(2):
        repo = SqlAlchemyQuoteRequests(sessionmaker(bind=case.db), scope_claim_id=case.claim)
        QuoteRequestsWorker(repo, sender, settings=SETTINGS, template_name="synthetic_quote").tick()
    assert len(calls) == 1
    row = requests(case)[0]
    assert row["estado"] == "desconocida" and row["intentos"] == 1 and "private" not in row["motivo"]


def test_off_flag_keeps_pending_and_does_not_claim_any_test_recipient(quote_case):
    case = eligible(quote_case)
    provider(case)
    def forbidden(_request):
        raise AssertionError("No debe llamar HTTP")
    settings = replace(SETTINGS, outbound_enabled=False)
    QuoteRequestsWorker(case.quotes, MetaWhatsAppSender(settings, transport=httpx.MockTransport(forbidden)),
        settings=settings, template_name="synthetic_quote").tick()
    assert requests(case)[0]["estado"] == "pendiente" and requests(case)[0]["intentos"] == 0


def test_cannot_forge_payload_of_a_reservation(quote_case):
    case = eligible(quote_case)
    provider(case)
    case.quotes.prepare(case.claim)
    job = case.quotes.reserve_one(recipients=("15555550100",))
    assert not begin(case, replace(job, recipient="15555550102"))


def test_migration_is_private_with_no_public_policies(quote_case):
    with quote_case.db.connect() as c:
        for table in ("reclamo_rondas_presupuesto", "proveedor_solicitudes_presupuesto", "solicitud_presupuesto_eventos"):
            assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:table AS regclass)"), {"table": table}).scalar_one()
            assert c.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=:table"), {"table": table}).scalar_one() == 0
            for role in ("anon", "authenticated"):
                assert not c.execute(text("SELECT has_table_privilege(:role,:table,'SELECT,INSERT,UPDATE,DELETE')"), {"role": role, "table": table}).scalar_one()


def test_failure_of_audit_rolls_back_round_and_all_requests(quote_case):
    case = eligible(quote_case)
    provider(case)
    with case.db.begin() as c:
        c.exec_driver_sql("""CREATE FUNCTION hu19_fail_audit() RETURNS trigger LANGUAGE plpgsql AS
            $$ BEGIN RAISE EXCEPTION 'synthetic failure'; END $$;
            CREATE TRIGGER hu19_audit_failure BEFORE INSERT ON solicitud_presupuesto_eventos
            FOR EACH ROW EXECUTE FUNCTION hu19_fail_audit();""")
    with pytest.raises(SQLAlchemyError):
        case.quotes.prepare(case.claim)
    with case.db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reclamo_rondas_presupuesto")).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM proveedor_solicitudes_presupuesto")).scalar_one() == 0


@pytest.mark.parametrize("state", ["enviando", "aceptada"])
def test_failure_at_commit_before_or_after_http_does_not_duplicate(quote_case, state):
    case = eligible(quote_case)
    provider(case)
    calls = []
    def accepted(request):
        calls.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.commit.synthetic"}]})
    worker = QuoteRequestsWorker(case.quotes, MetaWhatsAppSender(SETTINGS, transport=httpx.MockTransport(accepted)),
                                 settings=SETTINGS, template_name="synthetic_quote")
    with case.db.begin() as c:
        # Literal fijo parametrizado por pytest, no entrada pública.
        c.exec_driver_sql("""CREATE FUNCTION hu19_fail_commit() RETURNS trigger LANGUAGE plpgsql AS
            $$ BEGIN IF NEW.estado='""" + state + """' THEN RAISE EXCEPTION 'synthetic failure'; END IF;
            RETURN NEW; END $$;
            CREATE CONSTRAINT TRIGGER hu19_commit_failure AFTER UPDATE ON proveedor_solicitudes_presupuesto
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION hu19_fail_commit();""")
    with pytest.raises(SQLAlchemyError):
        worker.tick()
    assert len(calls) == (1 if state == "aceptada" else 0)
    with case.db.begin() as c:
        c.exec_driver_sql("DROP TRIGGER hu19_commit_failure ON proveedor_solicitudes_presupuesto")
    expire(case)
    worker.tick()
    assert len(calls) == 1
    assert requests(case)[0]["estado"] == ("desconocida" if state == "aceptada" else "aceptada")


def test_many_candidates_are_prepared_without_contacting_them(quote_case):
    case = eligible(quote_case)
    expected = {provider(case, phone=f"+15555551{n:03d}") for n in range(100)}
    before = snapshot(case.db, case.claim)
    assert case.quotes.prepare(case.claim).count == 100
    assert {row["proveedor_id"] for row in requests(case)} == expected
    assert snapshot(case.db, case.claim) == before
    assert case.quotes.reserve_one(recipients=("15555550100",)) is None
    assert all(row["intentos"] == 0 for row in requests(case))


def test_changing_parameters_or_token_cannot_send(quote_case):
    case = eligible(quote_case)
    provider(case)
    case.quotes.prepare(case.claim)
    job = case.quotes.reserve_one(recipients=("15555550100",))
    assert not begin(case, replace(job, token=uuid4()))
    assert not begin(case, replace(job, parameters=("forged", "problem", "address", "24 horas")))


def test_hu21_checkpoint_is_preserved_by_preparation_and_mock_send(quote_case):
    import psycopg
    from psycopg.rows import dict_row
    from app.db.coordination import PostgresCoordinationRepository
    from app.agents.coordination.state import ResumeRequest
    from scripts.check_coordination_postgres import apply, verify
    case = eligible(quote_case)
    provider(case)
    url = case.db.url
    def connect():
        return psycopg.connect(host=url.host, port=url.port, user=url.username, password=url.password,
                               dbname=url.database, row_factory=dict_row, prepare_threshold=None)
    with connect() as c:
        apply(c)
        verify(c)
    coordination = PostgresCoordinationRepository(connect)
    initial = coordination.resume(case.claim, ResumeRequest(evento_id=uuid4(),version_esperada=0), case.actor)
    def accepted(_request):
        return httpx.Response(200, json={"messages": [{"id": "wamid.context.synthetic"}]})
    QuoteRequestsWorker(case.quotes, MetaWhatsAppSender(SETTINGS, transport=httpx.MockTransport(accepted)),
                        settings=SETTINGS,template_name="synthetic_quote").tick()
    current = coordination.get(case.claim, case.actor)
    assert current.contexto == initial.contexto and current.ultima_actividad == initial.ultima_actividad
