"""Controles estructurales locales; no reemplazan la ejecución en PostgreSQL."""

from pathlib import Path
import re


MIGRATIONS = Path(__file__).parents[1] / "migrations"
MIGRATION = MIGRATIONS / "18_revalidar_operador_al_escalar.sql"


def migration_sql():
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).strip()


def test_reopening_fix_is_incremental_and_transactional():
    sql = migration_sql()
    assert sql.startswith("BEGIN;") and sql.endswith("COMMIT;")
    assert "SET LOCAL lock_timeout = '5s';" in sql
    assert "SET LOCAL statement_timeout = '30s';" in sql
    previous = (MIGRATIONS / "17_usuarios_operadores.sql").read_text(encoding="utf-8")
    assert "UPDATE OF operador_asignado_id ON public.reclamos" in previous
    assert "UPDATE OF operador_asignado_id, estado ON public.reclamos" in sql


def test_reopening_fix_revalidates_both_assignment_and_escalation():
    sql = migration_sql()
    assert "NEW.operador_asignado_id IS NOT NULL" in sql
    assert "TG_OP = 'INSERT'" in sql
    assert "NEW.operador_asignado_id IS DISTINCT FROM OLD.operador_asignado_id" in sql
    assert "NEW.estado = 'Escalado' AND NEW.estado IS DISTINCT FROM OLD.estado" in sql
    assert "FOR SHARE;" in sql
    assert "rol = 'operador' AND activo" in sql
    assert "ERRCODE = '23514'" in sql


def test_reopening_fix_keeps_function_private_and_invoker():
    sql = migration_sql()
    assert "SECURITY INVOKER SET search_path = ''" in sql
    assert "REVOKE ALL ON FUNCTION public.validar_operador_asignado() FROM PUBLIC, anon, authenticated;" in sql
    assert "SECURITY DEFINER" not in sql.upper()
    assert not re.search(r"\bGRANT\b", sql, re.IGNORECASE)


def test_reopening_fix_detects_invalid_existing_assignments_without_rewriting_data():
    sql = migration_sql()
    assert "r.estado = 'Escalado' AND r.operador_asignado_id IS NOT NULL" in sql
    assert "u.id = r.operador_asignado_id AND u.rol = 'operador' AND u.activo" in sql
    assert "Revisar sus asignaciones antes de migrar." in sql
    assert not re.search(r"\b(?:UPDATE\s+public\.|DELETE\s+FROM\b|INSERT\s+INTO\b|TRUNCATE\b)",
                         sql, re.IGNORECASE)
