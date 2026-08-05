"""Pruebas del loader de recursos del clasificador (AARI-112).

Cubren el bug de AARI-112: resources.py apuntaba a prompt_clasificacion_v3.md
pero el regex del loader seguía buscando el encabezado "(v2)", por lo que
load_prompt_template() lanzaba ValueError al iniciar la app.
"""

import pytest

from app.agents.classification.resources import (
    PROMPT_PATH,
    load_prompt_template,
)
from app.agents.classification.llm import build_classification_prompt


def test_prompt_path_apunta_a_v3():
    assert PROMPT_PATH.name == "prompt_clasificacion_v3.md"


def test_load_prompt_template_no_lanza_y_tiene_los_4_pasos():
    prompt = load_prompt_template()
    assert "PASO 1" in prompt
    assert "PASO 2" in prompt
    assert "PASO 3" in prompt
    assert "PASO 4" in prompt


def test_prompt_lee_campos_especiales_de_la_kb():
    """AARI-112: el prompt debe mencionar explícitamente los 4 campos
    especiales de base_conocimiento.json, no solo ejemplos de texto libre."""
    prompt = load_prompt_template()
    for campo in (
        "escalar_urgente",
        "escalar_si_falta_contexto",
        "requiere_causa_explicita",
        "admite_override_contractual",
    ):
        assert campo in prompt, f"El prompt no menciona el campo especial '{campo}'"


def test_prompt_no_le_pide_al_modelo_respuesta_modelo_invalida():
    """respuesta_modelo_invalida lo asigna el código (nodes.py) ante fallos
    de parseo/validación; el modelo nunca debe intentar producirlo."""
    prompt = load_prompt_template()
    # El único lugar donde puede aparecer es en texto explicativo por fuera
    # del contrato de salida que se le pide al modelo (sección "motivo_escalado").
    output_block_start = prompt.index('"tipo_gasto":')
    output_block = prompt[output_block_start : output_block_start + 400]
    assert "respuesta_modelo_invalida" not in output_block


def test_build_classification_prompt_no_deja_placeholders_sin_resolver():
    state = {
        "descripcion": "La canilla de la cocina gotea desde hace unos días.",
        "urgencia": "baja",
        "rubro_declarado": "plomeria",
        "clausulas_contrato": [],
    }
    prompt = build_classification_prompt(state, confidence_threshold=0.75)

    assert "{{" not in prompt
    assert "}}" not in prompt
    assert "La canilla de la cocina gotea desde hace unos días." in prompt
    assert "0.75" in prompt


def test_build_classification_prompt_sin_rubro_ni_clausulas_usa_fallback():
    state = {
        "descripcion": "Se cortó la luz en el dormitorio.",
        "urgencia": "media",
    }
    prompt = build_classification_prompt(state, confidence_threshold=0.75)

    assert "no disponible" in prompt
    assert "{{" not in prompt
