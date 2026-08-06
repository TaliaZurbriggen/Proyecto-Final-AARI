"""Pruebas deterministas del evaluador de AARI-112, sin usar Gemini."""

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).parent / "data" / "measure_precision_v3.py"
SPEC = importlib.util.spec_from_file_location("measure_precision_v3", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
measure_precision_v3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measure_precision_v3)


def test_un_motivo_unico_de_escalado_debe_coincidir():
    obtenido = {
        "tipo_gasto": None,
        "debe_escalar": True,
        "motivo_escalado": "confianza_insuficiente",
    }

    assert not measure_precision_v3._es_resultado_correcto(
        None,
        True,
        ["riesgo_seguridad"],
        obtenido,
    )


def test_un_motivo_alternativo_expresamente_aceptado_es_valido():
    obtenido = {
        "tipo_gasto": None,
        "debe_escalar": True,
        "motivo_escalado": "multiples_rubros",
    }

    assert measure_precision_v3._es_resultado_correcto(
        None,
        True,
        ["riesgo_seguridad", "multiples_rubros"],
        obtenido,
    )


def test_respuesta_invalida_cuenta_en_el_denominador_principal(tmp_path):
    casos = [
        {
            "id": "caso-valido",
            "categoria_esperada": "ordinario",
            "escalar_esperado": False,
        },
        {
            "id": "caso-invalido",
            "categoria_esperada": "extraordinario",
            "escalar_esperado": False,
        },
    ]
    parciales = {
        "caso-valido": {
            "esperado": {"categoria": "ordinario", "escalar": False, "motivo_esperado": None, "motivos_aceptables": None},
            "obtenido": {"tipo_gasto": "ordinario", "debe_escalar": False, "motivo_escalado": None, "confianza": 0.9},
        },
        "caso-invalido": {
            "esperado": {"categoria": "extraordinario", "escalar": False, "motivo_esperado": None, "motivos_aceptables": None},
            "obtenido": {"tipo_gasto": None, "debe_escalar": True, "motivo_escalado": "respuesta_modelo_invalida", "confianza": None},
        },
    }
    measure_precision_v3.PARCIALES_PATH = tmp_path / "parciales.json"
    measure_precision_v3.RESULTADOS_PATH = tmp_path / "resultados.json"
    measure_precision_v3.REGRESION_PATH = tmp_path / "regresiones.json"
    measure_precision_v3.INVALIDAS_PATH = tmp_path / "invalidas.json"
    measure_precision_v3.PARCIALES_PATH.write_text(json.dumps(parciales), encoding="utf-8")

    measure_precision_v3._generar_reporte_final(casos)

    resultado = json.loads(measure_precision_v3.RESULTADOS_PATH.read_text(encoding="utf-8"))
    assert resultado["v3"]["correctos"] == 1
    assert resultado["v3"]["total"] == 2
    assert resultado["v3"]["precision"] == 0.5
    assert resultado["v3"]["respuestas_invalidas"] == 1