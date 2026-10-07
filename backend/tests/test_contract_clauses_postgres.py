"""HU30: migración y repositorio real en esquema aislado con rollback."""

import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.clausulas_contrato import SqlAlchemyContractClausesRepository
from app.schemas.clausulas_contrato import (
    ClauseReviewRequest, ExtractedClause, RejectedClause,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CLAUSES_POSTGRES_TESTS") != "1",
    reason="Requiere autorización explícita para probar SQL en Supabase con rollback.",
)


def uid(n):
    return UUID(f"00000000-0000-0000-0000-{n:012d}")


def test_migration_worker_review_context_rls_and_rollback():
    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 10})
    schema = "aari319_test_" + uuid4().hex
    scripts = []
    for migration in (
        "23_clausulas_contractuales.sql",
        "24_evidencia_clausulas_contractuales.sql",
        "25_extraccion_asistida_literal.sql",
    ):
        sql = (Path(__file__).parents[1] / "migrations" / migration).read_text(encoding="utf-8")
        sql = "\n".join(line for line in sql.splitlines() if line.strip() not in {"begin;", "commit;"})
        scripts.append(sql.replace("public.", f'"{schema}".'))
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path = "{schema}", public'))
            for ddl in [
                "CREATE TABLE usuarios (id uuid PRIMARY KEY)",
                """CREATE TABLE contratos (id uuid PRIMARY KEY, inquilino_id uuid,
                    propiedad_id uuid, fecha_inicio date, fecha_fin date,
                    fecha_finalizacion date, estado text)""",
                """CREATE TABLE contrato_documentos (id uuid PRIMARY KEY,
                    contrato_id uuid REFERENCES contratos(id), version integer,
                    storage_path text, firmado boolean)""",
                """CREATE TABLE reclamos (id uuid PRIMARY KEY, inquilino_id uuid,
                    propiedad_id uuid, creado_en timestamptz)""",
            ]:
                connection.execute(text(ddl))
            for sql in scripts:
                connection.exec_driver_sql(sql)
            for n in (1, 2):
                connection.execute(text("INSERT INTO usuarios VALUES (:id)"), {"id": uid(n)})
            contract_id, document_id, claim_id = uid(10), uid(11), uid(12)
            connection.execute(text("""
                INSERT INTO contratos VALUES (:id,:tenant,:property,'2026-01-01','2026-12-31',NULL,'firmado')
            """), {"id": contract_id, "tenant": uid(20), "property": uid(30)})
            connection.execute(text("""
                INSERT INTO contrato_documentos VALUES (:id,:contract,1,'private/test.pdf',true)
            """), {"id": document_id, "contract": contract_id})
            connection.execute(text("""
                INSERT INTO reclamos (id,inquilino_id,propiedad_id,creado_en)
                VALUES (:id,:tenant,:property,'2026-06-01T12:00:00Z')
            """), {"id": claim_id, "tenant": uid(20), "property": uid(30)})

            factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
            repository = SqlAlchemyContractClausesRepository(factory)
            analysis_id = repository.request_analysis(
                contract_id, document_id, uid(1), extractor="test", prompt="v1", model="fake"
            )
            assert repository.request_analysis(
                contract_id, document_id, uid(1), extractor="test", prompt="v1", model="fake"
            ) == analysis_id
            job = repository.claim_due(limit=1)[0]
            clause = ExtractedClause(
                numero="NOVENA",
                evidencias=[{"pagina": 1, "texto": "Texto contractual sintético."}],
                resumen="Responsabilidad condicionada.", categoria="danio",
                responsable="condicional", uso_clasificador="operativa",
                condiciones="Si existe culpa.", confianza=0.9,
            )
            context_clause = ExtractedClause(
                numero="PRIMERA",
                evidencias=[{"pagina": 1, "texto": "Texto contractual sintético."}],
                resumen="Inventario contextual.", categoria="otro",
                responsable="no_especificado", uso_clasificador="contexto",
                condiciones=None, confianza=0.8,
            )
            rejected = RejectedClause(
                ordinal=3, propuesta=context_clause,
                motivo="el fragmento no es literal.",
                evidencias_invalidas=context_clause.evidencias,
            )
            assert repository.complete(
                job.id, pages=[{"pagina": 1, "metodo": "digital", "legible": True}],
                clauses=[clause, context_clause], rejected=[rejected],
                complete=True, incidents=["Una propuesta requiere revisión."],
                execution_id=job.execution_id,
            )
            stored = repository.get(contract_id, analysis_id)
            assert stored["propuestas_rechazadas"][0]["ordinal"] == 3
            assert stored["clausulas"][0]["evidencias"][0]["pagina"] == 1
            assert stored["clausulas"][0]["uso_clasificador"] == "contexto"
            assert stored["clausulas"][0]["habilitada_para_reclamos"] is False
            reviewed = repository.review(
                contract_id, stored["clausulas"][0]["id"],
                ClauseReviewRequest(accion="confirmar", revision=1), uid(1),
            )
            repository.review(
                contract_id, stored["clausulas"][1]["id"],
                ClauseReviewRequest(accion="confirmar", revision=1), uid(1),
            )
            assert reviewed["clausulas"][0]["estado_revision"] == "confirmada"
            assert reviewed["clausulas"][0]["habilitada_para_reclamos"] is False
            assert repository.confirmed_for_claim(claim_id) == []
            enabled = repository.review(
                contract_id, stored["clausulas"][0]["id"],
                ClauseReviewRequest(
                    accion="editar", revision=2, uso_clasificador="operativa",
                ), uid(1),
            )
            assert enabled["clausulas"][0]["habilitada_para_reclamos"] is True
            context = repository.confirmed_for_claim(claim_id)
            assert len(context) == 1 and context[0]["documento_version"] == 1
            assert context[0]["responsable"] == "condicional"

            # El respaldo literal se incorpora sin borrar ni reemplazar lo revisado.
            with pytest.raises(Exception):
                repository.request_analysis(contract_id, document_id, uid(1),
                    extractor="asistida", prompt="v10", model="fake", mode="ia")
            assert repository.request_analysis(contract_id, document_id, uid(1),
                extractor="asistida", prompt="sin-interpretacion", model="local", mode="literal") == analysis_id
            literal_job = repository.claim_due(limit=1)[0]
            assert literal_job.mode == "literal" and literal_job.execution_id != job.execution_id
            # Una respuesta atrasada del primer intento se audita, pero no modifica filas.
            assert repository.complete(job.id, pages=[], clauses=[], rejected=[],
                complete=True, incidents=[], execution_id=job.execution_id) is False
            literal = ExtractedClause(numero="SEXTA", evidencias=[{"pagina": 2, "texto": "SEXTA: Texto local."}],
                resumen="Interpretación pendiente.", categoria="otro", responsable="no_especificado",
                uso_clasificador="contexto", confianza=0)
            assert repository.complete(literal_job.id, pages=[{"pagina": 1, "metodo": "digital", "legible": True},
                {"pagina": 2, "metodo": "digital", "legible": True}], clauses=[literal], rejected=[],
                complete=True, incidents=[], origins=["literal"], execution_id=literal_job.execution_id)
            after_literal = repository.get(contract_id, analysis_id)
            assert after_literal["clausulas"][0]["id"] == stored["clausulas"][0]["id"]
            assert after_literal["clausulas"][0]["revision"] == 3
            assert after_literal["clausulas"][0]["habilitada_para_reclamos"] is True
            assert len(after_literal["clausulas"]) == 3
            assert len(after_literal["historial_intentos"]) == 2
            assert after_literal["propuestas_rechazadas"] == stored["propuestas_rechazadas"]
            assert len(repository.confirmed_for_claim(claim_id)) == 1
            # No se repite automáticamente un respaldo completado.
            repository.request_analysis(contract_id, document_id, uid(1),
                extractor="asistida", prompt="sin-interpretacion", model="local", mode="literal")
            assert repository.claim_due(limit=1) == []
            # Un error anterior a la migración 25 conserva su snapshot al reintentar.
            legacy_doc, legacy_analysis = uid(41), uid(42)
            connection.execute(text("""INSERT INTO contrato_documentos VALUES
                (:id,:contract,2,'private/legacy.pdf',true)"""), {"id": legacy_doc, "contract": contract_id})
            connection.execute(text("""INSERT INTO contrato_analisis
                (id,contrato_id,documento_id,estado,extractor_version,prompt_version,modelo,intentos,ultimo_error)
                VALUES (:id,:contract,:doc,'fallido','antiguo','v4','fake',1,'Error anterior preservado.')
            """), {"id": legacy_analysis, "contract": contract_id, "doc": legacy_doc})
            repository.request_analysis(contract_id, legacy_doc, uid(1),
                extractor="asistida", prompt="sin-interpretacion", model="local", mode="literal")
            legacy = repository.get(contract_id, legacy_analysis)
            assert legacy["historial_intentos"][0]["error"] == "Error anterior preservado."
            legacy_job = repository.claim_due(limit=1)[0]
            assert repository.fail(legacy_job.id, legacy_job.attempt_number,
                "Error local controlado.", execution_id=legacy_job.execution_id)
            assert repository.claim_due(limit=1) == []  # Sin reintentos automáticos por falla.
            assert len(repository.get(contract_id, legacy_analysis)["historial_intentos"]) == 2

            unrelated_claim_id, expired_claim_id = uid(13), uid(14)
            connection.execute(text("""
                INSERT INTO reclamos (id,inquilino_id,propiedad_id,creado_en)
                VALUES (:id,:tenant,:property,'2026-06-01T12:00:00Z')
            """), {"id": unrelated_claim_id, "tenant": uid(20), "property": uid(31)})
            connection.execute(text("""
                INSERT INTO reclamos (id,inquilino_id,propiedad_id,creado_en)
                VALUES (:id,:tenant,:property,'2027-01-01T12:00:00Z')
            """), {"id": expired_claim_id, "tenant": uid(20), "property": uid(30)})
            assert repository.confirmed_for_claim(unrelated_claim_id) == []
            assert repository.confirmed_for_claim(expired_claim_id) == []

            security = connection.execute(text("""
                SELECT c.relname, c.relrowsecurity,
                    has_table_privilege('anon', c.oid, 'SELECT'),
                    has_table_privilege('authenticated', c.oid, 'SELECT')
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=:schema AND c.relname IN
                    ('contrato_analisis','contrato_clausulas','contrato_clausula_eventos','contrato_analisis_intentos')
            """), {"schema": schema}).all()
            assert len(security) == 4 and all(row[1:] == (True, False, False) for row in security)
        finally:
            transaction.rollback()
        assert connection.execute(text(
            "SELECT count(*) FROM pg_namespace WHERE nspname=:schema"
        ), {"schema": schema}).scalar_one() == 0
    engine.dispose()
