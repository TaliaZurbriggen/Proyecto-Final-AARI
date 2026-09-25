"""HU30: extracción, validación y orquestación sin servicios externos."""

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.db.clausulas_contrato import AnalysisJob
from app.schemas.clausulas_contrato import ExtractedClauseBatch
from app.services.contract_clause_llm import (
    EXTRACTOR_VERSION,
    PROMPT_PATH,
    PROMPT_VERSION,
    build_clause_prompt,
    get_clause_model,
    validate_evidence,
)
from app.services.contract_clause_service import ContractClauseService
from app.services.contract_errors import ContractError
from app.services.contract_text_extraction import (
    ContractText, ContractTextError, PageText, extract_contract_text,
    minimize_personal_data,
)


def uid(n):
    return UUID(f"00000000-0000-0000-0000-{n:012d}")


class Page:
    def __init__(self, text): self.text = text
    def extract_text(self): return self.text


class Ocr:
    def __init__(self, value=None, error=False): self.value, self.error, self.calls = value, error, []
    def read_page(self, pdf, page_index):
        self.calls.append(page_index)
        if self.error: raise ContractTextError("OCR no disponible")
        return self.value


def test_extracts_digital_text_and_uses_ocr_only_for_scanned_pages(monkeypatch):
    digital = "Cláusula de mantenimiento " * 8
    scanned = "El inquilino deberá avisar el daño dentro de 24 horas. " * 4
    monkeypatch.setattr("app.services.contract_text_extraction.PdfReader",
                        lambda *_args, **_kwargs: SimpleNamespace(pages=[Page(digital), Page("")]))
    ocr = Ocr(scanned)
    result = extract_contract_text(b"pdf", ocr)
    assert result.complete is True
    assert [page.method for page in result.pages] == ["digital", "ocr"]
    assert ocr.calls == [1]
    assert "[PÁGINA 2]" in result.model_text and scanned.strip() in result.model_text


def test_marks_partial_reading_and_rejects_a_fully_unreadable_pdf(monkeypatch):
    useful = "Contenido contractual legible " * 8
    monkeypatch.setattr("app.services.contract_text_extraction.PdfReader",
                        lambda *_args, **_kwargs: SimpleNamespace(pages=[Page(useful), Page("")]))
    partial = extract_contract_text(b"pdf", Ocr(error=True))
    assert partial.complete is False and partial.pages[1].method == "sin_lectura"
    monkeypatch.setattr("app.services.contract_text_extraction.PdfReader",
                        lambda *_args, **_kwargs: SimpleNamespace(pages=[Page("")]))
    with pytest.raises(ContractTextError, match="obtener texto"):
        extract_contract_text(b"pdf", Ocr(error=True))


@pytest.mark.skipif(
    os.getenv("RUN_CLAUSES_OCR_TESTS") != "1",
    reason="Requiere Tesseract local con el idioma español instalado.",
)
def test_tesseract_reads_a_synthetic_scanned_pdf():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=42)
    lines = [
        "CONTRATO DE ALQUILER",
        "El inquilino debe avisar los daños dentro de veinticuatro horas.",
        "La reparación será evaluada según la causa informada.",
        "Este texto es sintético y no contiene datos personales.",
    ]
    for index, line in enumerate(lines):
        draw.text((70, 90 + index * 120), line, fill="black", font=font)
    buffer = BytesIO()
    image.save(buffer, format="PDF", resolution=150)

    result = extract_contract_text(buffer.getvalue())

    assert result.complete is True
    assert result.pages[0].method == "ocr"
    assert "inquilino" in result.pages[0].text.casefold()
    assert "veinticuatro horas" in result.pages[0].text.casefold()


def test_minimizes_common_identifiers_before_model():
    result = minimize_personal_data(
        "DNI 30123456, email persona@example.com y teléfono +54 9 3564 555555"
    )
    assert "30123456" not in result and "persona@example.com" not in result
    assert "+54 9 3564" not in result


def test_external_contract_analysis_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")

    with pytest.raises(RuntimeError, match="análisis externo está deshabilitado"):
        get_clause_model()


