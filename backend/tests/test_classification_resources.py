"""Validaciones de los insumos estáticos del clasificador."""

import json
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((BACKEND_DIR / relative_path).read_text(encoding="utf-8"))


def test_base_de_conocimiento_vigente_es_consistente() -> None:
    base = load_json("config/base_conocimiento.json")
    reglas = base["reglas"]

    assert base["version"] == "1.1"
    assert set(base["categorias_validas"]) == {"ordinario", "extraordinario", "expensa"}
    assert len(reglas) == 20
    assert len({regla["id"] for regla in reglas}) == len(reglas)


def test_conjunto_de_prueba_conserva_los_61_casos() -> None:
    conjunto = load_json("tests/data/conjunto_prueba_61_casos.json")
    casos = conjunto["casos"]

    assert conjunto["version"] == "1.1"
    assert conjunto["distribucion"]["total"] == 61
    assert len(casos) == 61
    assert len({caso["id"] for caso in casos}) == 61
    assert {caso["categoria_esperada"] for caso in casos if not caso["escalar_esperado"]} <= {
        "ordinario",
        "extraordinario",
        "expensa",
    }
