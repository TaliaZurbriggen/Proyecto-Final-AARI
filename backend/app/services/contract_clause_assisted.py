"""Extracción asistida: procedencia local, propuestas JSON y respaldo sin IA."""

from __future__ import annotations

import json
import os
from pathlib import Path

from google import genai
from google.genai import types

from app.schemas.clausulas_contrato import ExtractedClause
from app.services.contract_clause_v5 import build_segmented_input
from app.services.contract_clause_v7 import SourceClauseBatch, materialize_v7_batch
from app.services.contract_clause_segments import build_clause_segments
from app.services.contract_text_extraction import ContractText, minimize_personal_data


DEFAULT_MODEL = "gemini-3.5-flash-lite"
PROMPT_VERSION = "v10-asistida"
EXTRACTOR_VERSION = "hu30-asistida-v1"
LITERAL_SUMMARY = "Interpretación pendiente. Revisá el texto original antes de completar esta cláusula."
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts/prompt_extraccion_clausulas_v10.md"


def output_schema():
    """Sólo guía al modelo; la validación efectiva se ejecuta localmente."""
    source = SourceClauseBatch.model_json_schema()
    definitions = source.get("$defs", {})

    def inline(node):
        if isinstance(node, list):
            return [inline(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return inline(definitions[node["$ref"].split("/")[-1]])
        result = {key: inline(value) for key, value in node.items()
                  if key not in {"$defs", "title", "default", "minLength", "maxLength"}}
        alternatives = result.get("anyOf", [])
        if len(alternatives) == 2 and {item.get("type") for item in alternatives} == {"string", "null"}:
            result.pop("anyOf")
            result["type"] = ["string", "null"]
        if "properties" in result:
            result["required"] = list(result["properties"])
        return result

    return inline(source)


def build_assisted_prompt(prepared):
    template = PROMPT_PATH.read_text(encoding="utf-8")
    if template.count("{{TEXTO_CONTRATO}}") != 1:
        raise ValueError("El prompt requiere un único marcador de texto.")
    return template.replace("{{TEXTO_CONTRATO}}", minimize_personal_data(prepared.model_text)) + (
        "\n\nESQUEMA DE SALIDA:\n" + json.dumps(output_schema(), ensure_ascii=False)
    )


class JsonClauseModel:
    """Una solicitud HTTP por invocación, sin herramientas ni reintentos ocultos."""

    def __init__(self, key, model):
        self.key, self.model = key, model
        self.http_requests, self.http_statuses = 0, []

    def invoke(self, prompt):
        requests = 0
        self.http_requests, self.http_statuses = 0, []

        def guard(request):
            nonlocal requests
            if (requests or request.method != "POST"
                    or request.url.host != "generativelanguage.googleapis.com"
                    or request.url.path != f"/v1beta/models/{self.model}:generateContent"):
                raise RuntimeError("Solicitud o reintento externo no autorizado.")
            requests += 1
            self.http_requests = requests

        def on_response(response):
            self.http_statuses.append(response.status_code)

        with genai.Client(
            api_key=self.key, vertexai=False,
            http_options=types.HttpOptions(
                api_version="v1beta", base_url="https://generativelanguage.googleapis.com",
                timeout=60_000, retry_options=types.HttpRetryOptions(attempts=1),
                client_args={"follow_redirects": False, "event_hooks": {
                    "request": [guard], "response": [on_response],
                }},
            ),
        ) as client:
            response = client.models.generate_content(
                model=self.model, contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            return response.text or ""


def get_assisted_model(model_name=None):
    if os.getenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        raise RuntimeError("El análisis externo está deshabilitado.")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("El análisis con Gemini no está configurado.")
    return JsonClauseModel(key, model_name or os.getenv("CONTRACT_CLAUSE_MODEL", DEFAULT_MODEL))


def interpret(extracted: ContractText, model):
    prepared = build_segmented_input(extracted)
    value = model.invoke(build_assisted_prompt(prepared))
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict) or "clausulas" not in payload:
        raise ValueError("La respuesta no contiene un lote de cláusulas.")
    batch = SourceClauseBatch.model_validate(payload)
    clauses, rejected, incidents, _ = materialize_v7_batch(batch, prepared)
    return clauses, [item.model_dump(mode="json") for item in rejected], incidents


def literal_clauses(extracted: ContractText):
    """Conserva también preámbulos y encabezados dudosos; no interpreta su contenido."""
    pages = {page.page: page.text if page.readable else "" for page in extracted.pages}
    segments = build_clause_segments(pages)
    groups = []
    for segment in segments:
        groups.append((segment.label, [(part.page, part.text) for part in segment.fragments]))
    # Recuperar los bloques que el segmentador no incluyó, sin unir páginas ilegibles.
    for page in extracted.pages:
        cursor = 0
        for segment in segments:
            for fragment in segment.fragments:
                if fragment.page != page.page:
                    continue
                position = page.text.find(fragment.text, cursor)
                if position < 0:
                    raise ValueError("No se pudo conservar el texto de la página.")
                if page.text[cursor:position].strip():
                    groups.append((None, [(page.page, page.text[cursor:position])]))
                cursor = position + len(fragment.text)
        if page.text[cursor:].strip():
            groups.append((None, [(page.page, page.text[cursor:])]))
    groups.sort(key=lambda group: (group[1][0][0], pages.get(group[1][0][0], "").find(group[1][0][1])))
    clauses = []
    for number, fragments in groups:
        # Particionar explícitamente, nunca truncar para satisfacer los límites del esquema.
        chunks, current, size = [], [], 0
        for page, text in fragments:
            for offset in range(0, len(text), 7900):
                piece = text[offset:offset + 7900].strip()
                if not piece:
                    continue
                if current and (size + len(piece) + 2 > 8000 or len(current) >= 20):
                    chunks.append(current)
                    current, size = [], 0
                current.append({"pagina": page, "texto": piece})
                size += len(piece) + (2 if len(current) > 1 else 0)
        if current:
            chunks.append(current)
        for index, evidences in enumerate(chunks, 1):
            clauses.append(ExtractedClause(
                numero=number, titulo=("Texto sin encabezado reconocido" if number is None
                                      else f"Cláusula {number}") + (
                                          f" · parte {index}/{len(chunks)}" if len(chunks) > 1 else ""),
                evidencias=evidences, resumen=LITERAL_SUMMARY,
                categoria="otro", responsable="no_especificado", uso_clasificador="contexto",
                confianza=0, referencias=[], condiciones=None,
            ))
    return clauses
