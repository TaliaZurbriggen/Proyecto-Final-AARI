"""Mide la precisión del prompt v4 contra conjunto_prueba_80_casos.json.

Uso (desde backend/, con GEMINI_API_KEY configurada en .env):

    python -m tests.data.measure_precision_v4 --lote 0:20
    python -m tests.data.measure_precision_v4 --lote 20:40
    python -m tests.data.measure_precision_v4 --lote 40:60
    python -m tests.data.measure_precision_v4 --lote 60:80
    python -m tests.data.measure_precision_v4 --reporte-final

Corre en lotes por diseño: cada llamada real a Gemini consume créditos, y
AARI-112 requiere autorización explícita antes de cada tanda de hasta 20.

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
CASOS_PATH = BACKEND_DIR / "tests" / "data" / "conjunto_prueba_80_casos.json"
EVAL_DIR = BACKEND_DIR.parent / "docs" / "evaluaciones" / "aari112"
PARCIALES_PATH = EVAL_DIR / "resultados_v4_parciales.json"
RESULTADOS_PATH = EVAL_DIR / "resultados_v4.json"
REGRESION_PATH = EVAL_DIR / "casos_regresion_v4.json"
INVALIDAS_PATH = EVAL_DIR / "respuestas_invalidas_v4.json"


def _cargar_casos() -> list[dict]:
    data = json.loads(CASOS_PATH.read_text(encoding="utf-8"))
    return data["casos"]


def _cargar_parciales() -> dict[str, dict]:
    if PARCIALES_PATH.exists():
        return json.loads(PARCIALES_PATH.read_text(encoding="utf-8"))
    return {}


def _guardar_parciales(parciales: dict[str, dict]) -> None:
    """Persiste cada avance sin dejar un checkpoint parcialmente escrito."""

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    temporal = PARCIALES_PATH.with_suffix(".tmp")
    temporal.write_text(
        json.dumps(parciales, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    temporal.replace(PARCIALES_PATH)


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
                "motivo_esperado": caso.get("motivo_escalado_esperado"),
                "motivos_aceptables": caso.get("motivos_aceptables"),
            },
            "obtenido": {
                "tipo_gasto": resultado.get("tipo_gasto"),
                "debe_escalar": resultado.get("debe_escalar"),
                "motivo_escalado": resultado.get("motivo_escalado"),
                "confianza": resultado.get("confianza"),
            },
        }
        _guardar_parciales(parciales)
        print(f"{caso['id']}: esperado={caso['categoria_esperada']}/"
              f"escalar={caso['escalar_esperado']} -> "
              f"obtenido={resultado.get('tipo_gasto')}/"
              f"escalar={resultado.get('debe_escalar')}/"
              f"{resultado.get('motivo_escalado')}")

    print(f"\nGuardado en {PARCIALES_PATH} ({len(parciales)}/{len(casos)} casos medidos)")


def _es_resultado_correcto(
    categoria_esperada: str | None,
    escalar_esperado: bool,
    motivos_validos: list[str],
    obtenido: dict,
) -> bool:
    """Evalúa una respuesta válida con el mismo contrato que el conjunto de prueba."""

    if escalar_esperado:
        return (
            obtenido["debe_escalar"] is True
            and obtenido["motivo_escalado"] in motivos_validos
        )
    return (
        obtenido["debe_escalar"] is False
        and obtenido["tipo_gasto"] == categoria_esperada
    )


def _metricas(conteo: dict[str, int]) -> dict[str, int | float | None]:
    total = conteo["total"]
    correctos = conteo["correctos"]
    invalidas = conteo.get("respuestas_invalidas", 0)
    return {
        **conteo,
        "precision": round(correctos / total, 4) if total else None,
        "precision_sobre_respuestas_validas": (
            round(correctos / (total - invalidas), 4)
            if total - invalidas > 0 else None
        ),
    }


def _generar_reporte_final(casos: list[dict]) -> None:
    parciales = _cargar_parciales()
    faltantes = [c["id"] for c in casos if c["id"] not in parciales]
    if faltantes:
        raise SystemExit(
            f"Faltan {len(faltantes)} casos por medir: {faltantes}. "
            "Corré los lotes pendientes antes de generar el reporte final."
        )

    por_categoria: dict[str, dict[str, int]] = {}
    por_origen: dict[str, dict[str, int]] = {}
    por_origen_y_categoria: dict[str, dict[str, dict[str, int]]] = {}
    regresiones = []
    invalidas = []
    correctos_total = 0

    for caso in casos:
        p = parciales[caso["id"]]
        esperado_cat = p["esperado"]["categoria"]
        esperado_escalar = p["esperado"]["escalar"]
        motivos_ok = p["esperado"]["motivos_aceptables"]
        motivo_esperado = p["esperado"].get("motivo_esperado")
        obtenido = p["obtenido"]
        origen = caso.get("conjunto_origen", "sin_origen")
        clave_cat = "escalar" if esperado_escalar else esperado_cat

        por_categoria.setdefault(
            clave_cat, {"total": 0, "correctos": 0, "respuestas_invalidas": 0}
        )
        por_origen.setdefault(
            origen, {"total": 0, "correctos": 0, "respuestas_invalidas": 0}
        )
        por_origen_y_categoria.setdefault(origen, {})
        por_origen_y_categoria[origen].setdefault(
            clave_cat, {"total": 0, "correctos": 0, "respuestas_invalidas": 0}
        )

        bloques = (
            por_categoria[clave_cat],
            por_origen[origen],
            por_origen_y_categoria[origen][clave_cat],
        )
        for bloque in bloques:
            bloque["total"] += 1

        if obtenido["motivo_escalado"] == "respuesta_modelo_invalida":
            invalidas.append({"id": caso["id"], "conjunto_origen": origen, **p})
            for bloque in bloques:
                bloque["respuestas_invalidas"] += 1
            continue

        motivos_validos = motivos_ok or ([motivo_esperado] if motivo_esperado else [])
        es_correcto = _es_resultado_correcto(
            esperado_cat,
            esperado_escalar,
            motivos_validos,
            obtenido,
        )

        if es_correcto:
            correctos_total += 1
            for bloque in bloques:
                bloque["correctos"] += 1
        else:
            regresiones.append({
                "id": caso["id"],
                "conjunto_origen": origen,
                "descripcion_error": (
                    "sobreescalado"
                    if (esperado_escalar is False and obtenido["debe_escalar"])
                    else "escalamiento_omitido"
                    if (esperado_escalar is True and not obtenido["debe_escalar"])
                    else "motivo_o_categoria_incorrecta"
                ),
                **p,
            })

    total = len(casos)
    total_respuestas_validas = total - len(invalidas)
    precision_macro = (
        sum(v["correctos"] / v["total"] for v in por_categoria.values())
        / len(por_categoria)
        if por_categoria else None
    )
    resultado = {
        "prompt_version": "v4",
        "referencia_v3_observada": {
            "correctos": 48,
            "total_ejecutado": 60,
            "precision": 0.8,
            "nota": "V3 se cerró antes del caso 61; no existe resultado observado sobre 61.",
        },
        "v4": {
            "correctos": correctos_total,
            "total": total,
            "precision": round(correctos_total / total, 4) if total else None,
            "respuestas_invalidas": len(invalidas),
            "precision_sobre_respuestas_validas": (
                round(correctos_total / total_respuestas_validas, 4)
                if total_respuestas_validas else None
            ),
            "precision_macro": (
                round(precision_macro, 4) if precision_macro is not None else None
            ),
        },
        "por_origen": {k: _metricas(v) for k, v in por_origen.items()},
        "por_categoria": {k: _metricas(v) for k, v in por_categoria.items()},
        "por_origen_y_categoria": {
            origen: {categoria: _metricas(valores) for categoria, valores in categorias.items()}
            for origen, categorias in por_origen_y_categoria.items()
        },
        "criterio_aceptacion_hu9": {
            "umbral": 0.85,
            "universo": "80 casos validados con Oikos",
            "cumple": ((correctos_total / total) >= 0.85 if total else False),
        },
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    for path, data in (
        (RESULTADOS_PATH, resultado),
        (REGRESION_PATH, regresiones),
        (INVALIDAS_PATH, invalidas),
    ):
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
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
        help="genera resultados_v4.json y casos_regresion_v4.json a partir de los parciales",
    )
    args = parser.parse_args()

    casos = _cargar_casos()

    if args.lote:
        desde_str, hasta_str = args.lote.split(":")
        desde, hasta = int(desde_str), int(hasta_str)
        if not 0 <= desde < hasta <= len(casos):
            raise SystemExit(
                f"Rango inválido {desde}:{hasta}; debe cumplir 0 <= desde < hasta <= {len(casos)}."
            )
        if hasta - desde > 20:
            raise SystemExit("Cada lote puede contener como máximo 20 casos.")
        _correr_lote(casos, desde, hasta)
    elif args.reporte_final:
        _generar_reporte_final(casos)
    else:
        parser.error("Usá --lote desde:hasta o --reporte-final")


if __name__ == "__main__":
    main()
