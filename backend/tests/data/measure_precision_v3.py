"""Mide la precisión del prompt v3 contra conjunto_prueba_61_casos.json.

Uso (desde backend/, con GEMINI_API_KEY configurada en .env):

    python -m tests.data.measure_precision_v3 --lote 0:20
    python -m tests.data.measure_precision_v3 --lote 20:40
    python -m tests.data.measure_precision_v3 --lote 40:61
    python -m tests.data.measure_precision_v3 --reporte-final

Corre en lotes por diseño: cada llamada real a Gemini consume créditos, y
AARI-112 pide autorización explícita antes de cada tanda de 20.

No sobrescribe evidencia de AARI-111: escribe siempre en
docs/evaluaciones/aari112/, nunca en la carpeta de AARI-111.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agents.classification.graph import build_classification_graph
from app.agents.classification.state import ClassificationState

BACKEND_DIR = Path(__file__).resolve().parents[2]
CASOS_PATH = BACKEND_DIR / "tests" / "data" / "conjunto_prueba_61_casos.json"
EVAL_DIR = BACKEND_DIR.parent / "docs" / "evaluaciones" / "aari112"
PARCIALES_PATH = EVAL_DIR / "resultados_v3_parciales.json"
RESULTADOS_PATH = EVAL_DIR / "resultados_v3.json"
REGRESION_PATH = EVAL_DIR / "casos_regresion_v3.json"
INVALIDAS_PATH = EVAL_DIR / "respuestas_invalidas_v3.json"


def _cargar_casos() -> list[dict]:
    data = json.loads(CASOS_PATH.read_text(encoding="utf-8"))
    return data["casos"]


def _cargar_parciales() -> dict[str, dict]:
    if PARCIALES_PATH.exists():
        return json.loads(PARCIALES_PATH.read_text(encoding="utf-8"))
    return {}


def _guardar_parciales(parciales: dict[str, dict]) -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    PARCIALES_PATH.write_text(
        json.dumps(parciales, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _correr_lote(casos: list[dict], desde: int, hasta: int) -> None:
    grafo = build_classification_graph()
    parciales = _cargar_parciales()

    for caso in casos[desde:hasta]:
        if caso["id"] in parciales:
            continue  # ya medido en una tanda anterior

        state: ClassificationState = {
            "descripcion": caso["descripcion"],
            "urgencia": caso.get("urgencia", "media"),
            "rubro_declarado": caso.get("rubro_declarado"),
            "clausulas_contrato": caso.get("clausulas_contrato", []),
        }
        resultado = grafo.invoke(state)
        parciales[caso["id"]] = {
            "esperado": {
                "categoria": caso["categoria_esperada"],
                "escalar": caso["escalar_esperado"],
                "motivos_aceptables": caso.get("motivos_aceptables"),
            },
            "obtenido": {
                "tipo_gasto": resultado.get("tipo_gasto"),
                "debe_escalar": resultado.get("debe_escalar"),
                "motivo_escalado": resultado.get("motivo_escalado"),
                "confianza": resultado.get("confianza"),
            },
        }
        print(f"{caso['id']}: esperado={caso['categoria_esperada']}/"
              f"escalar={caso['escalar_esperado']} -> "
              f"obtenido={resultado.get('tipo_gasto')}/"
              f"escalar={resultado.get('debe_escalar')}/"
              f"{resultado.get('motivo_escalado')}")

    _guardar_parciales(parciales)
    print(f"\nGuardado en {PARCIALES_PATH} ({len(parciales)}/{len(casos)} casos medidos)")


def _generar_reporte_final(casos: list[dict]) -> None:
    parciales = _cargar_parciales()
    faltantes = [c["id"] for c in casos if c["id"] not in parciales]
    if faltantes:
        raise SystemExit(
            f"Faltan {len(faltantes)} casos por medir: {faltantes}. "
            "Corré los lotes pendientes antes de generar el reporte final."
        )

    por_categoria: dict[str, dict[str, int]] = {}
    regresiones = []
    invalidas = []
    correctos_total = 0

    for caso in casos:
        p = parciales[caso["id"]]
        esperado_cat = p["esperado"]["categoria"]
        esperado_escalar = p["esperado"]["escalar"]
        motivos_ok = p["esperado"]["motivos_aceptables"]
        obtenido = p["obtenido"]

        clave_cat = "escalar" if esperado_escalar else esperado_cat
        por_categoria.setdefault(clave_cat, {"total": 0, "correctos": 0})
        por_categoria[clave_cat]["total"] += 1

        if obtenido["motivo_escalado"] == "respuesta_modelo_invalida":
            invalidas.append({"id": caso["id"], **p})
            continue  # no cuenta como error de prompt, ver sección 4.3 del prompt v3

        es_correcto = False
        if esperado_escalar:
            if obtenido["debe_escalar"] is True:
                if motivos_ok:
                    es_correcto = obtenido["motivo_escalado"] in motivos_ok
                else:
                    es_correcto = True
        else:
            es_correcto = (
                obtenido["debe_escalar"] is False
                and obtenido["tipo_gasto"] == esperado_cat
            )

        if es_correcto:
            correctos_total += 1
            por_categoria[clave_cat]["correctos"] += 1
        else:
            regresiones.append({"id": caso["id"], "descripcion_error": (
                "sobreescalado" if (esperado_escalar is False and obtenido["debe_escalar"])
                else "escalamiento_omitido" if (esperado_escalar is True and not obtenido["debe_escalar"])
                else "motivo_o_categoria_incorrecta"
            ), **p})

    total_medibles = len(casos) - len(invalidas)
    resultado = {
        "prompt_version": "v3",
        "linea_base_v2": {"correctos": 35, "total": 61, "precision": round(35 / 61, 4)},
        "v3": {
            "correctos": correctos_total,
            "total_medibles": total_medibles,
            "total_con_invalidas": len(casos),
            "invalidas_excluidas": len(invalidas),
            "precision_sobre_medibles": round(correctos_total / total_medibles, 4)
            if total_medibles else None,
        },
        "por_categoria": {
            k: {**v, "precision": round(v["correctos"] / v["total"], 4) if v["total"] else None}
            for k, v in por_categoria.items()
        },
        "criterio_aceptacion_hu9": {"umbral": 0.85, "cumple": (
            (correctos_total / total_medibles) >= 0.85 if total_medibles else False
        )},
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    RESULTADOS_PATH.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    REGRESION_PATH.write_text(
        json.dumps(regresiones, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    INVALIDAS_PATH.write_text(
        json.dumps(invalidas, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Resultados -> {RESULTADOS_PATH}")
    print(f"Regresiones ({len(regresiones)}) -> {REGRESION_PATH}")
    print(f"Respuestas inválidas ({len(invalidas)}) -> {INVALIDAS_PATH}")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lote", help="rango 'desde:hasta', ej. 0:20")
    parser.add_argument(
        "--reporte-final", action="store_true",
        help="genera resultados_v3.json y casos_regresion_v3.json a partir de los parciales",
    )
    args = parser.parse_args()

    casos = _cargar_casos()

    if args.lote:
        desde_str, hasta_str = args.lote.split(":")
        _correr_lote(casos, int(desde_str), int(hasta_str))
    elif args.reporte_final:
        _generar_reporte_final(casos)
    else:
        parser.error("Usá --lote desde:hasta o --reporte-final")


if __name__ == "__main__":
    main()
