"""Garantías estructurales de la migración de accesos."""

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "14_acceso_propietarios_inquilinos.sql"
)


def test_access_migration_has_explicit_transaction_boundaries() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    statements = [
        line.strip().lower()
        for line in sql.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]

    assert statements[0] == "begin;"
    assert statements[-1] == "commit;"
