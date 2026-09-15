"""Garantías estructurales locales de la migración HU10."""

from pathlib import Path
import re
from typing import get_args

from app.schemas.reclamos import EstadoReclamo


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "21_actualizaciones_estado_reclamo.sql"
)
SQL = MIGRATION_PATH.read_text(encoding="utf-8")
SQL_LOWER = SQL.lower()


def test_migration_is_transactional_and_bounded() -> None:
    statements = [
        line.strip().lower()
        for line in SQL.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]

    assert statements[0] == "begin;"
    assert statements[-1] == "commit;"
    assert "set local lock_timeout = '5s';" in SQL_LOWER
    assert "set local statement_timeout = '30s';" in SQL_LOWER


def test_migration_models_delivery_queue_and_three_attempts() -> None:
    for column in (
        "asunto",
        "estado_reclamo",
        "historial_estado_id",
        "proximo_intento_en",
        "bloqueado_hasta",
    ):
        assert f"add column if not exists {column}" in SQL_LOWER

    assert "'pendiente', 'procesando', 'enviado', 'fallido'" in SQL_LOWER
    assert "check (intentos between 0 and 3)" in SQL_LOWER
    assert "idx_notificaciones_entrega_pendiente" in SQL_LOWER
    assert "where estado_envio in ('pendiente', 'procesando') and intentos < 3" in SQL_LOWER


def test_migration_notifies_real_transitions_once_without_duplicating_creation() -> None:
    assert "create trigger trg_notificar_cambio_estado_reclamo" in SQL_LOWER
    assert "when (new.estado_anterior is not null)" in SQL_LOWER
    assert "uq_notificaciones_cambio_inquilino" in SQL_LOWER
    assert "historial_estado_id" in SQL_LOWER
    assert "on conflict (historial_estado_id, destinatario_tipo)" in SQL_LOWER
    assert "where historial_estado_id is not null" in SQL_LOWER
    assert "insert into public.reclamos" not in SQL_LOWER


def test_migration_preserves_origin_context_and_private_execution() -> None:
    assert "current_setting('app.origen_reclamo', true)" in SQL_LOWER
    assert "current_setting('app.usuario_reclamo', true)" in SQL_LOWER
    assert SQL_LOWER.count("security invoker") == 2
    assert SQL_LOWER.count("set search_path = ''") == 2
    assert "security definer" not in SQL_LOWER
    assert not re.search(r"\bgrant\b", SQL, re.IGNORECASE)
    assert "enable row level security" in SQL_LOWER
    assert "from public, anon, authenticated" in SQL_LOWER


def test_migration_defaults_to_email_and_keeps_whatsapp_explicit() -> None:
    assert "canal_notificacion text not null default 'email'" in SQL_LOWER
    assert "check (canal_notificacion in ('email', 'whatsapp'))" in SQL_LOWER
    assert "when v_canal = 'whatsapp' then v_telefono" in SQL_LOWER


def test_migration_supports_every_declared_claim_status() -> None:
    statuses = get_args(EstadoReclamo)

    for status in statuses:
        assert f"'{status.lower()}'" in SQL_LOWER
    for status in set(statuses) - {"Recibido"}:
        assert f"when '{status.lower()}' then" in SQL_LOWER
