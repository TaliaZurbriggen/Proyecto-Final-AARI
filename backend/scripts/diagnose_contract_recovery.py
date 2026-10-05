"""Controles aislados de disponibilidad: cada caso hace una única solicitud."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services.contract_clause_v5_trial import TrialAlreadyRecorded  # noqa: E402
from app.services.contract_clause_v5 import build_segmented_input  # noqa: E402
from app.services.contract_clause_windows import write_json_atomically  # noqa: E402
from app.services.contract_text_extraction import minimize_personal_data  # noqa: E402
from scripts import diagnose_contract_clause_plain as single  # noqa: E402
from scripts import diagnose_contract_direct_gemini as direct  # noqa: E402


CASES = {
    "health38": "gemini-3.8-flash", "quinta_lite": "gemini-3.5-flash-lite",
    "v04_lite_native": "gemini-3.5-flash-lite", "v04_lite_json": "gemini-3.5-flash-lite",
    "v04_lite31_json": "gemini-3.1-flash-lite",
    "v04_flash38_json_low": "gemini-3.8-flash",
    "v04_flash37_json": "gemini-3.7-flash",
    "v04_lite31_json_high": "gemini-3.1-flash-lite",
}
DIRECTORY = PROJECT / "docs/evaluaciones/hu30/diagnostico_recuperacion_2026-10-02"
PROMPT_PATH = BACKEND / "prompts/prompt_extraccion_clausulas_v10.md"


def build_short_batch_prompt(prepared):
    template = PROMPT_PATH.read_text(encoding="utf-8")
    if template.count("{{TEXTO_CONTRATO}}") != 1:
        raise ValueError("La plantilla debe tener un único marcador.")
    return template.replace("{{TEXTO_CONTRATO}}", minimize_personal_data(prepared.model_text)) + (
        "\n\nESQUEMA DE SALIDA:\n" + json.dumps(direct.native_schema(), ensure_ascii=False)
    )


class Counter(direct.HttpCounter):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def on_request(self, request):
        if (request.method != "POST" or request.url.host != "generativelanguage.googleapis.com"
                or request.url.path != f"/v1beta/models/{self.model}:generateContent" or self.attempts):
            raise RuntimeError("Solicitud fuera del ensayo o reintento bloqueado.")
        self.attempts += 1


def prepare(case):
    if case not in CASES:
        raise ValueError("Caso desconocido.")
    if case == "health38":
        prompt = "Respondé solamente OK."
        metadata = {"document": None, "source_kind": "synthetic_health_control"}
    elif case == "quinta_lite":
        prompt, metadata = single.prepare_probe()
    else:
        extracted, metadata = direct.prepare()
        prepared = build_segmented_input(extracted)
        prompt = build_short_batch_prompt(prepared)
        metadata.update(prompt_version="v10-experimental", prompt_template_sha256=hashlib.sha256(
            PROMPT_PATH.read_bytes()).hexdigest(), source_preserved=prepared.reconstructed_pages() == {
                p.page: p.text for p in extracted.pages},
        )
    metadata.update(
        case=case, model=CASES[case], prompt=prompt, prompt_characters=len(prompt),
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        maximum_http_requests=1, automatic_retries=0, production_changed=False,
        counts_towards_corpus_metrics=False, tools=False,
    )
    return prompt, metadata


def case_config(case):
    mode = {
        "v04_lite_native": "json_schema", "v04_lite_json": "json", "v04_lite31_json": "json",
        "v04_flash38_json_low": "json",
        "v04_flash37_json": "json",
        "v04_lite31_json_high": "json",
    }.get(case, "plain")
    config = direct.stage_config(mode)
    if case == "v04_flash38_json_low":
        config.thinking_config = direct.types.ThinkingConfig(thinking_level="LOW")
    elif case == "v04_lite31_json_high":
        config.thinking_config = direct.types.ThinkingConfig(thinking_level="HIGH")
    return mode, config


def run_case(prompt, metadata, path, *, client_factory=direct.create_client):
    record = {**metadata, "state": "started", "started_at": datetime.now(timezone.utc).isoformat(),
              "sdk_invocations": 0, "http_requests": 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as checkpoint:
            json.dump(record, checkpoint, ensure_ascii=False, indent=2)
            checkpoint.flush()
            os.fsync(checkpoint.fileno())
    except FileExistsError as error:
        raise TrialAlreadyRecorded("Ya existe evidencia; no se repite.") from error
    client = None
    counter = Counter(metadata["model"])
    started = time.monotonic()
    try:
        client = client_factory(counter)
        record["sdk_invocations"] = 1
        write_json_atomically(path, record)
        mode, config = case_config(metadata["case"])
        record["output_mode"] = mode
        record["thinking_level"] = (config.thinking_config.thinking_level.value
                                    if config.thinking_config else "provider_default")
        write_json_atomically(path, record)
        response = client.models.generate_content(
            model=metadata["model"], contents=prompt, config=config,
        )
        record.update(state="completed", raw_text=response.text or "")
        record["response_received"] = bool(record["raw_text"].strip())
        record["semantic_review"] = "pending" if metadata["document"] else "not_applicable"
        if metadata["case"].startswith("v04_"):
            extracted, frozen_metadata = direct.prepare()
            if frozen_metadata["source_sha256"] != metadata["source_sha256"]:
                raise ValueError("La fuente cambió durante el ensayo.")
            record.update(direct.validate_response(record["raw_text"], build_segmented_input(extracted)))
        usage = response.usage_metadata
        record["usage"] = {} if usage is None else {name: getattr(usage, name, None) for name in (
            "prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count",
        )}
    except Exception as error:
        record.update(state="failed", error=single.safe_error(error))
    finally:
        record.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      duration_seconds=round(time.monotonic() - started, 3),
                      http_requests=counter.attempts, http_statuses=counter.statuses)
        write_json_atomically(path, record)
        if client is not None:
            client.close()
    return record


def validate_saved_case(case, path, output):
    """Valida evidencia existente sin modificarla ni llamar al proveedor."""
    if case not in CASES or not case.startswith("v04_"):
        raise ValueError("Sólo se validan extracciones completas de V04.")
    record = json.loads(path.read_text(encoding="utf-8"))
    _, expected = prepare(case)
    for field in ("case", "model", "document", "source_sha256", "extracted_pages_sha256", "prompt_sha256"):
        if record.get(field) != expected[field]:
            raise ValueError("La evidencia no coincide con el ensayo congelado.")
    if record.get("state") != "completed" or not isinstance(record.get("raw_text"), str):
        raise ValueError("No hay respuesta completada para validar.")
    extracted, _ = direct.prepare()
    validation = {
        "case": case, "document": "V04", "model": record["model"],
        "original_record_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "external_calls": 0, "validated_at": datetime.now(timezone.utc).isoformat(),
        **direct.validate_response(record["raw_text"], build_segmented_input(extracted)),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as sidecar:
        json.dump(validation, sidecar, ensure_ascii=False, indent=2)
        sidecar.flush()
        os.fsync(sidecar.fileno())
    return validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--run", action="store_true")
    operation.add_argument("--validate-saved", action="store_true", help="Validación local, cero llamadas.")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    try:
        prompt, metadata = prepare(args.case)
        if args.validate_saved:
            validation = validate_saved_case(
                args.case, DIRECTORY / f"{args.case}.json", DIRECTORY / f"validacion_{args.case}.json",
            )
            print(json.dumps({key: validation.get(key) for key in (
                "case", "external_calls", "format_valid", "model_proposals", "has_usable_clauses",
            )}, ensure_ascii=False, indent=2))
            return 0 if validation["format_valid"] else 1
        if not args.run:
            print(json.dumps({**metadata, "external_calls": 0}, ensure_ascii=False, indent=2))
            return 0
        load_dotenv(args.env_file, override=False)
        result = run_case(prompt, metadata, DIRECTORY / f"{args.case}.json")
    except Exception as error:
        print(f"Caso no ejecutado ({type(error).__name__}); no se repite.")
        return 2
    print(json.dumps({key: result.get(key) for key in (
        "case", "model", "state", "http_requests", "error", "duration_seconds",
        "format_valid", "model_proposals", "has_usable_clauses",
    )}, ensure_ascii=False, indent=2))
    return 0 if result["state"] == "completed" and result["response_received"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
