"""El SDK de los diagnósticos de HU30 debe ser reproducible al instalar."""

import json
from pathlib import Path

import pytest


BACKEND = Path(__file__).resolve().parents[1]
BASELINE = (
    BACKEND.parent
    / "docs/evaluaciones/hu30/diagnostico_flash38_esquema_completo/resultado.json"
)


@pytest.mark.parametrize("package", ["langchain-google-genai", "google-genai"])
def test_requirements_pin_the_sdk_versions_recorded_in_hu30(package):
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    requirements = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    versions = [
        line.partition("==")[2]
        for line in requirements.splitlines()
        if line.partition("==")[0] == package
    ]
    assert versions == [baseline["packages"][package]], (
        f"requirements.txt debe fijar una única versión de {package}, "
        "igual a la evidencia histórica de HU30; no regenerar la evidencia."
    )
