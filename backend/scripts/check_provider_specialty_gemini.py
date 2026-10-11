"""Una sola consulta HU15 autorizada: descripción y catálogo ficticios.

No toca la base de datos, no activa workers y no transmite un reclamo real.
El adaptador y el grafo son los mismos de producción, sin reintentos.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from uuid import UUID

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = "Pierde agua la cañería debajo de la pileta"
CATALOG = [
    {"id": UUID("00000000-0000-0000-0000-000000000201"), "nombre": "Plomería"},
    {"id": UUID("00000000-0000-0000-0000-000000000202"), "nombre": "Electricidad"},
    {"id": UUID("00000000-0000-0000-0000-000000000203"), "nombre": "Cerrajería"},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--execute-authorized", action="store_true",
                        help="Usar sólo después de autorización explícita para esta llamada.")
    args = parser.parse_args()
    if not args.execute_authorized:
        print("No se hizo ninguna llamada: requiere autorización explícita.")
        return 2
    settings = dotenv_values(args.env_file)
    for key in ("GEMINI_API_KEY", "GEMINI_MODEL", "PROVIDER_SPECIALTY_MODEL"):
        if settings.get(key):
            os.environ[key] = settings[key]
    sys.path.insert(0, str(ROOT))
    from app.agents.provider_candidates import build_provider_candidates_graph, get_specialty_resolver
    calls = []
    failure = []

    class Once:
        def __init__(self, adapter):
            self.adapter = adapter

        def invoke(self, prompt):
            assert not calls, "No se permite una segunda invocación."
            calls.append(True)
            try:
                return self.adapter.invoke(prompt)
            except Exception as error:
                # Sólo clase/estado: la excepción completa puede incluir datos.
                code = getattr(error, "status_code", None)
                failure.append({"clase": type(error).__name__, "estado_http": code if isinstance(code,int) else None})
                raise

    try:
        adapter = Once(get_specialty_resolver())
        result = build_provider_candidates_graph(lambda state: None, resolver=adapter).invoke(
            {"descripcion": DESCRIPTION, "tipo_id": None, "catalogo": CATALOG})
        correct = result.get("especialidad_id") == CATALOG[0]["id"] and result.get("fuente") == "modelo"
        print(json.dumps({"invocaciones": len(calls), "modelo": result.get("modelo"),
            "prompt_version": result.get("prompt_version"), "resultado": "Plomería" if correct else "Revisión",
            "validacion": "aprobada" if correct else "no aprobada", "fallo": failure or None}, ensure_ascii=False))
        return 0 if correct else 1
    except Exception as error:
        print(json.dumps({"invocaciones": len(calls), "validacion": "interrumpida", "clase": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
