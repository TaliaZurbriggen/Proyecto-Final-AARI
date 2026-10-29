"""El ejecutor compartido nunca debe conectar sin autorización o a otro proyecto."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run(tmp_path, flags, *, optimized=False):
    command = [sys.executable] + (['-O'] if optimized else [])
    return subprocess.run(command + ['-m', 'scripts.check_hu33_shared', '--env-root', str(tmp_path), *flags],
                          cwd=ROOT, env={**os.environ, 'PYTHON_DOTENV_DISABLED': '1'},
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize('flags', [[], ['--authorized'], ['--validate']])
def test_requires_authorization_and_an_explicit_action(tmp_path, flags):
    result = run(tmp_path, flags)
    assert result.returncode == 2
    assert 'Requiere' in result.stderr
    assert 'migration' not in result.stdout


def test_refuses_disabled_assertions_before_reading_configuration(tmp_path):
    result = run(tmp_path, ['--authorized', '--validate'], optimized=True)
    assert result.returncode == 2
    assert 'No ejecutar con -O' in result.stderr


@pytest.mark.parametrize('value', ['postgresql://qa:fake-secret@not-authorized.invalid/test', 'not-a-url'])
def test_rejects_other_targets_without_showing_private_configuration(tmp_path, value):
    (tmp_path / '.env').write_text('DATABASE_URL=' + value + '\n', encoding='utf-8')
    result = run(tmp_path, ['--authorized', '--validate'])
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report['stage'] == 'configuration' and not report['success']
    assert value not in result.stdout + result.stderr
    assert 'fake-secret' not in result.stdout + result.stderr
