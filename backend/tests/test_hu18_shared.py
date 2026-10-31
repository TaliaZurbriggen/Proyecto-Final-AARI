"""Guardas del ejecutor HU18 y aplicación/QA sólo en PostgreSQL LOCAL."""

import os
import subprocess
import sys

import pytest
from sqlalchemy import text

from scripts import check_hu18_shared as runner
from tests.test_provider_choices_postgres import choice_base
from tests.test_quote_portal_postgres import portal_case
from tests.test_responsible_actor_postgres import claim_case, local_engine


@pytest.mark.parametrize('raw', [
    f'postgresql://postgres@db.{runner.PROJECT_REF}.supabase.co/postgres',
    f'postgresql://postgres.{runner.PROJECT_REF}@aws-0-sa-east-1.pooler.supabase.com/postgres',
])
def test_expected_targets(raw):
    assert runner.target_url(raw).get_backend_name() == 'postgresql'


@pytest.mark.parametrize('raw', ['sqlite://', 'postgresql://postgres@localhost/postgres',
    'postgresql://postgres.other@aws-0-sa-east-1.pooler.supabase.com/postgres',
    f'postgresql://postgres@db.{runner.PROJECT_REF}.supabase.co.other/postgres'])
def test_rejects_other_targets(raw):
    with pytest.raises(RuntimeError):
        runner.target_url(raw)


def test_authorization_checked_before_reading_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['check', '--env-root', str(tmp_path), '--apply'])
    monkeypatch.setattr(runner, 'dotenv_values', lambda *_: pytest.fail('No debe leer configuración sin autorización.'))
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def test_optimized_interpreter_rejected_before_connection(tmp_path):
    result = subprocess.run([sys.executable, '-O', '-m', 'scripts.check_hu18_shared', '--authorized',
        '--env-root', str(tmp_path), '--apply'], capture_output=True, text=True,
        env={**os.environ, 'PYTHON_DOTENV_DISABLED': '1'}, timeout=20)
    assert result.returncode == 2 and 'No ejecutar con -O' in result.stderr


def test_configuration_error_does_not_expose_values(monkeypatch, tmp_path, capsys):
    (tmp_path / '.env').touch()
    marker = 'CONFIGURATION_MUST_NOT_APPEAR'
    monkeypatch.setattr(sys, 'argv', ['check', '--authorized', '--env-root', str(tmp_path)])
    monkeypatch.setattr(runner, 'dotenv_values', lambda *_: {'DATABASE_URL': marker})
    monkeypatch.setattr(runner, 'create_engine', lambda *_args, **_kwargs: pytest.fail('No debe conectar.'))
    with pytest.raises(SystemExit):
        runner.main()
    output = capsys.readouterr()
    assert marker not in output.out + output.err
    assert '"success": false' in output.out


@pytest.fixture
def deployment_case(portal_case):
    with portal_case.db.begin() as connection:
        connection.execute(text('CREATE SCHEMA supabase_migrations'))
        connection.execute(text('CREATE TABLE supabase_migrations.schema_migrations(version text primary key,name text,statements text[])'))
        connection.execute(text("INSERT INTO proveedores_externos(reclamo_id,propiedad_id,nombre,telefono) SELECT id,propiedad_id,'Contacto Legado','12345678' FROM reclamos"))
    return portal_case


local = pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'), reason='Sólo PostgreSQL local descartable.')


@local
def test_apply_preserves_rows_and_second_invocation_does_not_repeat(deployment_case):
    with deployment_case.db.begin() as connection:
        before = runner.fingerprints(connection)
        assert not runner.installation_state(connection)
        assert runner.apply(connection)
        runner.verify(connection)
        assert runner.fingerprints(connection) == before
        assert not runner.apply(connection)
        assert connection.execute(text('SELECT count(*) FROM supabase_migrations.schema_migrations')).scalar_one() == 1
        assert connection.execute(text('SELECT count(*) FROM proveedores_externos WHERE usuario_id IS NULL')).scalar_one() == 1


@local
def test_failure_rolls_back_ddl_and_history(deployment_case, monkeypatch):
    with deployment_case.db.connect() as connection:
        outer = connection.begin()
        baseline = runner.fingerprints(connection)
        outer.rollback()
    def fail(_connection):
        raise RuntimeError('Fallo sintético de verificación.')
    monkeypatch.setattr(runner, 'verify', fail)
    with pytest.raises(RuntimeError), deployment_case.db.begin() as connection:
        runner.apply(connection)
    with deployment_case.db.connect() as connection:
        assert not runner.installation_state(connection)
        assert runner.fingerprints(connection) == baseline


@local
def test_real_repository_checks_rollback_and_preserve_claim_sequence(deployment_case):
    with deployment_case.db.begin() as connection:
        runner.apply(connection)
    with deployment_case.db.connect() as connection:
        outer = connection.begin()
        baseline = runner.fingerprints(connection)
        sequence = connection.execute(text('SELECT last_value,is_called FROM reclamos_numero_seq')).one()
        passed = []
        try:
            runner.run_cases(connection, passed)
            assert len(passed) == 2 and outer.is_active
        finally:
            outer.rollback()
        assert runner.fingerprints(connection) == baseline
        assert connection.execute(text('SELECT last_value,is_called FROM reclamos_numero_seq')).one() == sequence
