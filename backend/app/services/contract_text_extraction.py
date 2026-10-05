"""Lectura local de PDF con OCR selectivo y trazabilidad por página."""

import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from pypdf import PdfReader


MIN_DIGITAL_CHARACTERS = 80
MAX_MODEL_CHARACTERS = 90_000
OCR_RENDER_SCALE = 4.0


class ContractTextError(Exception):
    """El documento no pudo convertirse en texto utilizable."""


class OcrEngine(Protocol):
    def read_page(self, pdf: bytes, page_index: int) -> str: ...


class TesseractOcrEngine:
    """Renderiza una página y la procesa sin enviar el documento a terceros."""

    def read_page(self, pdf: bytes, page_index: int) -> str:
        try:
            import pypdfium2 as pdfium
            import pytesseract
        except ImportError as error:
            raise ContractTextError("El OCR local no está instalado.") from error

        pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD", "tesseract")
        language = os.getenv("TESSERACT_LANGUAGE", "spa")
        try:
            document = pdfium.PdfDocument(pdf)
            page = document[page_index]
            image = page.render(scale=OCR_RENDER_SCALE).to_pil()
            return pytesseract.image_to_string(image, lang=language)
        except Exception as error:
            raise ContractTextError("No se pudo leer una página escaneada con OCR.") from error


@dataclass(frozen=True)
class PageText:
    page: int
    text: str
    method: str
    readable: bool


@dataclass(frozen=True)
class ContractText:
    pages: list[PageText]
    complete: bool

    @property
    def model_text(self) -> str:
        return "\n\n".join(
            f"[PÁGINA {page.page}]\n{page.text}" for page in self.pages if page.text
        )


def _normalize(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\r\n?", "\n", text or "")).strip()


def _useful_characters(text: str) -> int:
    return sum(character.isalnum() for character in text)


def extract_contract_text(pdf: bytes, ocr: OcrEngine | None = None) -> ContractText:
    try:
        reader = PdfReader(BytesIO(pdf), strict=False)
    except Exception as error:
        raise ContractTextError("El PDF no pudo abrirse para el análisis.") from error

    ocr = ocr or TesseractOcrEngine()
    pages: list[PageText] = []
    for index, page in enumerate(reader.pages):
        try:
            digital = _normalize(page.extract_text() or "")
        except Exception:
            digital = ""
        if _useful_characters(digital) >= MIN_DIGITAL_CHARACTERS:
            pages.append(PageText(index + 1, digital, "digital", True))
            continue
        try:
            recognized = _normalize(ocr.read_page(pdf, index))
        except ContractTextError:
            recognized = digital
        readable = _useful_characters(recognized) >= MIN_DIGITAL_CHARACTERS
        pages.append(PageText(index + 1, recognized, "ocr" if recognized != digital else "sin_lectura", readable))

    if not any(page.text for page in pages):
        raise ContractTextError("No se pudo obtener texto del contrato.")
    return ContractText(pages=pages, complete=all(page.readable for page in pages))


def minimize_personal_data(text: str) -> str:
    """Enmascara identificadores frecuentes antes de construir el prompt."""

    patterns = [
        (r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", "[EMAIL OMITIDO]"),
        (r"(?i)\b(?:DNI|CUIT|CUIL)\s*(?:N[°ºo]\.?\s*)?[:#-]?\s*[\d.-]{7,15}\b", "[IDENTIFICADOR OMITIDO]"),
        (r"(?i)\b(?:tel(?:éfono)?|cel(?:ular)?|whatsapp)\s*[:#-]?\s*\+?[\d ()-]{7,20}\b", "[TELÉFONO OMITIDO]"),
    ]
    minimized = text
    for pattern, replacement in patterns:
        minimized = re.sub(pattern, replacement, minimized)
    if len(minimized) > MAX_MODEL_CHARACTERS:
        raise ContractTextError("El contrato supera el límite seguro de análisis.")
    return minimized
