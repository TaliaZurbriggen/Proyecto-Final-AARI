"""Guardas del comprobador compartido, sin conexiones ni credenciales reales."""
import re

import pytest

from scripts import check_visits_postgres as checker


@pytest.mark.parametrize('url', [
    'sqlite:///:memory:',
    'postgresql://qa@example.com/aari',
    'postgresql://qa@db.supabase.co.example.com/aari',
    'postgresql://qa@supabase.co/aari',
])
def test_configure_rejects_non_supabase_destinations(monkeypatch, url):
    monkeypatch.setattr(checker, 'dotenv_values', lambda _: {'DATABASE_URL': url})

    def forbidden(*args, **kwargs):
        raise AssertionError('Un destino rechazado no debe abrir un motor.')

    monkeypatch.setattr(checker, 'create_engine', forbidden)
    with pytest.raises(ValueError, match='Supabase'):
        checker.configure('archivo-local-no-leido')


def test_configure_hides_parameters_and_limits_connection_time(monkeypatch):
    monkeypatch.setattr(checker, 'dotenv_values', lambda _: {
        'DATABASE_URL': 'postgresql://qa@db.qa.supabase.co/aari',
        'JWT_SECRET': 'valor-ficticio-no-utilizado',
    })
    received = {}
    sentinel = object()

    def create(url, **kwargs):
        received.update(url=url, **kwargs)
        return sentinel

    monkeypatch.setattr(checker, 'create_engine', create)
    assert checker.configure('archivo-local-no-leido') is sentinel
    assert received['url'].host == 'db.qa.supabase.co'
    assert received['hide_parameters'] is True
    assert received['connect_args'] == {'connect_timeout': 10}


@pytest.mark.parametrize('version,name,_', checker.MIGRATIONS)
def test_migration_body_uses_the_outer_transaction(version, name, _):
    sql = checker.body(version, name)
    assert sql.strip()
    assert not re.search(r'(?im)^\s*(?:BEGIN|COMMIT);\s*$', sql)
