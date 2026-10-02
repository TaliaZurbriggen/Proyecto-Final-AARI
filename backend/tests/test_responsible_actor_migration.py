"""Garantías estructurales de la migración de AARI-135."""

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "23_notificaciones_actor_responsable.sql"
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


def test_migration_models_responsibility_and_idempotency() -> None:
    assert "create table public.reclamo_responsables" in SQL_LOWER
    assert "uq_notificaciones_clave_idempotencia" in SQL_LOWER
    assert "recordatorio_programado_en" in SQL_LOWER
    assert "respuesta_vence_en" in SQL_LOWER
    assert "responsable_inicial" in SQL_LOWER
    assert "responsable_recordatorio" in SQL_LOWER
    assert "responsable_vencido" in SQL_LOWER


def test_migration_keeps_the_new_table_private() -> None:
    assert "alter table public.reclamo_responsables enable row level security" in SQL_LOWER
    assert (
        "revoke all on table public.reclamo_responsables from anon, authenticated"
        in SQL_LOWER
    )
    assert "security definer" not in SQL_LOWER


def test_migration_supports_consolidating_the_tenant_notification() -> None:
    assert "app.omitir_notificacion_inquilino" in SQL_LOWER
    assert "current_setting" in SQL_LOWER
    assert "security invoker" in SQL_LOWER
    assert "set search_path = ''" in SQL_LOWER


def test_due_work_has_partial_indexes() -> None:
    assert "idx_reclamo_responsables_recordatorio_pendiente" in SQL_LOWER
    assert "where recordatorio_generado_en is null and escalado_en is null" in SQL_LOWER
    assert "idx_reclamo_responsables_vencimiento_pendiente" in SQL_LOWER
    assert "where escalado_en is null" in SQL_LOWER


def test_existing_cancellation_alerts_keep_their_event_type() -> None:
    assert "create or replace function public.chk_alerta_cancelaciones()" in SQL_LOWER
    assert "'alerta_operador'" in SQL_LOWER
    assert "new.id" in SQL_LOWER