def test_v4_prompt_requires_atomic_evidence_and_neutral_ambiguity():
    prompt = build_clause_prompt("[PÁGINA 1]\nTexto contractual sintético.")

    assert PROMPT_VERSION == "v4"
    assert EXTRACTOR_VERSION == "hu30-v4"
    assert PROMPT_PATH.name == "prompt_extraccion_clausulas_v4.md"
    assert "Una regla verificable por propuesta" in prompt
    assert "el fragmento más corto" in prompt
    assert "responsable: no_especificado" in prompt
    assert "uso_clasificador: contexto" in prompt
    assert "ninguna coordinación ambigua haya quedado como `operativa`" in prompt
    assert "Texto contractual sintético." in prompt
    assert "{{TEXTO_CONTRATO}}" not in prompt


def test_external_model_uses_function_calling_and_pydantic_validation(monkeypatch):
    captured = {}

    class FakeChatModel:
        def __init__(self, **kwargs):
            captured["configuration"] = kwargs

        def with_structured_output(self, schema, *, method):
            captured["schema"] = schema
            captured["method"] = method
            return "structured-model"

    monkeypatch.setenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    monkeypatch.setattr(
        "app.services.contract_clause_llm.ChatGoogleGenerativeAI", FakeChatModel
    )

    assert get_clause_model() == "structured-model"
    assert captured["schema"] is ExtractedClauseBatch
    assert captured["method"] == "function_calling"


def test_discards_model_evidence_that_is_not_on_declared_pages():
    batch = ExtractedClauseBatch.model_validate({"clausulas": [{
        "numero": "NOVENA", "titulo": "Reparaciones",
        "evidencias": [{"pagina": 2, "texto": "El inquilino repara cuando existe culpa."}],
        "resumen": "La responsabilidad depende de culpa.", "categoria": "reparacion",
        "responsable": "condicional", "condiciones": "Debe existir culpa.",
        "uso_clasificador": "operativa", "referencias": [], "confianza": 0.9,
    }, {
        "numero": "X", "titulo": None,
        "evidencias": [{"pagina": 3, "texto": "Texto inventado"}],
        "resumen": "No existe.",
        "categoria": "otro", "responsable": "no_especificado",
        "uso_clasificador": "contexto", "condiciones": None,
        "referencias": [], "confianza": 0.4,
    }]})
    valid, rejected, incidents = validate_evidence(batch, {
        2: "EL INQUILINO REPARA cuando existe culpa.", 3: "Contenido diferente",
    })
    assert len(valid) == 1 and valid[0].numero == "NOVENA"
    assert rejected[0].ordinal == 2
    assert rejected[0].propuesta.numero == "X"
    assert rejected[0].evidencias_invalidas[0].pagina == 3
    assert len(incidents) == 1


def test_validates_each_page_of_a_cross_page_clause_and_normalizes_hyphenation():
    batch = ExtractedClauseBatch.model_validate({"clausulas": [{
        "numero": "NOVENA (d)", "titulo": "Roturas imputables",
        "evidencias": [
            {"pagina": 5, "texto": "El locatario reparará los desperfectos"},
            {"pagina": 6, "texto": "cuando la causa le resulte imputable."},
        ],
        "resumen": "La reparación depende de que la causa sea imputable.",
        "categoria": "reparacion", "responsable": "condicional",
        "uso_clasificador": "operativa", "condiciones": "Causa imputable.",
        "referencias": [], "confianza": 0.95,
    }, {
        "numero": "X", "titulo": "Texto con palabra cortada",
        "evidencias": [{"pagina": 7, "texto": "responsabilidad contractual"}],
        "resumen": "Texto normalizado.", "categoria": "otro",
        "responsable": "no_especificado", "uso_clasificador": "contexto",
        "condiciones": None, "referencias": [], "confianza": 0.8,
    }]})

    valid, rejected, incidents = validate_evidence(batch, {
        5: "El locatario reparará los desperfectos",
        6: "cuando la causa le resulte imputable.",
        7: "responsa-\nbilidad contractual",
    })

    assert [item.numero for item in valid] == ["NOVENA (d)", "X"]
    assert valid[0].paginas == [5, 6]
    assert rejected == [] and incidents == []


