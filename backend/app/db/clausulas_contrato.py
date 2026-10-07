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
    mode: str = "ia"
    execution_id: UUID | None = None
    model_name: str | None = None
    prompt_version: str | None = None


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

    def request_analysis(self, contract_id, document_id, actor, *, extractor, prompt, model, mode="ia"):
        analysis_id = str(uuid4())
        with self.session_factory.begin() as session:
            # Serializa también el primer pedido, cuando aún no hay fila de análisis.
            document = session.execute(text("""
                SELECT id FROM contrato_documentos
                WHERE id=:document AND contrato_id=:contract FOR UPDATE
            """), {"document": str(document_id), "contract": str(contract_id)}).scalar_one_or_none()
            if document is None:
                raise ContractError("No encontramos la versión del contrato.", status=404)
            existing = session.execute(text("""
                SELECT a.*,
                    EXISTS (
                        SELECT 1 FROM contrato_clausulas cl
                        WHERE cl.analisis_id=a.id AND cl.estado_revision<>'pendiente'
                    ) AS tiene_revision
                FROM contrato_analisis a WHERE a.documento_id=:document_id
                FOR UPDATE
            """), {"document_id": str(document_id)}).mappings().one_or_none()
            if existing:
                if existing["estado"] in {"pendiente", "procesando"}:
                    if existing["modo"] != mode:
                        raise ContractError("Esperá a que termine el intento actual antes de cambiar el modo.",
                                            code="analysis_busy", status=409)
                    return UUID(str(existing["id"]))
                retry = existing["estado"] in {"fallido", "incompleto"} or existing["modo"] != mode
                if retry:
                    if existing["tiene_revision"] and mode == "ia":
                        raise ContractError(
                            "El análisis ya tiene cláusulas revisadas y no puede reemplazarse.",
                            code="analysis_reviewed", status=409,
                        )
                    if existing["ejecucion_id"] is None and existing["intentos"] > 0:
                        session.execute(text("""
                            INSERT INTO contrato_analisis_intentos
                                (id, analisis_id, modo, modelo, prompt_version, extractor_version,
                                 estado, resultado, error, iniciado_en, finalizado_en)
                            VALUES (:id, :analysis, :mode, :model, :prompt, :extractor,
                                :state, CAST(:result AS jsonb), :error, :started, :finished)
                        """), {"id": str(uuid4()), "analysis": str(existing["id"]), "mode": existing["modo"],
                                "model": existing["modelo"], "prompt": existing["prompt_version"],
                                "extractor": existing["extractor_version"], "state": existing["estado"],
                                "result": json.dumps({"origen": "snapshot_previo_migracion_25",
                                    "lectura_paginas": _json(existing["lectura_paginas"]),
                                    "propuestas_rechazadas": _json(existing["propuestas_rechazadas"])}, ensure_ascii=False),
                                "error": existing["ultimo_error"], "started": existing["iniciado_en"] or existing["created_at"],
                                "finished": existing["finalizado_en"]})
                    session.execute(text("""
                        UPDATE contrato_analisis
                        SET estado='pendiente', intentos=0, completo=false,
                            extractor_version=:extractor, prompt_version=:prompt,
                            modelo=:model,
                            modo=:mode, ejecucion_id=NULL,
                            ultimo_error=NULL, paginas_total=NULL,
                            lectura_paginas='[]'::jsonb,
                            proximo_intento_en=CURRENT_TIMESTAMP, bloqueado_hasta=NULL,
                            iniciado_en=NULL, finalizado_en=NULL,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=:id
                    """), {
                        "id": str(existing["id"]), "extractor": extractor,
                        "prompt": prompt, "model": model,
                        "mode": mode,
                    })
                return UUID(str(existing["id"]))
            session.execute(text("""
                INSERT INTO contrato_analisis
                    (id, contrato_id, documento_id, extractor_version, prompt_version,
                     modelo, solicitado_por, modo)
                VALUES
                    (:id, :contract_id, :document_id, :extractor, :prompt, :model, :actor, :mode)
            """), {
                "id": analysis_id, "contract_id": str(contract_id),
                "document_id": str(document_id), "extractor": extractor,
                "prompt": prompt, "model": model, "actor": str(actor),
                "mode": mode,
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
        result["propuestas_fuente_rechazadas"] = _json(result.get("propuestas_fuente_rechazadas")) or []
        attempts = session.execute(text("""
            SELECT id, modo, modelo, prompt_version, extractor_version, estado,
                   error, iniciado_en, finalizado_en
            FROM contrato_analisis_intentos WHERE analisis_id=:id ORDER BY iniciado_en, id
        """), {"id": str(result["id"])}).mappings().all()
        result["historial_intentos"] = [dict(attempt) for attempt in attempts]
        clauses = session.execute(text("""
            SELECT cl.id, cl.ordinal, cl.numero, cl.titulo, cl.paginas,
                   cl.texto_original, cl.resumen, cl.categoria, cl.responsable,
                   cl.condiciones, cl.referencias, cl.confianza, cl.evidencias,
                   cl.uso_clasificador, cl.estado_revision, cl.revision, cl.origen,
                   cl.revisado_por, cl.revisado_en,
                   (cl.estado_revision='editada' AND cl.uso_clasificador='operativa'
                    AND EXISTS (
                        SELECT 1 FROM contrato_clausula_eventos ev
                        WHERE ev.clausula_id=cl.id AND ev.accion='editada'
                          AND ev.valor_nuevo->>'habilitacion_operativa_explicita'='true'
                    )) AS habilitada_para_reclamos
            FROM contrato_clausulas cl WHERE cl.analisis_id=:id ORDER BY cl.ordinal
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
                UPDATE contrato_analisis_intentos i
                SET estado='interrumpido', finalizado_en=CURRENT_TIMESTAMP,
                    error='El intento perdió su reserva de ejecución.'
                FROM contrato_analisis a WHERE i.id=a.ejecucion_id
                  AND i.estado='procesando' AND a.estado='procesando'
                  AND a.bloqueado_hasta<=CURRENT_TIMESTAMP
            """))
            session.execute(text("""
                UPDATE contrato_analisis
                SET estado='fallido', ultimo_error=coalesce(
                    ultimo_error, 'El análisis se interrumpió durante el último intento.'),
                    bloqueado_hasta=NULL, updated_at=CURRENT_TIMESTAMP
                WHERE estado='procesando' AND intentos>=3
                  AND bloqueado_hasta<=CURRENT_TIMESTAMP
            """))
            rows = session.execute(text("""
                    SELECT a.*, d.storage_path FROM contrato_analisis a
                    JOIN contrato_documentos d ON d.id=a.documento_id
                    WHERE intentos < 3 AND (
                        (estado='pendiente' AND proximo_intento_en<=CURRENT_TIMESTAMP)
                        OR (estado='procesando' AND bloqueado_hasta<=CURRENT_TIMESTAMP)
                    )
                    ORDER BY a.proximo_intento_en, a.created_at
                    FOR UPDATE OF a SKIP LOCKED LIMIT :limit
            """), {"limit": max(1, min(limit, 10))}).mappings().all()
            jobs = []
            for row in rows:
                execution = uuid4()
                session.execute(text("""
                    UPDATE contrato_analisis SET estado='procesando', intentos=intentos+1,
                        ejecucion_id=:execution,
                        bloqueado_hasta=CURRENT_TIMESTAMP + make_interval(secs=>:lease),
                        iniciado_en=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=:id
                """), {"execution": str(execution), "id": str(row["id"]), "lease": ANALYSIS_LEASE_SECONDS})
                session.execute(text("""
                    INSERT INTO contrato_analisis_intentos
                        (id, analisis_id, modo, modelo, prompt_version, extractor_version, estado)
                    VALUES (:id, :analysis, :mode, :model, :prompt, :extractor, 'procesando')
                """), {"id": str(execution), "analysis": str(row["id"]), "mode": row["modo"],
                        "model": row["modelo"], "prompt": row["prompt_version"], "extractor": row["extractor_version"]})
                jobs.append(AnalysisJob(UUID(str(row["id"])), UUID(str(row["contrato_id"])),
                            UUID(str(row["documento_id"])), str(row["storage_path"]),
                            int(row["intentos"]) + 1, row["modo"], execution, row["modelo"], row["prompt_version"]))
        return jobs

    def renew_lease(self, analysis_id, *, execution_id):
        """Sólo el dueño vigente puede extender la reserva, nunca revivirla."""
        if execution_id is None:
            return False
        with self.session_factory.begin() as session:
            result = session.execute(text("""
                UPDATE contrato_analisis
                SET bloqueado_hasta=clock_timestamp() + make_interval(secs=>:lease),
                    updated_at=clock_timestamp()
                WHERE id=:id AND estado='procesando'
                  AND ejecucion_id=CAST(:execution AS uuid)
                  AND bloqueado_hasta>clock_timestamp()
            """), {"id": str(analysis_id), "execution": str(execution_id),
                    "lease": ANALYSIS_LEASE_SECONDS})
        return result.rowcount == 1

    def complete(
        self, analysis_id, *, pages, clauses: list[ExtractedClause],
        rejected: list[RejectedClause], complete, incidents,
        extractor_version: str | None = None,
        source_rejected=None, origins=None, execution_id=None,
    ):
        with self.session_factory.begin() as session:
            current = session.execute(text("""
                SELECT estado, ejecucion_id FROM contrato_analisis WHERE id=:id FOR UPDATE
            """), {"id": str(analysis_id)}).mappings().one_or_none()
            outcome = {"lectura_paginas": pages, "clausulas": [c.model_dump(mode="json") for c in clauses],
                       "propuestas_rechazadas": [r.model_dump(mode="json") for r in rejected],
                       "propuestas_fuente_rechazadas": source_rejected or [], "incidencias": incidents}
            if execution_id:
                session.execute(text("""
                    UPDATE contrato_analisis_intentos SET resultado=CAST(:result AS jsonb),
                        estado=CASE WHEN estado='procesando' THEN :state ELSE estado END,
                        finalizado_en=CURRENT_TIMESTAMP WHERE id=:id AND analisis_id=:analysis
                          AND estado IN ('procesando', 'interrumpido')
                """), {"id": str(execution_id), "analysis": str(analysis_id),
                        "result": json.dumps(outcome, ensure_ascii=False),
                        "state": "completado" if complete and not incidents else "incompleto"})
            if (current is None or current["estado"] != "procesando"
                    or (execution_id and str(current.get("ejecucion_id")) != str(execution_id))):
                return False
            previous = session.execute(text("""
                SELECT ordinal, propuesta_original, origen FROM contrato_clausulas
                WHERE analisis_id=:id ORDER BY ordinal
            """), {"id": str(analysis_id)}).mappings().all()
            known = {(json.dumps(_json(row["propuesta_original"]), sort_keys=True, ensure_ascii=False),
                      row["origen"]) for row in previous}
            ordinal = max((row["ordinal"] for row in previous), default=0)
            for index, clause in enumerate(clauses):
                origin = (origins or ["ia"] * len(clauses))[index]
                original = clause.model_dump(mode="json")
                key = (json.dumps(original, sort_keys=True, ensure_ascii=False), origin)
                if key in known:
                    continue
                known.add(key)
                ordinal += 1
                session.execute(text("""
                    INSERT INTO contrato_clausulas
                        (id, analisis_id, ordinal, numero, titulo, paginas,
                         texto_original, resumen, categoria, responsable, condiciones,
                         referencias, confianza, evidencias, uso_clasificador,
                         propuesta_original, origen)
                    VALUES
                        (:id, :analysis_id, :ordinal, :numero, :titulo, CAST(:paginas AS jsonb),
                         :texto_original, :resumen, :categoria, :responsable, :condiciones,
                         CAST(:referencias AS jsonb), :confianza, CAST(:evidencias AS jsonb),
                         :uso_clasificador, CAST(:original AS jsonb), :origin)
                """), {
                    **original, "id": str(uuid4()), "analysis_id": str(analysis_id),
                    "ordinal": ordinal, "paginas": json.dumps(clause.paginas),
                    "referencias": json.dumps(clause.referencias),
                    "evidencias": json.dumps(original["evidencias"], ensure_ascii=False),
                    "uso_clasificador": "contexto",
                    "original": json.dumps(original, ensure_ascii=False),
                    "origin": origin,
                })
            safe_error = " ".join(incidents)[:1000] or None
            session.execute(text("""
                UPDATE contrato_analisis
                SET estado=:state, completo=:complete, paginas_total=:page_count,
                    extractor_version=coalesce(:extractor_version, extractor_version),
                    lectura_paginas=CAST(:pages AS jsonb), ultimo_error=:incidents,
                    propuestas_rechazadas=propuestas_rechazadas || CAST(:rejected AS jsonb),
                    propuestas_fuente_rechazadas=propuestas_fuente_rechazadas || CAST(:source_rejected AS jsonb),
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
                "id": str(analysis_id), "extractor_version": extractor_version,
                "source_rejected": json.dumps(source_rejected or [], ensure_ascii=False),
            })
        return True

    def fail(self, analysis_id, attempt_number, safe_error, *, execution_id=None):
        with self.session_factory.begin() as session:
            result = session.execute(text("""
                UPDATE contrato_analisis
                SET estado='fallido',
                    ultimo_error=:error, bloqueado_hasta=NULL,
                    proximo_intento_en=CASE WHEN intentos<3 THEN CURRENT_TIMESTAMP
                        + make_interval(secs=>:retry) ELSE proximo_intento_en END,
                    finalizado_en=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND estado='procesando' AND intentos=:attempt
                  AND (CAST(:execution AS uuid) IS NULL OR ejecucion_id=CAST(:execution AS uuid))
            """), {"id": str(analysis_id), "attempt": attempt_number,
                    "error": safe_error[:1000], "retry": ANALYSIS_RETRY_SECONDS,
                    "execution": str(execution_id) if execution_id else None})
            if execution_id:
                session.execute(text("""
                    UPDATE contrato_analisis_intentos SET estado=CASE WHEN estado='procesando'
                        THEN 'fallido' ELSE estado END, error=:error, finalizado_en=CURRENT_TIMESTAMP
                    WHERE id=:id AND analisis_id=:analysis
                      AND estado IN ('procesando', 'interrumpido')
                """), {"id": str(execution_id), "analysis": str(analysis_id), "error": safe_error[:1000]})
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
            summary = values.get("resumen", row["resumen"]).strip()
            if not summary:
                raise ContractError("Completá el resumen de la cláusula.", field="resumen", status=422)
            category = values.get("categoria", row["categoria"])
            responsible = values.get("responsable", row["responsable"])
            # Confirmar nunca habilita una interpretación propuesta por la IA.
            # Sólo una edición que incluya operativa puede generar el evento de activación.
            usage = values.get("uso_clasificador", "contexto") if state == "editada" else "contexto"
            if row.get("origen") == "literal" and usage == "operativa":
                from app.services.contract_clause_assisted import LITERAL_SUMMARY
                if summary == LITERAL_SUMMARY or not summary.strip():
                    raise ContractError("Completá la interpretación antes de habilitar esta cláusula.",
                                        field="resumen", status=422)
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
            if state == "editada" and values.get("uso_clasificador") == "operativa":
                after["habilitacion_operativa_explicita"] = True
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
                        AND c.fecha_inicio<=(r.creado_en AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
                        AND coalesce(c.fecha_finalizacion, c.fecha_fin)>=
                            (r.creado_en AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
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
                JOIN contrato_clausulas cl ON cl.analisis_id=a.id
                    AND cl.estado_revision='editada'
                    AND cl.uso_clasificador='operativa'
                    AND EXISTS (
                        SELECT 1 FROM contrato_clausula_eventos ev
                        WHERE ev.clausula_id=cl.id AND ev.accion='editada'
                          AND ev.valor_nuevo->>'habilitacion_operativa_explicita'='true'
                    )
                ORDER BY cl.ordinal
            """), {"claim_id": str(claim_id)}).mappings().all()
        return [{key: str(value) if isinstance(value, UUID) else value for key, value in dict(row).items()}
                for row in rows]
