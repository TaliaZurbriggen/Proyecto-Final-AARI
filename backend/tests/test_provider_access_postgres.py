"""HU32 real en PostgreSQL LOCAL descartable. Nunca Supabase/SMTP/Gemini."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db.provider_access import SqlAlchemyProviderAccessRepository
from app.db.usuarios import SqlAlchemyUsuariosRepository
from app.api.auth import get_auth_service
from app.main import app
from app.schemas.auth import LoginRequest
from app.schemas.provider_access import ProviderActivationRequest, ProviderInvitationRequest
from app.services.auth_service import AuthService, InactiveAccountError
from app.services.provider_access_service import ProviderAccessError, ProviderAccessService, invitation_digest


pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="PostgreSQL local dedicado.")
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
NOW = datetime(2026, 10, 26, 18, tzinfo=UTC)


@pytest.fixture
def case():
    url = make_url(os.environ["AARI_TEST_POSTGRES_URL"])
    assert url.host in {"localhost", "127.0.0.1", "::1"} and url.get_backend_name() == "postgresql"
    name = "aari_hu32_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.exec_driver_sql("""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
        END $$;""")
        c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(url.set(database=name))
    try:
        for filename in ("01_modulo_administracion.sql", "13_autenticacion_usuarios.sql",
                         "20261026180000_hu32_rol_proveedor.sql", "20261026180100_hu32_acceso_proveedor.sql"):
            with engine.connect() as c:
                cursor = c.connection.cursor()
                cursor.execute((MIGRATIONS / filename).read_text(encoding="utf-8"))
                c.connection.commit()  # cursor DBAPI: confirmar realmente antes del enum siguiente.
                cursor.close()
        with engine.begin() as c:
            provider = c.execute(text("""
                INSERT INTO proveedores(nombre_razon_social,telefono)
                VALUES ('Servicio Sintetico','+540000000001') RETURNING id
            """)).scalar_one()
        repo = SqlAlchemyProviderAccessRepository(sessionmaker(bind=engine))
        messages = []
        class Sender:
            def send(self, delivery): messages.append(delivery)
        yield engine, repo, ProviderAccessService(repo, Sender()), provider, messages
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


def invite(case, **kwargs):
    engine, repo, service, provider, messages = case
    request = ProviderInvitationRequest(email=kwargs.pop("email", "service@example.com"), request_id=kwargs.pop("request_id", uuid4()))
    result = service.invite(provider, request, now=kwargs.pop("now", NOW))
    return request, result


def activate(case, token=None, **kwargs):
    engine, repo, service, provider, messages = case
    service.activate(ProviderActivationRequest(token=token or messages[-1].token,
        password_nueva="PruebaLocal123", confirmacion_password="PruebaLocal123"), now=kwargs.pop("now", NOW))


def count(engine, table):
    assert table in {"usuarios", "proveedor_invitaciones"}
    with engine.connect() as c:
        return c.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_legacy_provider_is_preserved_and_no_account_is_created(case):
    engine, repo, service, provider, messages = case
    assert service.get(provider, now=NOW).estado == "sin_acceso"
    assert count(engine, "usuarios") == count(engine, "proveedor_invitaciones") == 0


def test_inactive_legacy_provider_has_no_account_and_cannot_be_invited(case):
    engine, repo, service, provider, _ = case
    with engine.begin() as c:
        c.execute(text('UPDATE proveedores SET activo=false WHERE id=:id'), {'id': provider})
    result = service.get(provider, now=NOW)
    assert result.estado == 'sin_acceso' and not result.puede_invitar


def test_full_activation_login_profile_and_deactivation(case):
    engine, repo, service, provider, messages = case
    _, response = invite(case)
    assert response.estado == "pendiente" and response.envio_estado == "enviado"
    assert response.vence_en == NOW + timedelta(hours=24)
    with engine.connect() as c:
        row = c.execute(text("SELECT * FROM proveedor_invitaciones")).mappings().one()
        assert row["token_hash"] == invitation_digest(messages[-1].token)
        assert messages[-1].token not in str(dict(row))
    activate(case)
    auth = AuthService(SqlAlchemyUsuariosRepository(sessionmaker(bind=engine)))
    user = auth.login(LoginRequest(email="service@example.com", password="PruebaLocal123"))
    assert user.rol == "proveedor" and user.perfil_id == provider and not user.primer_ingreso
    assert service.profile(user).proveedor_id == provider
    assert service.get(provider, now=NOW).estado == "activo"
    with engine.begin() as c:
        c.execute(text("UPDATE proveedores SET activo=false WHERE id=:id"), {"id": provider})
    with pytest.raises(InactiveAccountError): auth.get_active_user(user.id)
    with pytest.raises(ProviderAccessError): service.profile(user)
    assert count(engine, "usuarios") == 1


def test_replay_does_not_create_account_or_duplicate_email(case):
    engine, repo, service, provider, messages = case
    request, _ = invite(case)
    service.invite(provider, request, now=NOW)
    assert count(engine, "usuarios") == count(engine, "proveedor_invitaciones") == len(messages) == 1


def test_resend_revokes_previous_and_email_can_change_before_activation(case):
    engine, repo, service, provider, messages = case
    invite(case)
    old = messages[-1].token
    invite(case, email="new@example.com")
    with pytest.raises(ProviderAccessError): activate(case, old)
    activate(case)
    assert service.get(provider, now=NOW).email == "new@example.com"
    assert count(engine, "usuarios") == 1 and count(engine, "proveedor_invitaciones") == 2


@pytest.mark.parametrize("hours", [24, 25])
def test_expiry_is_inclusive_and_does_not_consume_invitation(case, hours):
    engine, repo, service, provider, messages = case
    invite(case)
    with pytest.raises(ProviderAccessError): activate(case, now=NOW + timedelta(hours=hours))
    assert service.get(provider, now=NOW+timedelta(hours=hours)).estado == "vencido"
    with engine.connect() as c:
        assert c.execute(text("SELECT usado_en FROM proveedor_invitaciones")).scalar_one() is None


def test_used_and_invalid_token_are_rejected(case):
    invite(case)
    with pytest.raises(ProviderAccessError): activate(case, "z"*43)
    activate(case)
    with pytest.raises(ProviderAccessError): activate(case)


@pytest.mark.parametrize("role", ["administrador", "inquilino", "propietario", "operador"])
def test_email_used_by_other_role_is_not_reassigned(case, role):
    engine, repo, service, provider, messages = case
    with engine.begin() as c:
        c.execute(text("INSERT INTO usuarios(email,password_hash,rol) VALUES ('service@example.com','unused',:role)"), {"role": role})
    with pytest.raises(ProviderAccessError, match="correo"):
        invite(case)
    assert count(engine, "usuarios") == 1 and count(engine, "proveedor_invitaciones") == 0
    assert service.get(provider, now=NOW).estado == "sin_acceso"


def test_active_account_email_cannot_be_changed(case):
    invite(case)
    activate(case)
    with pytest.raises(ProviderAccessError, match="activada"):
        invite(case, email="new@example.com")


def test_deactivated_provider_cannot_be_invited_or_activated(case):
    engine, repo, service, provider, messages = case
    invite(case)
    with engine.begin() as c:
        c.execute(text("UPDATE proveedores SET activo=false WHERE id=:id"), {"id": provider})
    with pytest.raises(ProviderAccessError): invite(case)
    with pytest.raises(ProviderAccessError): activate(case)
    assert service.get(provider, now=NOW).estado == "desactivado"


def test_concurrent_activation_has_only_one_winner(case):
    invite(case)
    start = Barrier(2)
    def run(_):
        start.wait(timeout=5)
        try:
            activate(case)
            return True
        except ProviderAccessError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == [False, True]


def test_concurrent_resends_keep_one_account_and_one_usable_token(case):
    engine, repo, service, provider, messages = case
    start = Barrier(2)
    def run(_):
        start.wait(timeout=5)
        return invite(case)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, range(2)))
    assert count(engine, "usuarios") == 1
    with engine.connect() as c:
        valid = c.execute(text("SELECT count(*) FROM proveedor_invitaciones WHERE revocado_en IS NULL AND usado_en IS NULL")).scalar_one()
    assert valid == 1


def test_cross_provider_profile_is_forbidden_and_db_rejects_wrong_role(case):
    engine, repo, service, provider, messages = case
    invite(case)
    activate(case)
    auth = AuthService(SqlAlchemyUsuariosRepository(sessionmaker(bind=engine)))
    user = auth.login(LoginRequest(email="service@example.com", password="PruebaLocal123"))
    with pytest.raises(ProviderAccessError): service.profile(user.model_copy(update={"perfil_id": uuid4()}))
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text("UPDATE usuarios SET rol='administrador' WHERE id=:id"), {"id": user.id})
    assert auth.get_active_user(user.id).rol == "proveedor"


def test_rls_and_no_public_policy_and_no_raw_token_column(case):
    engine, *_ = case
    with engine.connect() as c:
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='proveedor_invitaciones'::regclass")).scalar_one()
        assert c.execute(text("SELECT count(*) FROM pg_policies WHERE tablename='proveedor_invitaciones'")).scalar_one() == 0
        cols = c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='proveedor_invitaciones'" )).scalars().all()
        assert "token_hash" in cols and "token" not in cols


def test_cookie_session_is_denied_immediately_when_provider_is_deactivated(case, monkeypatch):
    engine, repo, service, provider, messages = case
    invite(case)
    activate(case)
    monkeypatch.setenv("JWT_SECRET", "local-testing-secret-with-more-than-32-characters")
    app.dependency_overrides[get_auth_service] = lambda: AuthService(SqlAlchemyUsuariosRepository(sessionmaker(bind=engine)))
    try:
        client = TestClient(app)
        assert client.post('/auth/login', json={'email': 'service@example.com', 'password': 'PruebaLocal123'}).status_code == 200
        assert client.get('/auth/me').status_code == 200
        with engine.begin() as c:
            c.execute(text('UPDATE proveedores SET activo=false WHERE id=:id'), {'id': provider})
        assert client.get('/auth/me').status_code == 401
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_concurrent_same_email_for_two_providers_rolls_back_loser(case):
    engine, repo, service, provider, messages = case
    with engine.begin() as c:
        other = c.execute(text("INSERT INTO proveedores(nombre_razon_social,telefono) VALUES ('Otro Servicio','+540000000002') RETURNING id")).scalar_one()
    start = Barrier(2)
    def run(pid):
        start.wait(timeout=5)
        try:
            service.invite(pid, ProviderInvitationRequest(email='service@example.com', request_id=uuid4()), now=NOW)
            return True
        except ProviderAccessError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, [provider, other])) == [False, True]
    assert count(engine, 'usuarios') == count(engine, 'proveedor_invitaciones') == 1
