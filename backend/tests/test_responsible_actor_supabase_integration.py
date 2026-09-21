"""QA transaccional optativo de AARI-135 contra PostgreSQL/Supabase."""

import os
from pathlib import Path
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api.reclamos import get_claim_notification_service, get_classification_service
from app.db.database import engine
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.main import app
from app.schemas.reclamos import AgentClassificationResult
from app.services.claim_notifications import (
    ClaimNotificationService,
    SmtpClaimEmailSender,
)
from app.services.classification_service import ClassificationService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SUPABASE_INTEGRATION") != "1",
    reason="Requiere autorización explícita para probar Supabase.",
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "23_notificaciones_actor_responsable.sql"
)


def _migration_body() -> str:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    sql = re.sub(r"(?im)^\s*begin;\s*$", "", sql, count=1)
    sql = re.sub(r"(?im)^\s*commit;\s*$", "", sql, count=1)
    return sql


def _apply_migration_in_current_transaction(connection) -> None:
    installed = connection.execute(
        text("SELECT to_regclass('public.reclamo_responsables')")
    ).scalar_one()
    if installed is not None:
        return

    # SQLAlchemy entrega un mapping vacío a psycopg2 y este interpreta los
    # `%s` literales usados por pg_catalog.format como placeholders. La
    # ejecución DBAPI sin parámetros conserva el SQL exacto y participa de la
    # misma transacción exterior, que siempre se revierte al finalizar el QA.
    cursor = connection.connection.cursor()
    try:
        cursor.execute(_migration_body())
    finally:
        cursor.close()


def _claim_id(connection):
    return connection.execute(
        text(
            """
            SELECT r.id
            FROM reclamos r
            JOIN inquilinos i ON i.id = r.inquilino_id
            JOIN propiedades p ON p.id = r.propiedad_id
            JOIN propietarios pr ON pr.id = p.propietario_id
            ORDER BY r.creado_en, r.id
            FOR UPDATE OF r SKIP LOCKED
            LIMIT 1
            """
        )
    ).scalar_one_or_none()


class _ControlledOrdinaryGraph:
    def invoke(self, _: dict[str, object]) -> dict[str, object]:
        return {
            "tipo_gasto": "ordinario",
            "confianza": 0.95,
            "fundamento": "Caso controlado para validar la notificación de HU12.",
            "debe_escalar": False,
            "motivo_escalado": None,
            "estado_clasificacion": "clasificado",
            "actor_responsable": "inquilino",
            "notificacion_responsable_requerida": True,
        }


@pytest.mark.parametrize(
    ("expense_type", "actor", "expected_notifications"),
    [
        ("ordinario", "inquilino", 1),
        ("extraordinario", "propietario", 2),
        ("expensa", "inmobiliaria", 2),
    ],
)
def test_classification_persists_actor_and_outbox_atomically(
    expense_type: str,
    actor: str,
    expected_notifications: int,
) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            _apply_migration_in_current_transaction(connection)
            claim_id = _claim_id(connection)
            if claim_id is None:
                pytest.skip("No existe un reclamo apto para el QA transaccional.")

            repository = SqlAlchemyClaimsRepository(
                sessionmaker(
                    bind=connection,
                    join_transaction_mode="create_savepoint",
                )
            )
            persisted = repository.persist_classification(
                claim_id,
                AgentClassificationResult(
                    tipo_gasto=expense_type,
                    confianza=0.95,
                    fundamento="Clasificación sintética para QA transaccional.",
                    debe_escalar=False,
                    motivo_escalado=None,
                    estado_clasificacion="clasificado",
                    actor_responsable=actor,
                    notificacion_responsable_requerida=True,
                ),
            )

            assert persisted.response.estado == (
                "Pendiente de respuesta del responsable"
            )
            assert persisted.notification_id is not None
            responsibility = connection.execute(
                text(
                    """
                    SELECT actor_tipo, destinatario_contacto, canal,
                           recordatorio_programado_en - solicitado_en AS recordatorio,
                           respuesta_vence_en - solicitado_en AS vencimiento
                    FROM reclamo_responsables
                    WHERE reclamo_id = :claim_id
                    """
                ),
                {"claim_id": claim_id},
            ).mappings().one()
            assert responsibility["actor_tipo"] == actor
            assert responsibility["destinatario_contacto"]
            assert responsibility["canal"] in {"email", "whatsapp"}
            assert responsibility["recordatorio"].total_seconds() == 48 * 3600
            assert responsibility["vencimiento"].total_seconds() == 72 * 3600

            history_id = connection.execute(
                text(
                    """
                    SELECT id
                    FROM reclamo_historial_estados
                    WHERE reclamo_id = :claim_id
                      AND estado_nuevo = 'Pendiente de respuesta del responsable'
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"claim_id": claim_id},
            ).scalar_one()
            assert connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM notificaciones
                    WHERE historial_estado_id = :history_id
                    """
                ),
                {"history_id": history_id},
            ).scalar_one() == expected_notifications
        finally:
            transaction.rollback()


