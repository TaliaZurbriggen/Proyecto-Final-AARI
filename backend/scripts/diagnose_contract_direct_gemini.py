"""Diagnóstico aislado de V04: texto, JSON y esquema nativo, sin herramientas."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services.contract_clause_corpus import (  # noqa: E402
    file_sha256, get_document, load_json, verify_document, verify_prompt_freeze,
)
from app.services.contract_clause_v5 import build_segmented_input  # noqa: E402
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded  # noqa: E402
from app.services.contract_clause_v7 import SourceClauseBatch, materialize_v7_batch  # noqa: E402
from app.services.contract_clause_v9 import build_v9_prompt  # noqa: E402
from app.services.contract_clause_windows import write_json_atomically  # noqa: E402
from app.services.contract_text_extraction import ContractText, extract_contract_text  # noqa: E402


MODEL = "gemini-3.8-flash"
MANIFEST = PROJECT / "docs/evaluaciones/hu30/corpus_v9_flash38_manifest.json"
RESULT = PROJECT / "docs/evaluaciones/hu30/diagnostico_directo_flash38/resultado.json"
MODES = ("plain", "json", "json_schema")
TIMEOUT_MS = 60_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def native_schema() -> dict:
    """Esquema inline de los mismos nueve campos; límites locales sin cambios."""
    source = SourceClauseBatch.model_json_schema()
    definitions = source.get("$defs", {})

    def resolve(node):
        if isinstance(node, list):
            return [resolve(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return resolve(deepcopy(definitions[node["$ref"].split("/")[-1]]))
        result = {
            key: resolve(value) for key, value in node.items()
            if key not in {"$defs", "title", "default", "minLength", "maxLength"}
        }
        alternatives = result.get("anyOf", [])
        if len(alternatives) == 2 and {item.get("type") for item in alternatives} == {"string", "null"}:
            result.pop("anyOf")
            result["type"] = ["string", "null"]
        if "properties" in result:
            result["required"] = list(result["properties"])
        return result

    return resolve(source)


def build_diagnostic_prompt(prepared) -> str:
    # Idéntico en los tres modos: la etapa plain también necesita conocer el formato.
    # No se modifica el prompt congelado ni se incluyen respuestas esperadas.
    return build_v9_prompt(prepared) + (
        "\n\nFORMATO DE SALIDA DE ESTE DIAGNÓSTICO\n"
        "Respondé solamente con un objeto JSON, sin Markdown, comentarios ni llamadas a herramientas. "
        "Incluí todos los campos de cada propuesta; para valores opcionales usá null o []. "
        "El esquema de salida es:\n" + json.dumps(native_schema(), ensure_ascii=False)
    )


def stage_config(mode: str) -> types.GenerateContentConfig:
    if mode not in MODES:
        raise ValueError("Modo de diagnóstico desconocido.")
    config = {"automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True)}
    if mode != "plain":
        config["response_mime_type"] = "application/json"
    if mode == "json_schema":
        config["response_json_schema"] = native_schema()
    # Sin temperature, tools, thinking ajustado ni límites artificiales de salida.
    return types.GenerateContentConfig(**config)


@dataclass
class HttpCounter:
    attempts: int = 0
    statuses: list[int] = field(default_factory=list)

    def on_request(self, request):
        if (request.method != "POST" or request.url.host != "generativelanguage.googleapis.com"
                or not request.url.path.endswith(f"/models/{MODEL}:generateContent")):
            raise RuntimeError("Se bloqueó una solicitud fuera del diagnóstico autorizado.")
        if self.attempts >= len(MODES):
            raise RuntimeError("Se alcanzó el máximo de solicitudes autorizadas.")
        self.attempts += 1

    def on_response(self, response):
        self.statuses.append(response.status_code)


def create_client(counter: HttpCounter):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Gemini no está configurado.")
    return genai.Client(
        api_key=key, vertexai=False,
        http_options=types.HttpOptions(
            api_version="v1beta", base_url="https://generativelanguage.googleapis.com",
            timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1),
            client_args={"follow_redirects": False, "event_hooks": {
                "request": [counter.on_request], "response": [counter.on_response],
            }},
        ),
    )


def validate_response(text: str, prepared) -> dict:
    result = {"raw_text": text, "format_valid": False, "semantic_review": "pending"}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {**result, "validation_error": "not_json"}
    result["raw_json"] = payload
    # No convertir {} en una extracción vacía aparentemente válida por el default del modelo.
    if not isinstance(payload, dict) or "clausulas" not in payload:
        return {**result, "validation_error": "missing_batch"}
    try:
        batch = SourceClauseBatch.model_validate(payload)
    except ValidationError:
        return {**result, "validation_error": "local_schema"}
    accepted, rejected, incidents, assignments = materialize_v7_batch(batch, prepared)
    return {
        **result, "format_valid": True, "model_proposals": len(batch.clausulas),
        "proposals": [item.model_dump() for item in batch.clausulas],
        "valid_clauses": [item.model_dump() for item in accepted],
        "rejected_proposals": [item.model_dump() for item in rejected],
        "incidents": incidents, "assignments": assignments,
        "has_usable_clauses": bool(accepted),
    }


def run_diagnostic(extracted: ContractText, path: Path, *, metadata: dict, client_factory=create_client) -> dict:
    prepared = build_segmented_input(extracted)
    prompt = build_diagnostic_prompt(prepared)
    record = {
        **metadata, "model": MODEL, "state": "started", "started_at": utc_now(),
        "maximum_http_requests": 3, "automatic_retries": 0,
        "http_requests": 0, "sdk_invocations": 0, "stages": [],
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "source_preserved": prepared.reconstructed_pages() == {p.page: p.text for p in extracted.pages},
        "production_changed": False, "counts_towards_corpus_metrics": False,
    }
    if not record["source_preserved"]:
        raise ValueError("La segmentación no conserva todo el texto original.")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as checkpoint:
            json.dump(record, checkpoint, ensure_ascii=False, indent=2)
            checkpoint.flush()
            os.fsync(checkpoint.fileno())
    except FileExistsError as error:
        raise TrialAlreadyRecorded("El diagnóstico ya tiene evidencia; no se repite.") from error

    counter = HttpCounter()
    client = None
    try:
        client = client_factory(counter)
        for mode in MODES:
            stage = {"mode": mode, "state": "started", "started_at": utc_now(),
                     "prompt_sha256": record["prompt_sha256"], "http_requests": 0}
            record["stages"].append(stage)
            record["sdk_invocations"] += 1
            write_json_atomically(path, record)  # Antes de cada llamada, no al final de la tanda.
            before = counter.attempts
            started = time.monotonic()
            try:
                response = client.models.generate_content(model=MODEL, contents=prompt, config=stage_config(mode))
                text = response.text or ""
                stage.update(validate_response(text, prepared))
                stage["state"] = "completed"
                candidates = response.candidates or []
                stage["finish_reasons"] = [str(c.finish_reason.value) if hasattr(c.finish_reason, "value")
                                           else str(c.finish_reason) for c in candidates]
                usage = response.usage_metadata
                stage["usage"] = {} if usage is None else {
                    name: getattr(usage, name, None) for name in (
                        "prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count",
                    )
                }
            except Exception as error:
                code = getattr(error, "code", None)
                stage.update(state="failed", error={
                    "type": type(error).__name__, "http_status": code if isinstance(code, int) else None,
                })
                record["state"] = "failed"
                record["stop_reason"] = "request_error_no_retry"
            finally:
                stage["finished_at"] = utc_now()
                stage["duration_seconds"] = round(time.monotonic() - started, 3)
                stage["http_requests"] = counter.attempts - before
                stage["http_statuses"] = counter.statuses[before:]
                record["http_requests"] = counter.attempts
                write_json_atomically(path, record)
            if stage["state"] == "failed":
                break  # Incluye 429, 503, otros errores y timeouts. Nunca reintentar.
            if not stage["raw_text"].strip():
                record.update(state="stopped", stop_reason="empty_or_blocked_response")
                break
            # Plain puede devolver Markdown: JSON es la siguiente variable a aislar.
            if mode != "plain" and not (stage["format_valid"] and stage.get("has_usable_clauses")):
                record.update(state="stopped", stop_reason="unusable_json_response")
                break
        else:
            record["state"] = "completed"
    except Exception as error:
        record.update(state="failed", stop_reason="client_setup_error", error={"type": type(error).__name__})
    finally:
        record["finished_at"] = utc_now()
        record["http_requests"] = counter.attempts
        write_json_atomically(path, record)
        if client is not None:
            client.close()
    return record


def prepare() -> tuple[ContractText, dict]:
    manifest = load_json(MANIFEST)
    frozen = verify_prompt_freeze(manifest, PROJECT)
    source = verify_document(get_document(manifest, "V04"), PROJECT)
    extracted = extract_contract_text(source.read_bytes())
    if not extracted.complete or any(p.method != "digital" for p in extracted.pages):
        raise ValueError("Este diagnóstico requiere la copia digital completa de V04.")
    pages_hash = hashlib.sha256(json.dumps(
        [{"page": p.page, "text": p.text} for p in extracted.pages], ensure_ascii=False,
    ).encode()).hexdigest()
    if pages_hash != "18f6fd085061b0f0979ce4025971664a40c3e446c920ca3ef7a17b9c03ba2385":
        raise ValueError("El texto de V04 cambió respecto de la extracción congelada.")
    prepared = build_segmented_input(extracted)
    prompt = build_diagnostic_prompt(prepared)
    return extracted, {
        "document": "V04", "source_kind": "public_reference", "source_sha256": file_sha256(source),
        "base_prompt_version": "v9-experimental", "frozen_files": frozen,
        "source_characters": sum(len(p.text) for p in extracted.pages),
        "extracted_pages_sha256": pages_hash, "prompt_characters": len(prompt),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "native_schema_sha256": json_hash(native_schema()),
        "local_schema_sha256": json_hash(SourceClauseBatch.model_json_schema()),
        "api": "Gemini Developer API generateContent v1beta", "tools": False,
        "sampling": "provider_default", "timeout_ms": TIMEOUT_MS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Hasta 3 solicitudes autorizadas; nunca reintenta.")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    try:
        extracted, metadata = prepare()
        if not args.run:
            print(json.dumps({**metadata, "model": MODEL, "external_calls": 0}, ensure_ascii=False, indent=2))
            return 0
        if RESULT.exists():
            raise TrialAlreadyRecorded("Ya existe evidencia.")
        load_dotenv(args.env_file, override=False)
        result = run_diagnostic(extracted, RESULT, metadata=metadata)
    except Exception as error:
        print(f"No se ejecutó el diagnóstico ({type(error).__name__}); no se reintenta.")
        return 2
    print(json.dumps({
        "state": result["state"], "http_requests": result["http_requests"],
        "stop_reason": result.get("stop_reason"),
        "stages": [{key: stage.get(key) for key in (
            "mode", "state", "error", "format_valid", "model_proposals", "http_requests", "duration_seconds",
        )} for stage in result["stages"]],
    }, ensure_ascii=False, indent=2))
    return 0 if result["state"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
