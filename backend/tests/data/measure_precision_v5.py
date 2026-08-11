"""Mide la precisión del prompt v5 contra conjunto_prueba_61_casos.json.

Uso (desde backend/, con GEMINI_API_KEY configurada en .env):

    python -m tests.data.measure_precision_v5 --lote 0:20
    python -m tests.data.measure_precision_v5 --lote 20:40
    python -m tests.data.measure_precision_v5 --lote 40:61
    python -m tests.data.measure_precision_v5 --reporte-final

Corre en lotes por diseño: cada llamada real a Gemini consume créditos, y
AARI-112 pide autorización explícita antes de cada tanda de 20.

Criterio de corte (decisión registrada para la iteración v5, ver
conclusiones de v4): no tiene sentido gastar cuota en el resto de los 61
casos si el primer lote (0:20) no alcanza al menos 17/20. Al cerrar ese
lote, el script imprime el resultado parcial contra ese piso a modo de
alerta — no bloquea la ejecución de lotes siguientes, la decisión de
seguir o no sigue siendo del equipo.

No sobrescribe evidencia de AARI-111 ni de la medición de v3: escribe
siempre en docs/evaluaciones/aari112/ con sufijo _v5, nunca pisa
resultados_v3.json ni resultados_v2.json.
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
PARCIALES_PATH = EVAL_DIR / "resultados_v5_parciales.json"
RESULTADOS_PATH = EVAL_DIR / "resultados_v5.json"
REGRESION_PATH = EVAL_DIR / "casos_regresion_v5.json"
INVALIDAS_PATH = EVAL_DIR / "respuestas_invalidas_v5.json"

PRIMER_LOTE_PISO = 17  # sobre 20 casos, ver criterio de corte en el docstring


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


def _es_correcto(caso: dict, obtenido: dict) -> bool:
    esperado_escalar = caso["escalar_esperado"]
    motivos_ok = caso.get("motivos_aceptables")

    if esperado_escalar:
        if obtenido["debe_escalar"] is not True:
            return False
        return obtenido["motivo_escalado"] in motivos_ok if motivos_ok else True

    return (
        obtenido["debe_escalar"] is False
        and obtenido["tipo_gasto"] == caso["categoria_esperada"]
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

    if desde == 0 and hasta == 20:
        _alertar_primer_lote(casos[:20], parciales)


def _alertar_primer_lote(primeros_20: list[dict], parciales: dict[str, dict]) -> None:
    medidos = [c for c in primeros_20 if c["id"] in parciales]
    if len(medidos) < 20:
        return  # lote incompleto (se corrió parcial), no evaluar todavía

    correctos = sum(
        1
        for c in medidos
        if parciales[c["id"]]["obtenido"]["motivo_escalado"] != "respuesta_modelo_invalida"
        and _es_correcto(c, parciales[c["id"]]["obtenido"])
    )
    print(
        f"\nPrimer lote (0:20): {correctos}/20 correctos "
        f"(piso de corte: {PRIMER_LOTE_PISO}/20)."
    )
    if correctos < PRIMER_LOTE_PISO:
        print(
            "⚠ No alcanza el piso acordado para seguir con el resto de los 61 casos. "
            "Revisar el prompt antes de gastar más cuota (ver sección 4.1 de "
            "prompt_clasificacion_v5.md)."
        )
    else:
        print("✓ Alcanza el piso acordado. Se puede continuar con los lotes siguientes.")


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
        obtenido = p["obtenido"]

        clave_cat = "escalar" if esperado_escalar else esperado_cat
        por_categoria.setdefault(clave_cat, {"total": 0, "correctos": 0})
        por_categoria[clave_cat]["total"] += 1

        if obtenido["motivo_escalado"] == "respuesta_modelo_invalida":
            invalidas.append({"id": caso["id"], **p})
            continue  # no cuenta como error de prompt, ver sección 4.3 del prompt v3

        es_correcto = _es_correcto(caso, obtenido)

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
        "prompt_version": "v5",
        "linea_base_v2": {"correctos": 35, "total": 61, "precision": round(35 / 61, 4)},
        "linea_base_v3": {"precision_aprox": 0.825},
        "v5": {
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
        help="genera resultados_v5.json y casos_regresion_v5.json a partir de los parciales",
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
