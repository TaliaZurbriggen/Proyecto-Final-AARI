"""Regresiones PR26 en una base descartable de PostgreSQL local, sin servicios externos.

AARI_TEST_POSTGRES_URL debe apuntar a una instancia local dedicada a pruebas.
Se crea y elimina únicamente una base aari_pr26_<uuid> por caso.
"""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.db.reclamos import SqlAlchemyClaimsRepository
from app.schemas.reclamos import AgentClassificationResult
from app.services.classification_service import ClaimClassificationConflictError


pytestmark = pytest.mark.skipif(
    not os.getenv("AARI_TEST_POSTGRES_URL"),
    reason="Requiere PostgreSQL local dedicado (AARI_TEST_POSTGRES_URL).",
)
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture
def local_engine():
    url = make_url(os.environ["AARI_TEST_POSTGRES_URL"])
    assert url.get_backend_name() == "postgresql"
    assert url.host in {"127.0.0.1", "localhost", "::1"}, "Solo PostgreSQL local."
    database = "aari_pr26_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    db = create_engine(
        url.set(database=database),
        connect_args={"options": "-c statement_timeout=10000 -c lock_timeout=5000"},
    )
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
    try:
        with db.connect() as connection:
            cursor = connection.connection.cursor()
            try:
                # Solo el catálogo mínimo de Storage, sin conectarse a Supabase.
                cursor.execute("""
                    CREATE SCHEMA storage;
                    CREATE TABLE storage.buckets (
                        id text PRIMARY KEY, name text, public boolean,
                        file_size_limit bigint, allowed_mime_types text[]
                    );
                """)
                for number in (1, 2, 3, 4, 6, 17, 18, 19, 21, 22, 23):
                    migration = next(MIGRATIONS.glob(f"{number:02d}_*.sql"))
                    sql = migration.read_text(encoding="utf-8")
                    if number == 4:
                        # No cargar contactos reales del seed histórico.
                        sql = sql.split("-- Seed de parámetros")[0]
                    cursor.execute(sql)
                cursor.execute("""
                    INSERT INTO configuracion_sistema (clave, valor) VALUES
                        ('correo_contacto_inmobiliaria', 'agency@example.com'),
                        ('plazo_recordatorio_horas', '48'),
                        ('plazo_escalado_horas', '24');
                """)
                connection.commit()
            finally:
                cursor.close()
        yield db
    finally:
        db.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database}"')
        admin.dispose()


@pytest.fixture
def claim_case(local_engine):
    with local_engine.begin() as connection:
        owner_id = connection.execute(text("""
            INSERT INTO propietarios (nombre_completo, dni, email, telefono)
            VALUES ('Titular Sintetico', '10000001', 'owner@example.com', '00000000')
            RETURNING id
        """)).scalar_one()
        property_id = connection.execute(text("""
            INSERT INTO propiedades (direccion, provincia, localidad, tipo, propietario_id)
            VALUES ('Unidad de prueba', 'Córdoba', 'Localidad de prueba', 'casa', :owner)
            RETURNING id
        """), {"owner": owner_id}).scalar_one()
        tenant_id = connection.execute(text("""
            INSERT INTO inquilinos (nombre_completo, dni, email, telefono, propiedad_id)
            VALUES ('Inquilino Sintetico', '10000002', 'tenant@example.com', '00000000', :property)
            RETURNING id
        """), {"property": property_id}).scalar_one()
        connection.execute(text("""
            INSERT INTO usuarios (email, password_hash, rol, nombre_completo)
            VALUES ('operator@example.com', 'not-a-credential', 'operador', 'Operador Sintetico')
        """))
        claim_id = connection.execute(text("""
            INSERT INTO reclamos (descripcion, urgencia, inquilino_id, propiedad_id)
            VALUES ('Descripción sintética para verificar la concurrencia.', 'media', :tenant, :property)
            RETURNING id
        """), {"tenant": tenant_id, "property": property_id}).scalar_one()
    return local_engine, SqlAlchemyClaimsRepository(sessionmaker(bind=local_engine)), claim_id


