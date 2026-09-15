"""QA transaccional optativo del historial y las notificaciones de HU10."""

import os
from typing import get_args

import pytest
from sqlalchemy import text

from app.db.database import engine
from app.schemas.reclamos import EstadoReclamo


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SUPABASE_INTEGRATION") != "1",
    reason="Requiere autorización explícita para probar Supabase.",
)


def test_every_status_transition_creates_one_history_and_notification() -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            claim = connection.execute(
                text(
                    """
                    SELECT r.id, r.estado
                    FROM reclamos r
                    JOIN inquilinos i ON i.id = r.inquilino_id
                    WHERE r.operador_asignado_id IS NULL
                      AND i.canal_notificacion = 'email'
                    ORDER BY r.creado_en ASC
                    FOR UPDATE OF r SKIP LOCKED
                    LIMIT 1
                    """
                )
            ).mappings().one_or_none()
            if claim is None:
                pytest.skip("No existe un reclamo apto para el QA transaccional.")

            connection.execute(
                text("SELECT set_config('app.origen_reclamo', 'sistema', true)")
            )
            original_status = str(claim["estado"])
            statuses = [
                status
                for status in get_args(EstadoReclamo)
                if status != original_status
            ]
            statuses.append(original_status)
            previous_status = original_status

            for next_status in statuses:
                previous_history_ids = set(
                    connection.execute(
                        text(
                            """
                            SELECT id
                            FROM reclamo_historial_estados
                            WHERE reclamo_id = :claim_id
                            """
                        ),
                        {"claim_id": claim["id"]},
                    ).scalars()
                )

                connection.execute(
                    text(
                        """
                        UPDATE reclamos
                        SET estado = :next_status
                        WHERE id = :claim_id
                        """
                    ),
                    {"claim_id": claim["id"], "next_status": next_status},
                )

                histories = connection.execute(
                    text(
                        """
                        SELECT id, estado_anterior, estado_nuevo, origen
                        FROM reclamo_historial_estados
                        WHERE reclamo_id = :claim_id
                        """
                    ),
                    {"claim_id": claim["id"]},
                ).mappings()
                new_histories = [
                    history
                    for history in histories
                    if history["id"] not in previous_history_ids
                ]
                assert len(new_histories) == 1
                history = new_histories[0]
                assert history["estado_anterior"] == previous_status
                assert history["estado_nuevo"] == next_status
                assert history["origen"] == "sistema"

                notification = connection.execute(
                    text(
                        """
                        SELECT estado_reclamo, estado_envio, canal
                        FROM notificaciones
                        WHERE historial_estado_id = :history_id
                          AND destinatario_tipo = 'inquilino'
                        """
                    ),
                    {"history_id": history["id"]},
                ).mappings().one()
                assert notification["estado_reclamo"] == next_status
                assert notification["estado_envio"] == "pendiente"
                assert notification["canal"] == "email"
                previous_status = next_status
        finally:
            transaction.rollback()


def test_third_cancellation_is_saved_and_queues_a_complete_alert() -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            claim = connection.execute(
                text(
                    """
                    SELECT r.id, r.estado, r.numero
                    FROM reclamos r
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM cancelaciones c
                        WHERE c.reclamo_id = r.id
                    )
                    ORDER BY r.creado_en ASC
                    FOR UPDATE OF r SKIP LOCKED
                    LIMIT 1
                    """
                )
            ).mappings().one_or_none()
            if claim is None:
                pytest.skip(
                    "No existe un reclamo sin cancelaciones para el QA transaccional."
                )

            previous_notification_ids = set(
                connection.execute(
                    text(
                        """
                        SELECT id
                        FROM notificaciones
                        WHERE reclamo_id = :claim_id
                          AND destinatario_tipo = 'operador'
                        """
                    ),
                    {"claim_id": claim["id"]},
                ).scalars()
            )

            for expected_count in (1, 2):
                connection.execute(
                    text(
                        """
                        INSERT INTO cancelaciones (reclamo_id, etapa)
                        VALUES (:claim_id, 'esperando_presupuestos')
                        """
                    ),
                    {"claim_id": claim["id"]},
                )
                assert connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM cancelaciones
                        WHERE reclamo_id = :claim_id
                        """
                    ),
                    {"claim_id": claim["id"]},
                ).scalar_one() == expected_count
                current_notification_ids = set(
                    connection.execute(
                        text(
                            """
                            SELECT id
                            FROM notificaciones
                            WHERE reclamo_id = :claim_id
                              AND destinatario_tipo = 'operador'
                            """
                        ),
                        {"claim_id": claim["id"]},
                    ).scalars()
                )
                assert current_notification_ids == previous_notification_ids

            connection.execute(
                text(
                    """
                    INSERT INTO cancelaciones (reclamo_id, etapa)
                    VALUES (:claim_id, 'esperando_presupuestos')
                    """
                ),
                {"claim_id": claim["id"]},
            )

            assert connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM cancelaciones
                    WHERE reclamo_id = :claim_id
                    """
                ),
                {"claim_id": claim["id"]},
            ).scalar_one() == 3

            notifications = connection.execute(
                text(
                    """
                    SELECT id, asunto, estado_reclamo, estado_envio,
                           proximo_intento_en, canal
                    FROM notificaciones
                    WHERE reclamo_id = :claim_id
                      AND destinatario_tipo = 'operador'
                    """
                ),
                {"claim_id": claim["id"]},
            ).mappings()
            new_notifications = [
                notification
                for notification in notifications
                if notification["id"] not in previous_notification_ids
            ]

            assert len(new_notifications) == 1
            notification = new_notifications[0]
            assert notification["asunto"] == (
                f"AARI - Reclamo #{int(claim['numero']):06d} "
                "con cancelaciones reiteradas"
            )
            assert notification["estado_reclamo"] == claim["estado"]
            assert notification["estado_envio"] == "pendiente"
            assert notification["proximo_intento_en"] is not None
            assert notification["canal"] == "email"
        finally:
            transaction.rollback()
