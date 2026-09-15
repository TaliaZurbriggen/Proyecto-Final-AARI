"""Garantías estructurales de la corrección de alertas por cancelaciones."""

from pathlib import Path
import re


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "22_corregir_alerta_cancelaciones.sql"
)
SQL = MIGRATION_PATH.read_text(encoding="utf-8")
SQL_LOWER = SQL.lower()


def test_correction_is_transactional_and_bounded() -> None:
    statements = [
        line.strip().lower()
        for line in SQL.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]

    assert statements[0] == "begin;"
    assert statements[-1] == "commit;"
    assert "set local lock_timeout = '5s';" in SQL_LOWER
    assert "set local statement_timeout = '30s';" in SQL_LOWER


def test_correction_replaces_the_existing_trigger_function_safely() -> None:
    assert (
        "create or replace function public.chk_alerta_cancelaciones()"
        in SQL_LOWER
    )
    assert "security invoker" in SQL_LOWER
    assert "set search_path = ''" in SQL_LOWER
    assert "security definer" not in SQL_LOWER
    assert "revoke all on function public.chk_alerta_cancelaciones()" in SQL_LOWER
    assert "from public, anon, authenticated" in SQL_LOWER
    assert not re.search(r"\bcreate\s+trigger\b", SQL, re.IGNORECASE)


def test_third_cancellation_notification_satisfies_the_delivery_contract() -> None:
    assert "from public.cancelaciones" in SQL_LOWER
    assert "where reclamo_id = new.reclamo_id" in SQL_LOWER
    assert "if v_total_cancelaciones >= 3 then" in SQL_LOWER
    assert "from public.reclamos as r" in SQL_LOWER

    insert_columns = SQL_LOWER.split(
        "insert into public.notificaciones (", maxsplit=1
    )[1].split(") values (", maxsplit=1)[0]
    for column in (
        "reclamo_id",
        "destinatario_tipo",
        "destinatario_contacto",
        "canal",
        "asunto",
        "mensaje",
        "estado_reclamo",
        "estado_envio",
        "proximo_intento_en",
    ):
        assert column in insert_columns

    assert "'operador@sistema'" in SQL_LOWER
    assert "'pendiente'" in SQL_LOWER
    assert "now()" in SQL_LOWER
