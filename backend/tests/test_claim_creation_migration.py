"""Controles estructurales de la migración HU8 sin ejecutar Supabase."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "19_alta_reclamos.sql"
).read_text(encoding="utf-8").lower()


def test_migration_is_transactional_and_does_not_invent_a_specialty():
    assert "begin;" in MIGRATION
    assert "commit;" in MIGRATION
    assert "alter column tipo_id drop not null" in MIGRATION
    assert "insert into public.especialidades" not in MIGRATION


def test_migration_guards_human_number_and_one_active_claim():
    assert "reclamos_numero_seq" in MIGRATION
    assert "uq_reclamos_numero" in MIGRATION
    assert "uq_reclamos_inquilino_propiedad_activo" in MIGRATION
    assert "'resuelto', 'resuelto (sin confirmación)'" in MIGRATION


def test_migration_configures_private_limited_photo_bucket():
    assert "'reclamos-fotos'" in MIGRATION
    assert "false," in MIGRATION
    assert "5242880" in MIGRATION
    assert "array['image/jpeg', 'image/png']" in MIGRATION
