"""Pruebas deterministas del evaluador de AARI-112, sin usar Gemini."""

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).parent / "data" / "measure_precision_v5.py"
SPEC = importlib.util.spec_from_file_location("measure_precision_v5", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
measure_precision_v5 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measure_precision_v5)

def test_evaluador_v5_usa_los_80_casos_validados():
    assert measure_precision_v5.CASOS_PATH.name == "conjunto_prueba_80_casos.json"
    assert len(measure_precision_v5._cargar_casos()) == 80


def test_un_motivo_unico_de_escalado_debe_coincidir():
    obtenido = {
        "tipo_gasto": None,
        "debe_escalar": True,
        "motivo_escalado": "confianza_insuficiente",
    }

    assert not measure_precision_v5._es_resultado_correcto(
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

    assert measure_precision_v5._es_resultado_correcto(
        None,
        True,
        ["riesgo_seguridad", "multiples_rubros"],
        obtenido,
    )


def test_respuesta_invalida_cuenta_en_el_denominador_principal(tmp_path, monkeypatch):
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
    monkeypatch.setattr(measure_precision_v5, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(
        measure_precision_v5, "PARCIALES_PATH", tmp_path / "parciales.json"
    )
    monkeypatch.setattr(
        measure_precision_v5, "RESULTADOS_PATH", tmp_path / "resultados.json"
    )
    monkeypatch.setattr(
        measure_precision_v5, "REGRESION_PATH", tmp_path / "regresiones.json"
    )
    monkeypatch.setattr(
        measure_precision_v5, "INVALIDAS_PATH", tmp_path / "invalidas.json"
    )
    measure_precision_v5.PARCIALES_PATH.write_text(json.dumps(parciales), encoding="utf-8")

    measure_precision_v5._generar_reporte_final(casos)

    resultado = json.loads(measure_precision_v5.RESULTADOS_PATH.read_text(encoding="utf-8"))
    assert resultado["v5"]["correctos"] == 1
    assert resultado["v5"]["total"] == 2
    assert resultado["v5"]["precision"] == 0.5
    assert resultado["v5"]["respuestas_invalidas"] == 1

def test_lote_guarda_un_checkpoint_por_cada_respuesta(tmp_path, monkeypatch):
    class GrafoSimulado:
        def invoke(self, _state):
            return {
                "tipo_gasto": "ordinario",
                "debe_escalar": False,
                "motivo_escalado": None,
                "confianza": 0.9,
            }

    casos = [
        {
            "id": "caso-1",
            "descripcion": "Una canilla gotea.",
            "urgencia": "baja",
            "categoria_esperada": "ordinario",
            "escalar_esperado": False,
        },
        {
            "id": "caso-2",
            "descripcion": "Otra canilla gotea.",
            "urgencia": "baja",
            "categoria_esperada": "ordinario",
            "escalar_esperado": False,
        },
    ]
    checkpoints = []
    guardar_original = measure_precision_v5._guardar_parciales

    def guardar_y_registrar(parciales):
        guardar_original(parciales)
        checkpoints.append(len(parciales))

    monkeypatch.setattr(measure_precision_v5, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(
        measure_precision_v5, "PARCIALES_PATH", tmp_path / "parciales.json"
    )
    monkeypatch.setattr(
        measure_precision_v5, "build_classification_graph", lambda: GrafoSimulado()
    )
    monkeypatch.setattr(measure_precision_v5, "_guardar_parciales", guardar_y_registrar)

    measure_precision_v5._correr_lote(casos, 0, 2)

    assert checkpoints == [1, 2]
    assert set(json.loads((tmp_path / "parciales.json").read_text(encoding="utf-8"))) == {
        "caso-1",
        "caso-2",
    }

def test_reporte_v5_separa_metricas_por_origen(tmp_path, monkeypatch):
    casos = [
        {
            "id": "baseline",
            "categoria_esperada": "ordinario",
            "escalar_esperado": False,
            "conjunto_origen": "baseline_61",
        },
        {
            "id": "holdout",
            "categoria_esperada": None,
            "escalar_esperado": True,
            "motivo_escalado_esperado": "causa_no_identificable",
            "conjunto_origen": "holdout_19",
        },
    ]
    parciales = {
        "baseline": {
            "esperado": {"categoria": "ordinario", "escalar": False, "motivo_esperado": None, "motivos_aceptables": None},
            "obtenido": {"tipo_gasto": "ordinario", "debe_escalar": False, "motivo_escalado": None, "confianza": 0.9},
        },
        "holdout": {
            "esperado": {"categoria": None, "escalar": True, "motivo_esperado": "causa_no_identificable", "motivos_aceptables": None},
            "obtenido": {"tipo_gasto": "ordinario", "debe_escalar": False, "motivo_escalado": None, "confianza": 0.9},
        },
    }
    monkeypatch.setattr(measure_precision_v5, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(measure_precision_v5, "PARCIALES_PATH", tmp_path / "parciales.json")
    monkeypatch.setattr(measure_precision_v5, "RESULTADOS_PATH", tmp_path / "resultados.json")
    monkeypatch.setattr(measure_precision_v5, "REGRESION_PATH", tmp_path / "regresiones.json")
    monkeypatch.setattr(measure_precision_v5, "INVALIDAS_PATH", tmp_path / "invalidas.json")
    measure_precision_v5.PARCIALES_PATH.write_text(json.dumps(parciales), encoding="utf-8")

    measure_precision_v5._generar_reporte_final(casos)

    resultado = json.loads(measure_precision_v5.RESULTADOS_PATH.read_text(encoding="utf-8"))
    assert resultado["v5"]["correctos"] == 1
    assert resultado["v5"]["total"] == 2
    assert resultado["por_origen"]["baseline_61"]["precision"] == 1.0
    assert resultado["por_origen"]["holdout_19"]["precision"] == 0.0
    assert resultado["criterio_aceptacion_hu9"]["universo"] == "80 casos validados con Oikos"
