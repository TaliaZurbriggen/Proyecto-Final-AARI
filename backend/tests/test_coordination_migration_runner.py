"""Guardas del aplicador HU21, sin leer .env reales ni contactar Supabase."""

from pathlib import Path
import sys

import pytest
from scripts import apply_hu21_shared as runner


def configure(monkeypatch, value, *, authorized=True):
    args = ["apply_hu21_shared", "--env-root", "synthetic-env"]
    if authorized:
        args.append("--authorized")
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    monkeypatch.setattr(runner, "dotenv_values", lambda _: value)
    def no_connection(**kwargs):
        raise AssertionError("Una entrada rechazada nunca debe conectarse.")
    monkeypatch.setattr(runner.psycopg, "connect", no_connection)


def test_requires_explicit_authorization_before_reading_config(monkeypatch):
    configure(monkeypatch,{},authorized=False)
    monkeypatch.setattr(runner,"dotenv_values",
                        lambda _: (_ for _ in ()).throw(AssertionError("No leer configuración")))
    with pytest.raises(SystemExit,match="autorización humana"):
        runner.main()


def test_missing_url_is_safe(monkeypatch):
    configure(monkeypatch,{})
    with pytest.raises(SystemExit,match="no disponible"):
        runner.main()


def test_malformed_url_is_not_echoed(monkeypatch):
    marker = "synthetic-sensitive-marker"
    configure(monkeypatch,{"DATABASE_URL":marker})
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert marker not in str(error.value)


@pytest.mark.parametrize("url",[
    "postgresql://test@db.otherproject.supabase.co/postgres",
    f"postgresql://test@db.{runner.PROJECT_REF}.supabase.co.invalid/postgres",
    f"postgresql://postgres.{runner.PROJECT_REF}@untrusted.invalid/postgres",
    "postgresql://postgres.other@aws-0-test.pooler.supabase.com/postgres",
])
def test_wrong_or_lookalike_destination_never_connects(monkeypatch,url):
    configure(monkeypatch,{"DATABASE_URL":url})
    with pytest.raises(SystemExit,match="no coincide"):
        runner.main()