def classification(expense):
    actor = {"ordinario": "inquilino", "extraordinario": "propietario", "expensa": "inmobiliaria"}[expense]
    return AgentClassificationResult(
        tipo_gasto=expense, confianza=0.95, fundamento="Clasificación sintética.",
        debe_escalar=False, motivo_escalado=None, estado_clasificacion="clasificado",
        actor_responsable=actor, notificacion_responsable_requerida=True,
    )


def snapshot(db, claim_id):
    with db.connect() as connection:
        return {
            table: connection.execute(
                text(f"SELECT * FROM {table} WHERE {key} = :id ORDER BY {order}"),
                {"id": claim_id},
            ).mappings().all()
            for table, key, order in (
                ("reclamos", "id", "id"),
                ("reclamo_responsables", "reclamo_id", "reclamo_id"),
                ("reclamo_historial_estados", "reclamo_id", "id"),
                ("notificaciones", "reclamo_id", "id"),
            )
        }


@pytest.mark.parametrize(("first", "second"), [
    ("ordinario", "ordinario"), ("extraordinario", "extraordinario"),
    ("ordinario", "extraordinario"), ("extraordinario", "ordinario"),
    ("expensa", "ordinario"),
])
def test_reclassification_preserves_the_entire_original_request(claim_case, first, second):
    db, repo, claim_id = claim_case
    repo.persist_classification(claim_id, classification(first))
    original = snapshot(db, claim_id)
    with pytest.raises(ClaimClassificationConflictError):
        repo.persist_classification(claim_id, classification(second))
    assert snapshot(db, claim_id) == original
    assert repo.get_for_classification(claim_id).clasificado is True


def test_two_simultaneous_classifications_persist_only_one_result(claim_case):
    db, repo, claim_id = claim_case
    start = Barrier(2)

    def classify(expense):
        start.wait(timeout=5)
        try:
            repo.persist_classification(claim_id, classification(expense))
            return expense
        except ClaimClassificationConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(classify, ["ordinario", "extraordinario"]))
    winner, = [value for value in results if value is not None]
    data = snapshot(db, claim_id)
    assert data["reclamos"][0]["tipo_gasto"] == winner
    assert data["reclamo_responsables"][0]["actor_tipo"] == classification(winner).actor_responsable
    assert len(data["reclamo_historial_estados"]) == 1
    assert len([n for n in data["notificaciones"] if n["tipo_evento"] == "responsable_inicial"]) == 1


def test_state_changed_during_model_call_is_rechecked_before_persisting(claim_case):
    db, repo, claim_id = claim_case
    context = repo.get_for_classification(claim_id)
    assert context.estado == "Recibido" and context.clasificado is False
    with db.begin() as connection:
        connection.execute(
            text("UPDATE reclamos SET estado = 'Autorizado' WHERE id = :id"),
            {"id": claim_id},
        )
    original = snapshot(db, claim_id)
    with pytest.raises(ClaimClassificationConflictError):
        repo.persist_classification(claim_id, classification("ordinario"))
    assert snapshot(db, claim_id) == original


def test_initial_pending_claim_can_still_be_classified(claim_case):
    db, repo, claim_id = claim_case
    with db.begin() as connection:
        connection.execute(
            text("UPDATE reclamos SET estado = 'Clasificación pendiente' WHERE id = :id"),
            {"id": claim_id},
        )
    result = repo.persist_classification(claim_id, classification("ordinario"))
    assert result.response.estado == "Pendiente de respuesta del responsable"
    assert result.notification_id is not None


def make_due(db, claim_id, *, expired=True):
    with db.begin() as connection:
        connection.execute(text("""
            UPDATE reclamo_responsables
            SET solicitado_en = CURRENT_TIMESTAMP - interval '80 hours',
                recordatorio_programado_en = CURRENT_TIMESTAMP - interval '32 hours',
                respuesta_vence_en = CURRENT_TIMESTAMP + make_interval(hours => :remaining)
            WHERE reclamo_id = :id
        """), {"id": claim_id, "remaining": -8 if expired else 8})


