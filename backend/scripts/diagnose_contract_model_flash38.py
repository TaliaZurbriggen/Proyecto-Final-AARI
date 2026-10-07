"""Hasta dos pruebas mínimas autorizadas de Flash 3.8, sin contratos."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services.contract_clause_v5_trial import TrialAlreadyRecorded  # noqa: E402
from app.services.contract_clause_windows import write_json_atomically  # noqa: E402


MODEL = "gemini-3.8-flash"
PROMPT = "Responde solamente OK."
OUTPUT = PROJECT / "docs/evaluaciones/hu30/diagnostico_flash38_minimo"


class ProbeResponse(BaseModel):
    respuesta: str


def build_model(key: str, *, structured: bool):
    model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=key, max_retries=1)
    return model.with_structured_output(ProbeResponse, method="function_calling") if structured else model


def summarize_response(output, *, structured: bool) -> dict:
    if structured:
        value = output.respuesta if isinstance(output, ProbeResponse) else output.get("respuesta")
    else:
        value = getattr(output, "content", output)
        if isinstance(value, list):
            value = "".join(
                block if isinstance(block, str) else block.get("text", "")
                for block in value if isinstance(block, (str, dict))
            )
    if not isinstance(value, str):
        raise ValueError("La respuesta no contiene texto utilizable.")
    # No se persiste contenido inesperado, aunque la entrada sea sintética.
    text = value.strip()
    return {
        "response_received": bool(text), "expected_ok": text == "OK",
        "response_characters": len(text), "safe_response": "OK" if text == "OK" else None,
    }


def safe_error(error: Exception) -> dict:
    result = {"type": type(error).__name__, "reason_category": "unknown"}
    status = getattr(error, "status_code", getattr(error, "code", None))
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        result["http_status"] = status
    # Clasifica sólo frases conocidas; nunca copia el mensaje del proveedor.
    message = str(error).lower()
    for phrase, category in (
        ("high demand", "high_demand"), ("quota", "quota_reported"),
        ("unavailable", "unavailable_reported"),
    ):
        if phrase in message:
            result["reason_category"] = category
            break
    return result


def execute_probe(factory, path: Path, *, structured: bool, metadata: dict) -> dict:
    if path.exists():
        raise TrialAlreadyRecorded("Ya existe este diagnóstico; no se repite.")
    base = {
        **metadata, "model": MODEL, "mode": "structured" if structured else "plain",
        "prompt": PROMPT, "contracts_sent": 0, "automatic_retries_setting": 1,
        "http_attempts_verified": False, "started_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump({**base, "state": "started"}, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise TrialAlreadyRecorded("Ya existe este diagnóstico; no se repite.") from error
    calls = 0
    started = time.monotonic()
    try:
        model = factory()
        calls = 1
        output = model.invoke(PROMPT)
        response = summarize_response(output, structured=structured)
        detail = {"state": "completed", **response}
    except Exception as error:
        detail = {"state": "failed", "error": safe_error(error)}
    result = {
        **base, **detail, "adapter_invocations": calls,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    write_json_atomically(path, result)
    return result


def run_diagnostic(plain_factory, structured_factory, directory: Path, *, metadata: dict) -> dict:
    plain_path = directory / "plain.json"
    structured_path = directory / "structured.json"
    if plain_path.exists() or structured_path.exists():
        raise TrialAlreadyRecorded("Ya hay evidencia; no se reanuda ni repite automáticamente.")
    plain = execute_probe(plain_factory, plain_path, structured=False, metadata=metadata)
    trials = [plain]
    if plain["state"] == "completed" and plain["response_received"]:
        trials.append(execute_probe(structured_factory, structured_path, structured=True, metadata=metadata))
    return {
        "model": MODEL, "trials": trials,
        "adapter_invocations": sum(item["adapter_invocations"] for item in trials),
        "structured_skipped": len(trials) == 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    args = parser.parse_args()
    metadata = {
        "diagnostic_version": "flash38-minimal-2026-10-02",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "packages": {name: version(name) for name in ("langchain-google-genai", "google-genai")},
        "maximum_authorized_adapter_invocations": 2,
    }
    if not args.run:
        print(json.dumps({**metadata, "model": MODEL, "prompt": PROMPT, "external_calls": 0}, indent=2))
        return 0
    load_dotenv(args.env_file, override=False)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        print("Gemini no está configurado; no se llamó al servicio.")
        return 2
    try:
        result = run_diagnostic(
            lambda: build_model(key, structured=False),
            lambda: build_model(key, structured=True), OUTPUT, metadata=metadata,
        )
    except TrialAlreadyRecorded:
        print("Ya existe evidencia de este diagnóstico; no se repite.")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(item["state"] == "completed" and item["expected_ok"] for item in result["trials"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
