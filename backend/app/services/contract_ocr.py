"""OCR del flujo actual, con liberación determinista de recursos nativos.

El adaptador histórico de contract_text_extraction permanece congelado para
reproducir sus evaluaciones. El worker actual utiliza este motor explícitamente.
"""

from contextlib import ExitStack
import os

from app.services.contract_text_extraction import ContractTextError, OCR_RENDER_SCALE


class ManagedTesseractOcrEngine:
    """Copia la imagen antes de cerrar PDFium y no depende del recolector de basura."""

    def read_page(self, pdf: bytes, page_index: int) -> str:
        try:
            import pypdfium2 as pdfium
            import pytesseract
        except ImportError as error:
            raise ContractTextError("El OCR local no está instalado.") from error

        pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD", "tesseract")
        language = os.getenv("TESSERACT_LANGUAGE", "spa")
        try:
            # ExitStack ejecuta todos los cierres (en orden inverso), incluso
            # si falla el render, la copia de PIL, Tesseract o algún cierre.
            with ExitStack() as images:
                with ExitStack() as native:
                    document = pdfium.PdfDocument(pdf)
                    native.callback(document.close)
                    page = document[page_index]
                    native.callback(page.close)
                    bitmap = page.render(scale=OCR_RENDER_SCALE)
                    native.callback(bitmap.close)
                    borrowed_image = bitmap.to_pil()
                    native.callback(borrowed_image.close)
                    image = borrowed_image.copy()
                    images.callback(image.close)
                # La imagen es independiente: no conserva el buffer del bitmap.
                return pytesseract.image_to_string(image, lang=language)
        except Exception as error:
            raise ContractTextError("No se pudo leer una página escaneada con OCR.") from error
