"""Recursos del OCR actual: pruebas locales sin Tesseract ni APIs externas."""

import sys
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.contract_clause_service import ContractClauseService
from app.services.contract_ocr import ManagedTesseractOcrEngine
from app.services.contract_text_extraction import ContractTextError, OCR_RENDER_SCALE


def install_fake_ocr(monkeypatch, failure=None):
    closed = []

    def step(name, result):
        if failure == name:
            raise RuntimeError("Fallo sintético")
        return result

    def resource(name):
        def close():
            closed.append(name)
            step(f"{name}_close", None)
        return SimpleNamespace(close=Mock(side_effect=close))

    image = resource("image")
    borrowed = resource("borrowed")
    borrowed.copy = Mock(side_effect=lambda: step("copy", image))
    bitmap = resource("bitmap")
    bitmap.to_pil = Mock(side_effect=lambda: step("to_pil", borrowed))
    page = resource("page")
    page.render = Mock(side_effect=lambda **_: step("render", bitmap))

    class Document:
        def __init__(self):
            self.close = resource("document").close

        def __getitem__(self, index):
            assert index == 2
            return step("page", page)

    document = Document()
    factory = Mock(side_effect=lambda _: step("document", document))

    def recognize(received, *, lang):
        assert received is image and received is not borrowed
        assert closed == ["borrowed", "bitmap", "page", "document"]
        assert lang == "spa"
        return step("ocr", "Texto reconocido")

    recognize_mock = Mock(side_effect=recognize)
    monkeypatch.setenv("TESSERACT_LANGUAGE", "spa")
    monkeypatch.setenv("TESSERACT_CMD", "ocr-sintetico")
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=factory))
    monkeypatch.setitem(sys.modules, "pytesseract", SimpleNamespace(
        pytesseract=SimpleNamespace(), image_to_string=recognize_mock,
    ))
    return closed, page, recognize_mock


def test_ocr_copies_image_and_closes_native_resources_before_tesseract(monkeypatch):
    closed, page, recognize = install_fake_ocr(monkeypatch)

    assert ManagedTesseractOcrEngine().read_page(b"PDF sintetico", 2) == "Texto reconocido"
    page.render.assert_called_once_with(scale=OCR_RENDER_SCALE)
    recognize.assert_called_once()
    assert closed == ["borrowed", "bitmap", "page", "document", "image"]


@pytest.mark.parametrize("failure, expected", [
    ("document", []),
    ("page", ["document"]),
    ("render", ["page", "document"]),
    ("to_pil", ["bitmap", "page", "document"]),
    ("copy", ["borrowed", "bitmap", "page", "document"]),
    ("ocr", ["borrowed", "bitmap", "page", "document", "image"]),
    ("bitmap_close", ["borrowed", "bitmap", "page", "document", "image"]),
])
def test_ocr_closes_all_created_resources_when_a_stage_fails(monkeypatch, failure, expected):
    closed, _, recognize = install_fake_ocr(monkeypatch, failure)

    with pytest.raises(ContractTextError, match="No se pudo leer"):
        ManagedTesseractOcrEngine().read_page(b"PDF sintetico", 2)

    assert closed == expected
    assert recognize.call_count == (1 if failure == "ocr" else 0)


def test_current_worker_uses_managed_ocr_and_preserves_injected_engine():
    assert isinstance(ContractClauseService(Mock(), Mock()).ocr, ManagedTesseractOcrEngine)
    injected = Mock()
    assert ContractClauseService(Mock(), Mock(), ocr=injected).ocr is injected


def test_ocr_reports_missing_optional_dependency_without_opening_resources(monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    with pytest.raises(ContractTextError, match="no está instalado"):
        ManagedTesseractOcrEngine().read_page(b"PDF sintetico", 2)


def test_detached_image_remains_readable_after_real_pdfium_resources_close(monkeypatch):
    from PIL import Image
    import pytesseract

    pdf = BytesIO()
    with Image.new("RGB", (80, 60), "white") as source:
        source.save(pdf, format="PDF")

    def recognize(image, *, lang):
        assert image.width > 0 and image.height > 0
        assert image.getpixel((0, 0)) == (255, 255, 255)
        return "Lectura simulada de una imagen real"

    monkeypatch.setattr(pytesseract, "image_to_string", recognize)
    assert ManagedTesseractOcrEngine().read_page(pdf.getvalue(), 0).startswith("Lectura simulada")


def test_assisted_evaluation_harness_can_renew_in_memory_lease(monkeypatch, tmp_path):
    from scripts import evaluate_contract_assisted as evaluation
    from app.services import contract_clause_service as service
    from app.services.contract_text_extraction import ContractText, PageText

    synthetic_pdf = tmp_path / "public.pdf"
    synthetic_pdf.write_bytes(b"PDF de prueba")
    monkeypatch.setattr(evaluation, "load_json", lambda _: {})
    monkeypatch.setattr(evaluation, "get_document", lambda *_: {
        "source_url": "https://example.com/public.pdf", "sha256": "0" * 64,
    })
    monkeypatch.setattr(evaluation, "verify_document", lambda *_: synthetic_pdf)
    monkeypatch.setattr(service, "extract_contract_text", lambda *_: ContractText([
        PageText(1, "PRIMERA: Avisar los daños.", "digital", True),
    ], True))
    model = SimpleNamespace(invoke=Mock(return_value='{"clausulas": []}'),
                            http_requests=0, http_statuses=[])
    monkeypatch.setattr(evaluation.assisted, "JsonClauseModel", lambda *_: model)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")

    result = evaluation.run_public_v04(tmp_path / "result.json")

    assert result["state"] == "completed"
    assert result["http_requests"] == 0
    model.invoke.assert_called_once()
