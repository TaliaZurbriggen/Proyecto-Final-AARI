"""Migración/bandeja reales. Sólo una base LOCAL y descartable de HU19."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
from threading import Barrier

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.api.whatsapp import get_whatsapp_inbox, get_whatsapp_settings
from app.db.whatsapp import SqlAlchemyWhatsAppInbox
from app.main import app
from app.services.whatsapp_webhook import parse_events
from tests.whatsapp_helpers import SETTINGS, body, message, payload, signature


TEST_URL = os.getenv("AARI_WHATSAPP_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="Requiere PostgreSQL local descartable de HU19.")


@pytest.fixture(scope="module")
def database():
    url = make_url(TEST_URL)
    # No permitir siquiera una conexión a Supabase, una base habitual ni otro host.
    assert url.get_backend_name() == "postgresql"
    assert url.host in {"127.0.0.1", "localhost", "::1"}
    assert url.database == "test_aari_hu19"
    engine = create_engine(url, connect_args={"connect_timeout": 5}, pool_size=8, max_overflow=0)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one() == "test_aari_hu19"
        assert connection.execute(text("SELECT to_regclass('public.whatsapp_eventos_entrada')")).scalar_one() is None
        connection.rollback()
        cursor = connection.connection.cursor()
        try:
            cursor.execute("""DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF;
                END $$;
                CREATE TABLE public.hu19_qa_canary (value text);
                INSERT INTO public.hu19_qa_canary VALUES ('synthetic unchanged');""")
            connection.commit()
            migration = Path(__file__).parents[1] / "migrations/20261019230000_hu19_whatsapp_base.sql"
            cursor.execute(migration.read_text(encoding="utf-8"))
            connection.commit()
        finally:
            cursor.close()
    yield engine
    engine.dispose()


@pytest.fixture
def inbox(database):
    # La base de nombre fijo anterior debe ser nueva, local y descartable.
    with database.begin() as connection:
        connection.execute(text("TRUNCATE public.whatsapp_eventos_entrada"))
    return SqlAlchemyWhatsAppInbox(sessionmaker(bind=database))


def count(database):
    with database.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM public.whatsapp_eventos_entrada")).scalar_one()


def test_migration_is_private_and_preserves_existing_data(database):
    with database.connect() as connection:
        assert connection.execute(text("SELECT value FROM public.hu19_qa_canary")).scalar_one() == "synthetic unchanged"
        assert connection.execute(text("""SELECT relrowsecurity FROM pg_class
            WHERE oid='public.whatsapp_eventos_entrada'::regclass""")).scalar_one()
        assert connection.execute(text("""SELECT count(*) FROM pg_policies
            WHERE schemaname='public' AND tablename='whatsapp_eventos_entrada'""")).scalar_one() == 0
        for role in ("anon", "authenticated"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                assert not connection.execute(text("SELECT has_table_privilege(:role, :table, :privilege)"),
                    {"role": role, "table": "public.whatsapp_eventos_entrada", "privilege": privilege}).scalar_one()
        assert connection.execute(text("""SELECT count(*) FROM pg_class c,
            LATERAL aclexplode(c.relacl) a WHERE c.oid='public.whatsapp_eventos_entrada'::regclass
            AND a.grantee=0""")).scalar_one() == 0


def test_commit_is_durable_for_a_new_repository_and_duplicate_does_not_overwrite(database, inbox):
    raw = body()
    result = inbox.save_events(parse_events(raw, SETTINGS))
    assert (result.inserted, result.duplicated) == (1, 0)
    other = SqlAlchemyWhatsAppInbox(sessionmaker(bind=database))
    changed = body(payload([message(text={"body": "Changed retry must not overwrite original"})]))
    result = other.save_events(parse_events(changed, SETTINGS))
    assert (result.inserted, result.duplicated) == (0, 1)
    with database.connect() as connection:
        row = connection.execute(text("SELECT * FROM public.whatsapp_eventos_entrada")).mappings().one()
        assert row["datos"] == {"type": "text", "text": "Presupuesto sintético: ARS 12500 por la reparación."}
        assert row["ocurrido_en"].tzinfo is not None and row["recibido_en"].tzinfo is not None
        assert row["estado"] == "pendiente"


@pytest.mark.parametrize("workers", [2, 8])
def test_concurrent_retries_insert_once(database, inbox, workers):
    events = parse_events(body(), SETTINGS)
    barrier = Barrier(workers)
    def save(_index):
        barrier.wait(timeout=10)
        return inbox.save_events(events)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(save, range(workers)))
    assert sum(value.inserted for value in results) == count(database) == 1
    assert sum(value.duplicated for value in results) == workers - 1


def test_overlapping_batches_in_reverse_order_do_not_deadlock(database, inbox):
    values = parse_events(body(payload([message(f"wamid.overlap.{i}") for i in range(40)])), SETTINGS)
    barrier = Barrier(2)
    def save(reverse):
        barrier.wait(timeout=10)
        return inbox.save_events(values[::-1] if reverse else values)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, (False, True)))
    assert sum(result.inserted for result in results) == count(database) == 40
    assert sum(result.duplicated for result in results) == 40


def test_duplicate_inside_one_batch_is_counted_once(database, inbox):
    values = parse_events(body(payload([message(), message()])), SETTINGS)
    result = inbox.save_events(values)
    assert (result.inserted, result.duplicated) == (1, 1) and count(database) == 1


def test_invalid_row_rolls_back_entire_batch(database, inbox):
    value = parse_events(body(), SETTINGS)[0]
    invalid = replace(value, event_key="f" * 64, state="invalid")
    with pytest.raises(IntegrityError):
        inbox.save_events([value, invalid])
    assert count(database) == 0
    assert inbox.save_events([value]).inserted == 1


def test_one_bulk_insert_for_one_thousand_events(database, inbox):
    values = parse_events(body(payload([message(f"wamid.load.{i}") for i in range(1000)])), SETTINGS)
    statements = []
    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("INSERT"):
            statements.append(statement)
    event.listen(database, "before_cursor_execute", record)
    try:
        result = inbox.save_events(values)
    finally:
        event.remove(database, "before_cursor_execute", record)
    assert result.inserted == count(database) == 1000 and len(statements) == 1


def test_real_webhook_commit_failure_returns_no_ack_then_retry_is_durable(database, inbox):
    app.dependency_overrides[get_whatsapp_settings] = lambda: SETTINGS
    app.dependency_overrides[get_whatsapp_inbox] = lambda: inbox
    with database.begin() as connection:
        connection.execute(text("""CREATE FUNCTION public.hu19_qa_fail() RETURNS trigger LANGUAGE plpgsql
            AS $$ BEGIN RAISE EXCEPTION 'synthetic private database failure'; END $$"""))
        # Falla al COMMIT, no al INSERT: el endpoint no puede confirmar antes.
        connection.execute(text("""CREATE CONSTRAINT TRIGGER hu19_qa_failure
            AFTER INSERT ON public.whatsapp_eventos_entrada DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.hu19_qa_fail()"""))
    raw = body()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": signature(raw)}
    try:
        with TestClient(app) as client:
            failed = client.post("/webhooks/whatsapp", content=raw, headers=headers)
            assert failed.status_code == 503 and "private" not in failed.text
            assert count(database) == 0
            with database.begin() as connection:
                connection.execute(text("DROP TRIGGER hu19_qa_failure ON public.whatsapp_eventos_entrada"))
            assert client.post("/webhooks/whatsapp", content=raw, headers=headers).status_code == 200
            assert client.post("/webhooks/whatsapp", content=raw, headers=headers).status_code == 200
            assert count(database) == 1
    finally:
        app.dependency_overrides.pop(get_whatsapp_inbox, None)
        app.dependency_overrides.pop(get_whatsapp_settings, None)
        with database.begin() as connection:
            connection.execute(text("DROP TRIGGER IF EXISTS hu19_qa_failure ON public.whatsapp_eventos_entrada"))
            connection.execute(text("DROP FUNCTION public.hu19_qa_fail()"))


def test_message_delivery_status_and_media_stay_separate(database, inbox):
    raw = body(payload([message(), message("wamid.media", type="image", image={"id": "do-not-download"})],
        statuses=[{"id": "wamid.outbound", "status": status, "timestamp": "1792440000", "recipient_id": "15555550100"}
                  for status in ("read", "delivered", "sent")]))
    assert inbox.save_events(parse_events(raw, SETTINGS)).inserted == 5
    with database.connect() as connection:
        assert connection.execute(text("""SELECT count(*) FROM public.whatsapp_eventos_entrada
            WHERE tipo_evento='estado' AND datos->>'type' IN ('read','delivered','sent')""")).scalar_one() == 3
        assert connection.execute(text("""SELECT datos FROM public.whatsapp_eventos_entrada
            WHERE estado='no_soportado'""")).scalar_one() == {"type": "image"}


def test_empty_event_does_not_open_a_session():
    def no_session():
        raise AssertionError("No debe acceder a la base")
    assert SqlAlchemyWhatsAppInbox(no_session).save_events([]).inserted == 0