@pytest.mark.parametrize("expired", [True, False], ids=["vencimiento", "recordatorio"])
def test_authorization_in_progress_prevents_followups(claim_case, expired):
    db, repo, claim_id = claim_case
    repo.persist_classification(claim_id, classification("extraordinario"))
    make_due(db, claim_id, expired=expired)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with db.begin() as authorization:
            authorization.execute(
                text("UPDATE reclamos SET estado = 'Autorizado' WHERE id = :id"),
                {"id": claim_id},
            )
            # El estado confirmado todavía es pendiente para el otro proceso.
            # Debe saltar el reclamo bloqueado, sin esperar ni generar alertas.
            future = pool.submit(repo.enqueue_due_responsible_followups, limit=10)
            assert future.result(timeout=3) == 0
    assert repo.enqueue_due_responsible_followups(limit=10) == 0
    data = snapshot(db, claim_id)
    assert data["reclamos"][0]["estado"] == "Autorizado"
    assert data["reclamo_responsables"][0]["escalado_en"] is None
    assert data["reclamo_responsables"][0]["recordatorio_generado_en"] is None
    assert not any(n["tipo_evento"] in {"responsable_vencido", "responsable_recordatorio"}
                   for n in data["notificaciones"])


def test_followup_selection_serializes_a_later_authorization(claim_case):
    db, repo, claim_id = claim_case
    repo.persist_classification(claim_id, classification("extraordinario"))
    make_due(db, claim_id)
    selected, release = Event(), Event()
    worker_db = create_engine(db.url, connect_args={"options": "-c statement_timeout=10000"})
    worker = SqlAlchemyClaimsRepository(sessionmaker(bind=worker_db))

    def pause_after_select(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE OF" in statement and "rr.respuesta_vence_en <=" in statement:
            selected.set()
            assert release.wait(timeout=5)

    event.listen(worker_db, "after_cursor_execute", pause_after_select)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.enqueue_due_responsible_followups, limit=10)
            try:
                assert selected.wait(timeout=5)
                # Otra conexión intenta autorizar entre SELECT y UPDATE.
                # El lock del reclamo debe impedirle adelantarse al vencimiento.
                with pytest.raises(OperationalError) as blocked, db.begin() as response:
                    response.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    response.execute(
                        text("UPDATE reclamos SET estado = 'Autorizado' WHERE id = :id"),
                        {"id": claim_id},
                    )
                assert blocked.value.orig.pgcode == "55P03"
            finally:
                release.set()
            assert future.result(timeout=5) == 1
    finally:
        event.remove(worker_db, "after_cursor_execute", pause_after_select)
        worker_db.dispose()
    data = snapshot(db, claim_id)
    assert data["reclamos"][0]["estado"] == "Pendiente de respuesta - vencido"
    assert data["reclamo_responsables"][0]["escalado_en"] is not None
    assert len([n for n in data["notificaciones"] if n["tipo_evento"] == "responsable_vencido"]) == 1
    assert repo.enqueue_due_responsible_followups(limit=10) == 0


def test_no_alert_or_escalation_marker_when_transition_updates_zero_rows(claim_case):
    db, repo, claim_id = claim_case
    repo.persist_classification(claim_id, classification("ordinario"))
    make_due(db, claim_id)
    with db.begin() as connection:
        connection.exec_driver_sql("""
            CREATE FUNCTION public.skip_test_expiry() RETURNS trigger AS $$
            BEGIN
                IF NEW.estado = 'Pendiente de respuesta - vencido' THEN RETURN NULL; END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER skip_test_expiry BEFORE UPDATE ON reclamos
            FOR EACH ROW EXECUTE FUNCTION public.skip_test_expiry();
        """)
    original = snapshot(db, claim_id)
    assert repo.enqueue_due_responsible_followups(limit=10) == 0
    assert snapshot(db, claim_id) == original
