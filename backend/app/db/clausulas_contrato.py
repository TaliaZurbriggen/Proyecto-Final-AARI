"""Persistencia durable del análisis y la revisión contractual."""

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import text

from app.db.database import SessionLocal
from app.schemas.clausulas_contrato import (
    ClauseReviewRequest, ExtractedClause, RejectedClause,
)
from app.services.contract_errors import ContractError


MAX_ANALYSIS_ATTEMPTS = 3
ANALYSIS_LEASE_SECONDS = 180
ANALYSIS_RETRY_SECONDS = 60


@dataclass(frozen=True)
class AnalysisJob:
    id: UUID
    contract_id: UUID
    document_id: UUID
    storage_path: str
    attempt_number: int


def _json(value):
    if value is None or isinstance(value, (dict, list)):
        return value
    return json.loads(value)


class SqlAlchemyContractClausesRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def document_for_analysis(self, contract_id, document_id):
        with self.session_factory() as session:
            row = session.execute(text("""
                SELECT d.id, d.contrato_id, d.storage_path, d.version, d.firmado
                FROM contrato_documentos d
                JOIN contratos c ON c.id = d.contrato_id
                WHERE d.id=:document_id AND d.contrato_id=:contract_id
                  AND d.firmado=true AND c.estado <> 'borrador'
            """), {"document_id": str(document_id), "contract_id": str(contract_id)}).mappings().one_or_none()
        if row is None:
            raise ContractError(
                "Seleccioná una versión firmada del contrato.",
                code="contract_document_not_analyzable", status=409,
            )
        return dict(row)

    def request_analysis(self, contract_id, document_id, actor, *, extractor, prompt, model):
        analysis_id = str(uuid4())
        with self.session_factory.begin() as session:
            existing = session.execute(text("""
                SELECT a.id, a.estado,
                    EXISTS (
                        SELECT 1 FROM contrato_clausulas cl
                        WHERE cl.analisis_id=a.id AND cl.estado_revision<>'pendiente'
                    ) AS tiene_revision
                FROM contrato_analisis a WHERE a.documento_id=:document_id
                FOR UPDATE
            """), {"document_id": str(document_id)}).mappings().one_or_none()
            if existing:
                if existing["estado"] in {"fallido", "incompleto"}:
                    if existing["tiene_revision"]:
                        raise ContractError(
                            "El análisis ya tiene cláusulas revisadas y no puede reemplazarse.",
                            code="analysis_reviewed", status=409,
                        )
                    session.execute(text(
                        "DELETE FROM contrato_clausulas WHERE analisis_id=:id"
                    ), {"id": str(existing["id"])})
                    session.execute(text("""
                        UPDATE contrato_analisis
                        SET estado='pendiente', intentos=0, completo=false,
                            ultimo_error=NULL, paginas_total=NULL,
                            lectura_paginas='[]'::jsonb,
                            propuestas_rechazadas='[]'::jsonb,
                            proximo_intento_en=CURRENT_TIMESTAMP, bloqueado_hasta=NULL,
                            iniciado_en=NULL, finalizado_en=NULL,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=:id
                    """), {"id": str(existing["id"])})
                return UUID(str(existing["id"]))
            session.execute(text("""
                INSERT INTO contrato_analisis
                    (id, contrato_id, documento_id, extractor_version, prompt_version,
                     modelo, solicitado_por)
                VALUES
                    (:id, :contract_id, :document_id, :extractor, :prompt, :model, :actor)
            """), {
                "id": analysis_id, "contract_id": str(contract_id),
                "document_id": str(document_id), "extractor": extractor,
                "prompt": prompt, "model": model, "actor": str(actor),
            })
        return UUID(analysis_id)

    def get_for_document(self, contract_id, document_id):
        with self.session_factory() as session:
            row = session.execute(text("""
                SELECT * FROM contrato_analisis
                WHERE contrato_id=:contract_id AND documento_id=:document_id
            """), {"contract_id": str(contract_id), "document_id": str(document_id)}).mappings().one_or_none()
            return self._with_clauses(session, row) if row else None

    def get(self, contract_id, analysis_id):
        with self.session_factory() as session:
            row = session.execute(text("""
                SELECT * FROM contrato_analisis
                WHERE id=:id AND contrato_id=:contract_id
            """), {"id": str(analysis_id), "contract_id": str(contract_id)}).mappings().one_or_none()
            if row is None:
                raise ContractError("No encontramos el análisis solicitado.", status=404)
            return self._with_clauses(session, row)

    @staticmethod
    def _with_clauses(session, row):
        result = dict(row)
        result["lectura_paginas"] = _json(result.get("lectura_paginas")) or []
        result["propuestas_rechazadas"] = _json(
            result.get("propuestas_rechazadas")
        ) or []
        clauses = session.execute(text("""
            SELECT id, ordinal, numero, titulo, paginas, texto_original, resumen,
                   categoria, responsable, condiciones, referencias, confianza,
                   evidencias, uso_clasificador, estado_revision, revision,
                   revisado_por, revisado_en
            FROM contrato_clausulas WHERE analisis_id=:id ORDER BY ordinal
        """), {"id": str(result["id"])}).mappings().all()
        result["clausulas"] = []
        for row_clause in clauses:
            clause = dict(row_clause)
            clause["paginas"] = _json(clause["paginas"]) or []
            clause["referencias"] = _json(clause["referencias"]) or []
            clause["evidencias"] = _json(clause["evidencias"]) or []
            clause["confianza"] = float(clause["confianza"])
            result["clausulas"].append(clause)
        return result

    def claim_due(self, *, limit=3):
        with self.session_factory.begin() as session:
            session.execute(text("""
                UPDATE contrato_analisis
                SET estado='fallido', ultimo_error=coalesce(
                    ultimo_error, 'El análisis se interrumpió durante el último intento.'),
                    bloqueado_hasta=NULL, updated_at=CURRENT_TIMESTAMP
                WHERE estado='procesando' AND intentos>=3
                  AND bloqueado_hasta<=CURRENT_TIMESTAMP
            """))
            rows = session.execute(text("""
                WITH candidates AS (
                    SELECT id FROM contrato_analisis
                    WHERE intentos < 3 AND (
                        (estado='pendiente' AND proximo_intento_en<=CURRENT_TIMESTAMP)
                        OR (estado='procesando' AND bloqueado_hasta<=CURRENT_TIMESTAMP)
                    )
                    ORDER BY proximo_intento_en, created_at
                    FOR UPDATE SKIP LOCKED LIMIT :limit
                )
                UPDATE contrato_analisis a
                SET estado='procesando', intentos=a.intentos+1,
                    bloqueado_hasta=CURRENT_TIMESTAMP + make_interval(secs=>:lease),
                    iniciado_en=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                FROM candidates c, contrato_documentos d
                WHERE a.id=c.id AND d.id=a.documento_id
                RETURNING a.id, a.contrato_id, a.documento_id, d.storage_path, a.intentos
            """), {"limit": max(1, min(limit, 10)), "lease": ANALYSIS_LEASE_SECONDS}).mappings().all()
        return [AnalysisJob(UUID(str(row["id"])), UUID(str(row["contrato_id"])),
                            UUID(str(row["documento_id"])), str(row["storage_path"]),
                            int(row["intentos"])) for row in rows]

    def complete(
        self, analysis_id, *, pages, clauses: list[ExtractedClause],
        rejected: list[RejectedClause], complete, incidents,
    ):
        with self.session_factory.begin() as session:
            current = session.execute(text("""
                SELECT estado FROM contrato_analisis WHERE id=:id FOR UPDATE
            """), {"id": str(analysis_id)}).mappings().one_or_none()
            if current is None or current["estado"] != "procesando":
                return False
            session.execute(text("DELETE FROM contrato_clausulas WHERE analisis_id=:id"), {"id": str(analysis_id)})
            for ordinal, clause in enumerate(clauses, start=1):
                original = clause.model_dump(mode="json")
                session.execute(text("""
                    INSERT INTO contrato_clausulas
                        (id, analisis_id, ordinal, numero, titulo, paginas,
                         texto_original, resumen, categoria, responsable, condiciones,
                         referencias, confianza, evidencias, uso_clasificador,
                         propuesta_original)
                    VALUES
                        (:id, :analysis_id, :ordinal, :numero, :titulo, CAST(:paginas AS jsonb),
                         :texto_original, :resumen, :categoria, :responsable, :condiciones,
                         CAST(:referencias AS jsonb), :confianza, CAST(:evidencias AS jsonb),
                         :uso_clasificador, CAST(:original AS jsonb))
                """), {
                    **original, "id": str(uuid4()), "analysis_id": str(analysis_id),
                    "ordinal": ordinal, "paginas": json.dumps(clause.paginas),
                    "referencias": json.dumps(clause.referencias),
                    "evidencias": json.dumps(original["evidencias"], ensure_ascii=False),
                    "original": json.dumps(original, ensure_ascii=False),
                })
            safe_error = " ".join(incidents)[:1000] or None
            session.execute(text("""
                UPDATE contrato_analisis
                SET estado=:state, completo=:complete, paginas_total=:page_count,
                    lectura_paginas=CAST(:pages AS jsonb), ultimo_error=:incidents,
                    propuestas_rechazadas=CAST(:rejected AS jsonb),
                    bloqueado_hasta=NULL, finalizado_en=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id
            """), {
                "state": "completado" if complete and not incidents else "incompleto",
                "complete": bool(complete and not incidents), "page_count": len(pages),
                "pages": json.dumps(pages, ensure_ascii=False), "incidents": safe_error,
                "rejected": json.dumps(
                    [item.model_dump(mode="json") for item in rejected],
                    ensure_ascii=False,
                ),
                "id": str(analysis_id),
            })
        return True

    def fail(self, analysis_id, attempt_number, safe_error):
        with self.session_factory.begin() as session:
            result = session.execute(text("""
                UPDATE contrato_analisis
                SET estado=CASE WHEN intentos>=3 THEN 'fallido' ELSE 'pendiente' END,
                    ultimo_error=:error, bloqueado_hasta=NULL,
                    proximo_intento_en=CASE WHEN intentos<3 THEN CURRENT_TIMESTAMP
                        + make_interval(secs=>:retry) ELSE proximo_intento_en END,
                    finalizado_en=CASE WHEN intentos>=3 THEN CURRENT_TIMESTAMP ELSE NULL END,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND estado='procesando' AND intentos=:attempt
            """), {"id": str(analysis_id), "attempt": attempt_number,
                    "error": safe_error[:1000], "retry": ANALYSIS_RETRY_SECONDS})
        return result.rowcount == 1

    def review(self, contract_id, clause_id, payload: ClauseReviewRequest, actor):
        with self.session_factory.begin() as session:
            row = session.execute(text("""
                SELECT cl.*, a.contrato_id FROM contrato_clausulas cl
                JOIN contrato_analisis a ON a.id=cl.analisis_id
                WHERE cl.id=:id AND a.contrato_id=:contract_id FOR UPDATE
            """), {"id": str(clause_id), "contract_id": str(contract_id)}).mappings().one_or_none()
            if row is None:
                raise ContractError("No encontramos la cláusula solicitada.", status=404)
            if int(row["revision"]) != payload.revision:
                raise ContractError("La cláusula cambió. Recargá la pantalla.",
                                    code="clause_stale", status=409)
            before = {key: _json(row[key]) if key in {"paginas", "referencias"} else row[key]
                      for key in ("resumen", "categoria", "responsable", "condiciones",
                                  "uso_clasificador", "estado_revision", "paginas", "referencias")}
            values = payload.model_dump(exclude_none=True)
            state = {"confirmar": "confirmada", "editar": "editada", "descartar": "descartada"}[payload.accion]
            summary = values.get("resumen", row["resumen"])
            category = values.get("categoria", row["categoria"])
            responsible = values.get("responsable", row["responsable"])
            usage = values.get("uso_clasificador", row["uso_clasificador"])
            conditions = values.get("condiciones", row["condiciones"])
            new_revision = int(row["revision"]) + 1
            session.execute(text("""
                UPDATE contrato_clausulas
                SET resumen=:summary, categoria=:category, responsable=:responsible,
                    uso_clasificador=:usage, condiciones=:conditions, estado_revision=:state,
                    revision=:revision, revisado_por=:actor,
                    revisado_en=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=:id
            """), {"summary": summary, "category": category, "responsible": responsible,
                    "usage": usage, "conditions": conditions, "state": state,
                    "revision": new_revision,
                    "actor": str(actor), "id": str(clause_id)})
            after = {**before, "resumen": summary, "categoria": category,
                     "responsable": responsible, "condiciones": conditions,
                     "uso_clasificador": usage, "estado_revision": state}
            session.execute(text("""
                INSERT INTO contrato_clausula_eventos
                    (id, clausula_id, accion, revision, valor_anterior, valor_nuevo, actor_id)
                VALUES (:id, :clause_id, :action, :revision,
                        CAST(:before AS jsonb), CAST(:after AS jsonb), :actor)
            """), {"id": str(uuid4()), "clause_id": str(clause_id), "action": state,
                    "revision": new_revision, "before": json.dumps(before, default=str, ensure_ascii=False),
                    "after": json.dumps(after, default=str, ensure_ascii=False), "actor": str(actor)})
            analysis_id = row["analisis_id"]
        return self.get(contract_id, analysis_id)

    def confirmed_for_claim(self, claim_id):
        with self.session_factory() as session:
            rows = session.execute(text("""
                WITH applicable_contract AS (
                    SELECT c.id
                    FROM reclamos r
                    JOIN contratos c ON c.inquilino_id=r.inquilino_id
                        AND c.propiedad_id=r.propiedad_id
                        AND c.estado<>'borrador'
                        AND c.fecha_inicio<=r.creado_en::date
                        AND coalesce(c.fecha_finalizacion, c.fecha_fin)>=r.creado_en::date
                    WHERE r.id=:claim_id
                    ORDER BY c.fecha_inicio DESC LIMIT 1
                ), latest_document AS (
                    SELECT d.id, d.version
                    FROM contrato_documentos d JOIN applicable_contract c ON c.id=d.contrato_id
                    WHERE d.firmado=true ORDER BY d.version DESC LIMIT 1
                )
                SELECT cl.id, a.contrato_id, a.documento_id, d.version AS documento_version,
                       cl.numero, cl.titulo, cl.resumen, cl.categoria, cl.responsable,
                       cl.condiciones, cl.texto_original, cl.revision
                FROM latest_document d
                JOIN contrato_analisis a ON a.documento_id=d.id
                    AND a.estado IN ('completado','incompleto')
                JOIN contrato_clausulas cl ON cl.analisis_id=a.id
                    AND cl.estado_revision IN ('confirmada','editada')
                    AND cl.uso_clasificador='operativa'
                ORDER BY cl.ordinal
            """), {"claim_id": str(claim_id)}).mappings().all()
        return [{key: str(value) if isinstance(value, UUID) else value for key, value in dict(row).items()}
                for row in rows]
