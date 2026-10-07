"""PR28: vigencia argentina y dos workers sobre PostgreSQL local descartable."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.clausulas_contrato import SqlAlchemyContractClausesRepository
from app.schemas.clausulas_contrato import ClauseReviewRequest, ExtractedClause
from app.services.contract_clause_service import ContractClauseService, PROMPT_VERSION
from app.services.contract_text_extraction import ContractText, PageText
from tests.test_responsible_actor_postgres import local_engine, claim_case  # noqa: F401


pytestmark = pytest.mark.skipif(
    not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Requiere PostgreSQL local dedicado.",
)


@pytest.fixture
def contract_case(claim_case):
    db, claims, claim_id = claim_case
    contract_id, actor = uuid4(), uuid4()
    with db.begin() as connection:
        participants = connection.execute(text("""
            SELECT r.inquilino_id, r.propiedad_id, p.propietario_id
            FROM reclamos r JOIN propiedades p ON p.id=r.propiedad_id WHERE r.id=:id
        """), {"id": claim_id}).mappings().one()
        connection.execute(text("""
            INSERT INTO usuarios (id,email,password_hash,rol,nombre_completo)
            VALUES (:id,'admin@example.com','not-a-credential','administrador','Administración Sintética')
        """), {"id": actor})
        connection.execute(text("""
            INSERT INTO contratos (id,inquilino_id,propiedad_id,propietario_id,fecha_inicio,fecha_fin,estado)
            VALUES (:id,:tenant,:property,:owner,'2026-01-01','2026-06-30','firmado')
        """), {"id": contract_id, "tenant": participants["inquilino_id"],
                "property": participants["propiedad_id"], "owner": participants["propietario_id"]})
    repository = SqlAlchemyContractClausesRepository(sessionmaker(bind=db))
    return db, claims, repository, claim_id, contract_id, actor


def add_document(db, contract_id, version):
    document_id = uuid4()
    with db.begin() as connection:
        connection.execute(text("""
            INSERT INTO contrato_documentos
                (id,contrato_id,version,storage_path,nombre_archivo,tamano,sha256,firmado)
            VALUES (:id,:contract,:version,:path,'synthetic.pdf',1,:hash,true)
        """), {"id": document_id, "contract": contract_id, "version": version,
                "path": f"private/synthetic-{version}.pdf", "hash": "a" * 64})
    return document_id


@pytest.mark.parametrize("server_zone", ["UTC", "Asia/Tokyo", "America/Argentina/Buenos_Aires"])
@pytest.mark.parametrize("finalized", [False, True], ids=["fin-pactado", "finalizacion-anticipada"])
def test_contract_dates_use_argentina_even_when_postgres_uses_another_zone(contract_case, server_zone, finalized):
    db, _, repository, claim_id, contract_id, actor = contract_case
    document = add_document(db, contract_id, 1)
    analysis = repository.request_analysis(contract_id, document, actor,
        extractor="test", prompt=PROMPT_VERSION, model="fake")
    claimed, = repository.claim_due(limit=1)
    clause = ExtractedClause(
        numero="PRIMERA", evidencias=[{"pagina": 1, "texto": "PRIMERA: Texto sintético."}],
        resumen="Obligación revisada.", categoria="mantenimiento", responsable="propietario",
        uso_clasificador="contexto", confianza=0,
    )
    repository.complete(analysis, pages=[{"pagina": 1, "metodo": "digital", "legible": True}],
                        clauses=[clause], rejected=[], complete=True,
                        incidents=[], execution_id=claimed.execution_id)
    row = repository.get(contract_id, analysis)["clausulas"][0]
    repository.review(contract_id, row["id"],
        ClauseReviewRequest(accion="editar", revision=1, uso_clasificador="operativa"), actor)
    if finalized:
        with db.begin() as connection:
            connection.execute(text("""
                UPDATE contratos SET estado='finalizado', fecha_fin='2026-12-31',
                    fecha_finalizacion='2026-06-30' WHERE id=:id
            """), {"id": contract_id})

    # Cada consulta usa una sesión con la zona indicada, independientemente del servidor.
    with db.connect() as connection:
        connection.execute(text("SELECT set_config('TimeZone', :zone, false)"), {"zone": server_zone})
        connection.commit()
        zoned = SqlAlchemyContractClausesRepository(sessionmaker(bind=connection))
        for instant, expected in (
            ("2026-01-01T02:59:59Z", 0),  # 31/12 23:59:59: todavía no comienza.
            ("2026-01-01T03:00:00Z", 1),  # 01/01 00:00:00: comienza.
            ("2026-07-01T01:00:00Z", 1),  # 30/06 22:00:00: sigue vigente.
            ("2026-07-01T02:59:59Z", 1),  # Último segundo del día final.
            ("2026-07-01T03:00:00Z", 0),  # 01/07 00:00:00: ya terminó.
        ):
            connection.execute(text("UPDATE reclamos SET creado_en=:instant WHERE id=:id"),
                               {"instant": instant, "id": claim_id})
            connection.commit()
            assert len(zoned.confirmed_for_claim(claim_id)) == expected


def test_only_the_current_unexpired_execution_can_renew(contract_case):
    db, _, repository, _, contract_id, actor = contract_case
    document = add_document(db, contract_id, 1)
    repository.request_analysis(contract_id, document, actor,
        extractor="test", prompt=PROMPT_VERSION, model="fake")
    job, = repository.claim_due(limit=1)
    assert repository.renew_lease(job.id, execution_id=job.execution_id)
    assert not repository.renew_lease(job.id, execution_id=uuid4())
    assert not repository.renew_lease(job.id, execution_id=None)
    with db.begin() as connection:
        connection.execute(text("""UPDATE contrato_analisis
            SET bloqueado_hasta=clock_timestamp()-interval '1 second' WHERE id=:id"""), {"id": job.id})
    assert not repository.renew_lease(job.id, execution_id=job.execution_id)
    recovered, = repository.claim_due(limit=1)
    assert recovered.execution_id != job.execution_id
    assert not repository.renew_lease(job.id, execution_id=job.execution_id)
    assert repository.renew_lease(job.id, execution_id=recovered.execution_id)


def test_three_jobs_with_two_workers_and_a_slow_model_are_sent_only_three_times(contract_case, monkeypatch):
    db, _, repository, _, contract_id, actor = contract_case
    for version in range(1, 4):
        document = add_document(db, contract_id, version)
        repository.request_analysis(contract_id, document, actor,
            extractor="test", prompt=PROMPT_VERSION, model="fake")
    monkeypatch.setattr("app.services.contract_clause_service.extract_contract_text",
        lambda *_: ContractText([PageText(1, "PRIMERA: Texto sintético.", "digital", True)], True))
    entered, renewed, release = Event(), Event(), Event()
    model = Mock()

    def response(_):
        if not entered.is_set():
            # Acercar el vencimiento para probar el heartbeat sin esperar 180 s.
            with db.begin() as connection:
                connection.execute(text("""UPDATE contrato_analisis SET
                    bloqueado_hasta=clock_timestamp()+interval '1 second' WHERE estado='procesando'"""))
            entered.set()
            assert release.wait(10)
        return {"clausulas": []}

    model.invoke.side_effect = response
    original_renew = repository.renew_lease

    def observed_renew(*args, **kwargs):
        result = original_renew(*args, **kwargs)
        if result and entered.is_set():
            renewed.set()
        return result

    repository.renew_lease = observed_renew
    storage = SimpleNamespace(download=lambda _: b"synthetic")
    first = ContractClauseService(repository, storage, model_factory=lambda: model, lease_interval_seconds=0.05)
    second = ContractClauseService(SqlAlchemyContractClausesRepository(sessionmaker(bind=db)),
                                   storage, model_factory=lambda: model)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first.process_due)
        try:
            assert entered.wait(5) and renewed.wait(5)
            assert second.process_due() == 2
            with db.connect() as connection:
                active, = connection.execute(text("""SELECT bloqueado_hasta FROM contrato_analisis
                    WHERE estado='procesando'""")).one()
            assert active > datetime.now(timezone.utc) + timedelta(seconds=100)
        finally:
            release.set()
        assert future.result(timeout=10) == 1
    assert model.invoke.call_count == 3
    with db.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM contrato_analisis_intentos")).scalar_one() == 3
        assert connection.execute(text("SELECT count(*) FROM contrato_analisis WHERE estado='completado'")).scalar_one() == 3


def test_notifications_snapshot_contract_context_and_still_block_reclassification(contract_case):
    db, claims, _, claim_id, _, _ = contract_case
    from app.services.classification_service import ClaimClassificationConflictError
    from tests.test_responsible_actor_postgres import classification, snapshot
    context = [{"id": "synthetic-clause", "resumen": "Regla revisada."}]
    result = claims.persist_classification(claim_id, classification("ordinario"), context)
    assert result.notification_id is not None
    with db.connect() as connection:
        assert connection.execute(text("""SELECT contexto_contractual_clasificacion
            FROM reclamos WHERE id=:id"""), {"id": claim_id}).scalar_one() == context
    before = snapshot(db, claim_id)
    with pytest.raises(ClaimClassificationConflictError):
        claims.persist_classification(claim_id, classification("extraordinario"), [])
    assert snapshot(db, claim_id) == before
