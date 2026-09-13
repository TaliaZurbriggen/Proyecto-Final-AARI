"""HU29: repositorio real (SQLite) + servicio/API; Storage doble, sin red."""
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfWriter
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.contratos import contract_user, get_contracts_service
from app.db.contratos import SqlAlchemyContractsRepository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.contratos import ContractCreate, ContractEnd, ContractUpdate
from app.services.contract_errors import ContractError, ContractHistoryError, preserve_contract_history
from app.services.contracts_service import ContractsService, MAX_PDF_SIZE, validate_pdf


def uid(n):
    return f"00000000-0000-0000-0000-{n:012d}"


def user(n=1, role="administrador"):
    return AuthenticatedUser(id=UUID(uid(n)), email=f"role{n}@example.com",
                             rol=role, primer_ingreso=False)


@pytest.fixture
def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    statements = [
        "CREATE TABLE usuarios (id TEXT PRIMARY KEY)",
        "CREATE TABLE propietarios (id TEXT PRIMARY KEY, usuario_id TEXT, nombre_completo TEXT)",
        "CREATE TABLE propiedades (id TEXT PRIMARY KEY, propietario_id TEXT, direccion TEXT, localidad TEXT, provincia TEXT)",
        "CREATE TABLE inquilinos (id TEXT PRIMARY KEY, usuario_id TEXT, propiedad_id TEXT, nombre_completo TEXT)",
        """CREATE TABLE contratos (
            id TEXT PRIMARY KEY, inquilino_id TEXT REFERENCES inquilinos(id) ON DELETE RESTRICT,
            propietario_id TEXT REFERENCES propietarios(id) ON DELETE RESTRICT,
            propiedad_id TEXT REFERENCES propiedades(id) ON DELETE RESTRICT,
            contrato_anterior_id TEXT REFERENCES contratos(id),
            fecha_inicio DATE NOT NULL, fecha_fin DATE NOT NULL, fecha_finalizacion DATE,
            estado TEXT DEFAULT 'borrador', revision INTEGER DEFAULT 1, creado_por TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE contrato_documentos (
            id TEXT PRIMARY KEY, contrato_id TEXT REFERENCES contratos(id), version INTEGER,
            storage_path TEXT UNIQUE, nombre_archivo TEXT, tamano INTEGER, sha256 TEXT,
            firmado BOOLEAN, creado_por TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(contrato_id, version))""",
        """CREATE TABLE contrato_eventos (
            id TEXT PRIMARY KEY, contrato_id TEXT REFERENCES contratos(id), accion TEXT,
            revision INTEGER, actor_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    ]
    with engine.begin() as c:
        c.execute(text("PRAGMA foreign_keys=ON"))
        for statement in statements:
            c.execute(text(statement))
        for n in range(1, 7):
            c.execute(text("INSERT INTO usuarios VALUES (:id)"), {"id": uid(n)})
        for n in (2, 4):
            c.execute(text("INSERT INTO propietarios VALUES (:id, :id, :name)"),
                      {"id": uid(n), "name": f"Propietario sintético {n}"})
        c.execute(text("INSERT INTO propiedades VALUES (:id, :owner, 'Inmueble de prueba 123', 'Localidad', 'Provincia')"),
                  {"id": uid(20), "owner": uid(2)})
        c.execute(text("INSERT INTO inquilinos VALUES (:id, :id, :property, 'Inquilino sintético')"),
                  {"id": uid(3), "property": uid(20)})
        c.execute(text("INSERT INTO inquilinos VALUES (:id, :id, NULL, 'Otro inquilino')"), {"id": uid(5)})
    factory = sessionmaker(engine)
    repo = SqlAlchemyContractsRepository(factory)
    storage = Mock()
    storage.signed_url.return_value = "https://example.invalid/private.pdf?token=temporary"
    service = ContractsService(repo, storage, today=lambda: date(2026, 9, 12))
    yield SimpleNamespace(service=service, repo=repo, storage=storage, engine=engine)
    engine.dispose()


def draft(setup, start="2026-09-01", end="2027-08-31", **extra):
    return setup.service.create(ContractCreate(inquilino_id=uid(3), propiedad_id=uid(20),
                                               fecha_inicio=start, fecha_fin=end, **extra), user())


def upload(setup, contract, pdf, signed=True):
    return setup.service.upload(contract.id, user(), content=pdf, filename="contrato.pdf",
                                content_type="application/pdf", signed=signed, revision=contract.revision)


def test_draft_without_pdf_is_private_and_keeps_owner(setup):
    contract = draft(setup)
    assert contract.estado == "borrador" and contract.documentos == []
    assert contract.propietario_id == UUID(uid(2))
    for actor in (user(3, "inquilino"), user(2, "propietario"), user(5, "inquilino")):
        assert setup.service.list(actor).total == 0
        with pytest.raises(ContractError) as err:
            setup.service.get(contract.id, actor)
        assert err.value.status == 404
    setup.storage.upload.assert_not_called()


def test_versions_confirmation_and_no_internal_data_leak(setup, pdf):
    contract = upload(setup, draft(setup), pdf, signed=False)
    old_draft_id = contract.documentos[0].id
    contract = upload(setup, contract, pdf)
    contract = upload(setup, contract, pdf)
    assert [d.version for d in contract.documentos] == [3, 2, 1]
    assert contract.estado == "firmado"
    for actor in (user(2, "propietario"), user(3, "inquilino")):
        own = setup.service.get(contract.id, actor)
        assert [d.version for d in own.documentos] == [3, 2]
        assert "storage_path" not in own.model_dump_json()
        assert "sha256" not in own.model_dump_json()
        with pytest.raises(ContractError):
            setup.service.download(contract.id, old_draft_id, actor)
    with setup.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM contrato_eventos")).scalar_one() == 4


@pytest.mark.parametrize("role,n", [("inquilino", 5), ("propietario", 4), ("operador", 6)])
def test_unrelated_users_cannot_read_or_download(setup, pdf, role, n):
    contract = upload(setup, draft(setup), pdf)
    actor = user(n, role)
    assert setup.service.list(actor, propiedad_id=uid(20)).total == 0
    with pytest.raises(ContractError) as err:
        setup.service.download(contract.id, contract.documentos[0].id, actor)
    assert err.value.status == 404
    setup.storage.signed_url.assert_not_called()


@pytest.mark.parametrize("role,n", [("inquilino", 3), ("propietario", 2), ("operador", 6)])
def test_participants_cannot_write_even_their_own_contract(setup, pdf, role, n):
    contract = draft(setup)
    actor = user(n, role)
    operations = [
        lambda: setup.service.create(ContractCreate(inquilino_id=uid(3), propiedad_id=uid(20), fecha_inicio="2026-09-01", fecha_fin="2027-08-31"), actor),
        lambda: setup.service.update(contract.id, ContractUpdate(fecha_inicio="2026-09-02", fecha_fin="2027-08-31", revision=1), actor),
        lambda: setup.service.upload(contract.id, actor, content=pdf, filename="x.pdf", content_type="application/pdf", signed=True, revision=1),
        lambda: setup.service.end(contract.id, ContractEnd(fecha_finalizacion="2026-09-11", revision=1), actor),
    ]
    for operation in operations:
        with pytest.raises(ContractError) as err:
            operation()
        assert err.value.status == 403
    setup.storage.upload.assert_not_called()


def test_access_survives_disassociation_and_owner_change_but_not_transferred(setup, pdf):
    contract = upload(setup, draft(setup), pdf)
    with setup.engine.begin() as c:
        c.execute(text("UPDATE inquilinos SET propiedad_id=NULL WHERE id=:id"), {"id": uid(3)})
        c.execute(text("UPDATE propiedades SET propietario_id=:id"), {"id": uid(4)})
        c.execute(text("UPDATE inquilinos SET propiedad_id=:p WHERE id=:id"), {"p": uid(20), "id": uid(5)})
    assert setup.service.get(contract.id, user(3, "inquilino")).id == contract.id
    assert setup.service.get(contract.id, user(2, "propietario")).id == contract.id
    assert setup.service.list(user(4, "propietario")).total == 0
    assert setup.service.list(user(5, "inquilino")).total == 0


def test_overlap_inclusive_and_compensation(setup, pdf):
    first = upload(setup, draft(setup), pdf)
    collision = draft(setup, start="2027-08-31", end="2028-08-31")
    with pytest.raises(ContractError) as err:
        upload(setup, collision, pdf)
    assert err.value.code == "contract_overlap"
    setup.storage.delete.assert_called_once()
    assert setup.service.get(collision.id, user()).documentos == []
    assert setup.service.get(collision.id, user()).estado == "borrador"
    renewal = draft(setup, start="2027-09-01", end="2028-08-31", contrato_anterior_id=first.id)
    assert upload(setup, renewal, pdf).estado == "firmado"


def test_dates_immutable_after_confirmation_and_stale_edit_rejected(setup, pdf):
    initial = draft(setup)
    changed = setup.service.update(initial.id, ContractUpdate(fecha_inicio="2026-08-31", fecha_fin="2027-08-31", revision=1), user())
    assert changed.revision == 2
    with pytest.raises(ContractError) as err:
        upload(setup, initial, pdf)
    assert err.value.code == "contract_stale"
    setup.storage.upload.assert_not_called()
    signed = upload(setup, changed, pdf)
    with pytest.raises(ContractError) as err:
        setup.service.update(signed.id, ContractUpdate(fecha_inicio="2026-09-02", fecha_fin="2027-08-31", revision=signed.revision), user())
    assert err.value.code == "contract_immutable"
    with pytest.raises(ContractError):
        upload(setup, signed, pdf, signed=False)


def test_finalization_and_renewal_preserve_history(setup, pdf):
    contract = upload(setup, draft(setup), pdf)
    with pytest.raises(ContractError):
        setup.service.end(contract.id, ContractEnd(fecha_finalizacion="2026-09-13", revision=contract.revision), user())
    ended = setup.service.end(contract.id, ContractEnd(fecha_finalizacion="2026-09-11", revision=contract.revision), user())
    assert ended.vigencia == "Finalizado"
    assert len(ended.documentos) == 1 and ended.fecha_fin == date(2027, 8, 31)
    with pytest.raises(ContractError):
        upload(setup, ended, pdf)
    renewed = upload(setup, draft(setup, start="2026-09-12", end="2027-09-11", contrato_anterior_id=ended.id), pdf)
    assert renewed.contrato_anterior_id == ended.id
    assert setup.service.list(user(3, "inquilino")).total == 2


@pytest.mark.parametrize("start,end,label", [
    ("2026-09-01", "2027-08-31", "Vigente"),
    ("2027-09-01", "2028-08-31", "Próximo a iniciar"),
    ("2025-09-01", "2026-08-31", "Vencido"),
])
def test_vigencia_derived_from_dates(setup, pdf, start, end, label):
    assert upload(setup, draft(setup, start=start, end=end), pdf).vigencia == label


def test_mismatched_parties_and_invalid_previous_rejected(setup):
    with pytest.raises(ContractError):
        setup.service.create(ContractCreate(inquilino_id=uid(5), propiedad_id=uid(20), fecha_inicio="2026-09-01", fecha_fin="2027-08-31"), user())
    previous = draft(setup)
    with pytest.raises(ContractError):
        draft(setup, start="2027-09-01", end="2028-08-31", contrato_anterior_id=previous.id)


@pytest.mark.parametrize("start,end", [("2026-09-01", "2026-09-01"), ("2027-01-01", "2026-01-01")])
def test_invalid_dates_schema(start, end):
    with pytest.raises(ValidationError):
        ContractCreate(inquilino_id=uid(3), propiedad_id=uid(20), fecha_inicio=start, fecha_fin=end)


@pytest.mark.parametrize("content,filename,mime", [
    (b"", "a.pdf", "application/pdf"),
    (b"not-pdf", "a.pdf", "application/pdf"),
    (b"%PDF-invalid", "a.pdf", "application/pdf"),
    (b"%PDF-1.7", "a.exe", "application/pdf"),
    (b"%PDF-1.7", "a.pdf", "text/html"),
    (b"x" * (MAX_PDF_SIZE + 1), "a.pdf", "application/pdf"),
], ids=["empty", "wrong_magic", "corrupt", "extension", "mime", "oversize"])
def test_invalid_files(content, filename, mime):
    with pytest.raises(ContractError) as err:
        validate_pdf(content, filename, mime)
    assert err.value.field == "archivo"


def test_encrypted_pdf_and_empty_pages_rejected():
    for encrypted in (False, True):
        writer = PdfWriter()
        if encrypted:
            writer.add_blank_page(width=10, height=10)
            writer.encrypt("test-only")
        output = BytesIO()
        writer.write(output)
        with pytest.raises(ContractError):
            validate_pdf(output.getvalue(), "a.pdf", "application/pdf")


def test_pdf_filename_normalized(pdf):
    assert validate_pdf(pdf, "../../contrato.pdf", "application/pdf") == "contrato.pdf"


def test_storage_failure_never_creates_document(setup, pdf):
    contract = draft(setup)
    setup.storage.upload.side_effect = ContractError("Storage no disponible", status=503)
    with pytest.raises(ContractError):
        upload(setup, contract, pdf)
    stored = setup.service.get(contract.id, user())
    assert stored.revision == 1 and stored.documentos == []


def test_uncertain_commit_keeps_persisted_object(setup, pdf, monkeypatch):
    original = setup.repo.save_document
    def uncertain(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("connection lost after commit")
    monkeypatch.setattr(setup.repo, "save_document", uncertain)
    contract = draft(setup)
    with pytest.raises(OSError):
        upload(setup, contract, pdf)
    setup.storage.delete.assert_not_called()
    assert len(setup.service.get(contract.id, user()).documentos) == 1


def test_post_commit_read_failure_does_not_delete_object(setup, pdf, monkeypatch):
    contract = draft(setup)
    original = setup.repo.get
    calls = 0
    def get(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("read unavailable")
        return original(*args)
    monkeypatch.setattr(setup.repo, "get", get)
    with pytest.raises(OSError):
        upload(setup, contract, pdf)
    setup.storage.delete.assert_not_called()


@pytest.mark.parametrize("table", ["inquilinos", "propiedades", "propietarios"])
def test_foreign_keys_protect_history(setup, table):
    draft(setup)
    with pytest.raises(IntegrityError), setup.engine.begin() as c:
        c.execute(text(f"DELETE FROM {table}"))


@pytest.mark.parametrize("fk", ["contratos_inquilino_id_fkey", "contratos_propiedad_id_fkey", "contratos_propietario_id_fkey"])
def test_delete_fk_translated(fk):
    @preserve_contract_history
    def operation():
        cause = Exception()
        cause.diag = SimpleNamespace(constraint_name=fk)
        raise IntegrityError("delete", {}, cause)
    with pytest.raises(ContractHistoryError) as err:
        operation()
    assert err.value.status == 409


def test_api_upload_download_and_access_guards(setup, pdf):
    actor = user()
    app.dependency_overrides[contract_user] = lambda: actor
    app.dependency_overrides[get_contracts_service] = lambda: setup.service
    try:
        client = TestClient(app)
        response = client.post("/contratos", json={"inquilino_id": uid(3), "propiedad_id": uid(20), "fecha_inicio": "2026-09-01", "fecha_fin": "2027-08-31"})
        assert response.status_code == 201
        cid = response.json()["id"]
        response = client.post(f"/contratos/{cid}/documentos", data={"firmado": "true", "revision": "1"}, files={"archivo": ("contrato.pdf", pdf, "application/pdf")})
        assert response.status_code == 200
        did = response.json()["documentos"][0]["id"]
        assert "storage_path" not in response.text
        actor = user(3, "inquilino")
        response = client.post(f"/contratos/{cid}/documentos/{did}/descarga")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["expires_in"] == 300
        assert client.patch(f"/contratos/{cid}", json={"fecha_inicio": "2026-09-02", "fecha_fin": "2027-08-31", "revision": 2}).status_code == 403
        actor = user(5, "inquilino")
        assert client.get(f"/contratos/{cid}").status_code == 404
        actor = user()
        response = client.post(f"/contratos/{cid}/documentos", data={"firmado": "true", "revision": "2"}, files={"archivo": ("x.pdf", b"x" * (MAX_PDF_SIZE + 1), "application/pdf")})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(contract_user, None)
        app.dependency_overrides.pop(get_contracts_service, None)


def test_api_without_login_is_unauthorized():
    assert TestClient(app).get("/contratos").status_code == 401
