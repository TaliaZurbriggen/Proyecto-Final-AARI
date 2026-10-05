"""Ensayo acotado del clasificador con contexto contractual ficticio.

No consulta la base ni envía contratos reales. Ejecutar solo con autorización
explícita porque cada escenario consume una llamada a Gemini.
"""

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import dotenv_values
from langchain_google_genai import ChatGoogleGenerativeAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.classification.graph import build_classification_graph  # noqa: E402
from app.agents.classification.schemas import ModelClassification  # noqa: E402


DESCRIPTION = (
    "El consorcio emitió las expensas ordinarias habituales del mes para el "
    "departamento. No incluyen obras, fondo de reserva ni gastos extraordinarios."
)
ENABLED_CLAUSE = {
    "id": "clausula-ficticia-1",
    "numero": "QUINTA",
    "titulo": "Expensas ordinarias",
    "resumen": "El inquilino asume las expensas ordinarias habituales del consorcio.",
    "categoria": "expensa",
    "responsable": "inquilino",
    "condiciones": "Solo gastos habituales; excluye obras y fondo de reserva.",
    "texto_original": (
        "El locatario abonará las expensas ordinarias habituales del consorcio. "
        "Las obras y el fondo de reserva quedan excluidos."
    ),
    "documento_version": 1,
}


class ObservedClassifier:
    """Registra solo el tipo de error, nunca su texto ni credenciales."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.error_type = None

    def invoke(self, prompt):
        try:
            return self.delegate.invoke(prompt)
        except Exception as error:
            self.error_type = type(error).__name__
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Confirma el consumo de API")
    parser.add_argument("--env-file", type=Path, help=".env local, nunca se imprime")
    parser.add_argument("--models", nargs="+", required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error("Falta --live: el ensayo consume una llamada por modelo y escenario")

    key = os.getenv("GEMINI_API_KEY")
    if not key and args.env_file:
        key = dotenv_values(args.env_file).get("GEMINI_API_KEY")
    if not key:
        parser.error("Falta GEMINI_API_KEY en el entorno o en --env-file")

    for model_name in args.models:
        model = ChatGoogleGenerativeAI(
            model=model_name, google_api_key=key, temperature=0, max_retries=1,
        ).with_structured_output(schema=ModelClassification, method="json_schema")
        for scenario_name, clauses in (
            ("sin_contexto", []), ("clausula_habilitada", [ENABLED_CLAUSE]),
        ):
            observed = ObservedClassifier(model)
            graph = build_classification_graph(observed, confidence_threshold=0.75)
            result = graph.invoke({
                "reclamo_id": "00000000-0000-0000-0000-000000000001",
                "descripcion": DESCRIPTION,
                "urgencia": "baja",
                "rubro_declarado": "expensas",
                "clausulas_contrato": clauses,
            })
            print(json.dumps({
                "model": model_name,
                "scenario": scenario_name,
                "error_type": observed.error_type,
                "tipo_gasto": result.get("tipo_gasto"),
                "debe_escalar": result.get("debe_escalar"),
                "motivo_escalado": result.get("motivo_escalado"),
                "confianza": result.get("confianza"),
                "fundamento": result.get("fundamento"),
            }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