def test_due_jobs_enqueue_reminder_then_escalate_without_smtp() -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            _apply_migration_in_current_transaction(connection)
            claim_id = _claim_id(connection)
            if claim_id is None:
                pytest.skip("No existe un reclamo apto para el QA transaccional.")

            repository = SqlAlchemyClaimsRepository(
                sessionmaker(
                    bind=connection,
                    join_transaction_mode="create_savepoint",
                )
            )
            repository.persist_classification(
                claim_id,
                AgentClassificationResult(
                    tipo_gasto="ordinario",
                    confianza=0.95,
                    fundamento="Clasificación sintética para QA transaccional.",
                    debe_escalar=False,
                    motivo_escalado=None,
                    estado_clasificacion="clasificado",
                    actor_responsable="inquilino",
                    notificacion_responsable_requerida=True,
                ),
            )
            connection.execute(
                text(
                    """
                    UPDATE reclamo_responsables
                    SET solicitado_en = CURRENT_TIMESTAMP - interval '49 hours',
                        recordatorio_programado_en = CURRENT_TIMESTAMP - interval '2 hours',
                        respuesta_vence_en = CURRENT_TIMESTAMP + interval '22 hours'
                    WHERE reclamo_id = :claim_id
                    """
                ),
                {"claim_id": claim_id},
            )

            assert repository.enqueue_due_responsible_followups(limit=10) == 1
            assert connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM notificaciones
                    WHERE reclamo_id = :claim_id
                      AND tipo_evento = 'responsable_recordatorio'
                    """
                ),
                {"claim_id": claim_id},
            ).scalar_one() == 1

            connection.execute(
                text(
                    """
                    UPDATE reclamo_responsables
                    SET respuesta_vence_en = CURRENT_TIMESTAMP - interval '1 minute'
                    WHERE reclamo_id = :claim_id
                    """
                ),
                {"claim_id": claim_id},
            )
            repository.enqueue_due_responsible_followups(limit=10)

            assert connection.execute(
                text("SELECT estado FROM reclamos WHERE id = :claim_id"),
                {"claim_id": claim_id},
            ).scalar_one() == "Pendiente de respuesta - vencido"
            assert connection.execute(
                text(
                    """
                    SELECT escalado_en IS NOT NULL
                    FROM reclamo_responsables
                    WHERE reclamo_id = :claim_id
                    """
                ),
                {"claim_id": claim_id},
            ).scalar_one() is True
        finally:
            transaction.rollback()


@pytest.mark.skipif(
    os.getenv("RUN_HU12_SMTP_INTEGRATION") != "1",
    reason="Requiere autorización explícita para enviar un correo de prueba.",
)
def test_http_flow_persists_and_delivers_initial_notification_by_smtp() -> None:
    recipient = os.getenv("HU12_TEST_RECIPIENT", "").strip()
    if not recipient:
        pytest.skip("Falta HU12_TEST_RECIPIENT para el envío controlado.")

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            claim_id = _claim_id(connection)
            if claim_id is None:
                pytest.skip("No existe un reclamo apto para el QA transaccional.")

            connection.execute(
                text(
                    """
                    UPDATE inquilinos
                    SET email = :recipient,
                        canal_notificacion = 'email'
                    WHERE id = (
                        SELECT inquilino_id
                        FROM reclamos
                        WHERE id = :claim_id
                    )
                    """
                ),
                {"claim_id": claim_id, "recipient": recipient},
            )
            repository = SqlAlchemyClaimsRepository(
                sessionmaker(
                    bind=connection,
                    join_transaction_mode="create_savepoint",
                )
            )
            app.dependency_overrides[get_classification_service] = lambda: (
                ClassificationService(repository, _ControlledOrdinaryGraph())
            )
            app.dependency_overrides[get_claim_notification_service] = lambda: (
                ClaimNotificationService(repository, SmtpClaimEmailSender())
            )

            try:
                with TestClient(app) as client:
                    response = client.post(f"/reclamos/{claim_id}/clasificar")
            finally:
                app.dependency_overrides.clear()

            assert response.status_code == 200
            assert response.json()["estado"] == (
                "Pendiente de respuesta del responsable"
            )
            notification = connection.execute(
                text(
                    """
                    SELECT estado_envio, intentos, tipo_evento,
                           destinatario_contacto
                    FROM notificaciones
                    WHERE reclamo_id = :claim_id
                      AND tipo_evento = 'responsable_inicial'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"claim_id": claim_id},
            ).mappings().one()
            assert notification["estado_envio"] == "enviado"
            assert notification["intentos"] == 1
            assert notification["destinatario_contacto"] == recipient
        finally:
            app.dependency_overrides.clear()
            transaction.rollback()