@dataclass
class FakeRepository:
    job: AnalysisJob
    completed: dict | None = None
    failed: tuple | None = None
    def claim_due(self, *, limit=3): return [self.job]
    def complete(self, analysis_id, **data): self.completed = data; return True
    def fail(self, analysis_id, attempt, error): self.failed = (attempt, error); return True


class FakeModel:
    def __init__(self, response): self.response = response
    def invoke(self, prompt):
        assert "[PÁGINA 1]" in prompt
        return self.response


def test_only_administration_can_request_an_analysis():
    service = ContractClauseService(None, None)
    tenant = SimpleNamespace(rol="inquilino", primer_ingreso=False)

    with pytest.raises(ContractError) as error:
        service.request(uid(1), uid(2), tenant)

    assert error.value.status == 403


def test_service_persists_only_validated_clauses(monkeypatch):
    job = AnalysisJob(uid(1), uid(2), uid(3), "private/doc.pdf", 1)
    repository = FakeRepository(job)
    text = "El LOCATARIO responde si el daño es atribuible a su culpa."
    monkeypatch.setattr("app.services.contract_clause_service.extract_contract_text",
                        lambda *_args: ContractText([PageText(1, text, "digital", True)], True))
    response = {"clausulas": [{
        "numero": "NOVENA", "titulo": "Daños",
        "evidencias": [{"pagina": 1, "texto": text}],
        "resumen": "Responsabilidad condicionada a culpa.",
        "categoria": "danio", "responsable": "condicional",
        "uso_clasificador": "operativa",
        "condiciones": "Daño atribuible a culpa.", "referencias": [], "confianza": 0.92,
    }]}
    storage = SimpleNamespace(download=lambda path: b"pdf")
    service = ContractClauseService(repository, storage, model_factory=lambda: FakeModel(response))
    assert service.process_due() == 1
    assert repository.failed is None
    assert repository.completed["complete"] is True
    assert len(repository.completed["clauses"]) == 1
    assert repository.completed["rejected"] == []


def test_service_keeps_an_ambiguous_rule_out_of_automatic_classification(monkeypatch):
    job = AnalysisJob(uid(11), uid(12), uid(13), "private/ambiguous.pdf", 1)
    repository = FakeRepository(job)
    text = (
        "La parte A realizará las tareas, salvo las originadas por terceros "
        "y las inspecciones periódicas."
    )
    monkeypatch.setattr(
        "app.services.contract_clause_service.extract_contract_text",
        lambda *_args: ContractText([PageText(1, text, "digital", True)], True),
    )
    response = {"clausulas": [{
        "numero": "CUARTA", "titulo": "Alcance sujeto a revisión",
        "evidencias": [{"pagina": 1, "texto": text}],
        "resumen": "El texto enumera tareas, una excepción por terceros e inspecciones.",
        "categoria": "mantenimiento", "responsable": "no_especificado",
        "uso_clasificador": "contexto",
        "condiciones": "Revisar si la excepción alcanza también a las inspecciones.",
        "referencias": [], "confianza": 0.6,
    }]}
    service = ContractClauseService(
        repository,
        SimpleNamespace(download=lambda path: b"pdf"),
        model_factory=lambda: FakeModel(response),
    )

    assert service.process_due() == 1
    clause = repository.completed["clauses"][0]
    assert clause.responsable == "no_especificado"
    assert clause.uso_clasificador == "contexto"
    assert clause.confianza <= 0.6
    assert repository.completed["rejected"] == []


def test_migration_protects_new_tables_and_snapshots_context():
    sql = (Path(__file__).parents[1] / "migrations" / "23_clausulas_contractuales.sql").read_text(encoding="utf-8").lower()
    for table in ("contrato_analisis", "contrato_clausulas", "contrato_clausula_eventos"):
        assert f"alter table public.{table} enable row level security" in sql
        assert table in sql
    assert "contexto_contractual_clasificacion jsonb" in sql
    assert "from public, anon, authenticated" in sql
    iteration = (Path(__file__).parents[1] / "migrations" / "24_evidencia_clausulas_contractuales.sql").read_text(encoding="utf-8").lower()
    assert "propuestas_rechazadas jsonb" in iteration
    assert "evidencias jsonb" in iteration
    assert "uso_clasificador" in iteration
