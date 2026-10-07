"""Preparación local del ejemplo 01. NO es el anonimizador de la aplicación.

Las zonas se seleccionaron al revisar este documento concreto. El script falla
si cambia su estructura. No contiene identificadores del original ni los imprime.
Requiere pdfplumber, pypdf, reportlab y las fuentes indicadas por CLI.
"""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

import pdfplumber
from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text):
    return re.sub(r"\s+", "", text).casefold()


def expanded_chars(page):
    """Un glifo Calibri puede representar fi/ti/fl; alinear texto y geometría."""
    result = []
    for char in page.chars:
        face = "SampleBold" if "Bold" in char["fontname"] else "SampleRegular"
        widths = [pdfmetrics.stringWidth(letter, face, char["size"]) for letter in char["text"]]
        total = sum(widths) or 1
        cursor = char["x0"]
        for letter, width in zip(char["text"], widths):
            right = cursor + (char["x1"] - char["x0"]) * width / total
            result.append({**char, "text": letter, "x0": cursor, "x1": right})
            cursor = right
    return result


def draw_run(writer, chars):
    if not chars:
        return
    first = chars[0]
    face = "SampleBold" if "Bold" in first["fontname"] else "SampleRegular"
    text = "".join(c["text"] for c in chars)
    width = pdfmetrics.stringWidth(text, face, first["size"])
    obj = writer.beginText(first["x0"], first["matrix"][5])
    obj.setFont(face, first["size"])
    if width:
        obj.setHorizScale(100 * (chars[-1]["x1"] - first["x0"]) / width)
    obj.textOut(text)
    writer.setFillColorRGB(0, 0, 0)
    writer.drawText(obj)


def prepare(source, target, font_dir):
    if source.resolve() == target.resolve():
        raise ValueError("La salida debe ser distinta del original")
    before = digest(source)
    pdfmetrics.registerFont(TTFont("SampleRegular", str(font_dir / "calibri.ttf")))
    pdfmetrics.registerFont(TTFont("SampleBold", str(font_dir / "calibrib.ttf")))
    with pdfplumber.open(source) as pdf:
        if len(pdf.pages) != 13:
            raise ValueError("Este preparador requiere el ejemplo revisado de 13 páginas")
        if any(page.images for page in pdf.pages):
            raise ValueError("El ejemplo cambió: revisar imágenes antes de anonimizar")
        all_chars = [expanded_chars(page) for page in pdf.pages]
        texts = ["".join(c["text"] for c in chars) for chars in all_chars]
        ranges = defaultdict(list)

        def hide(page, pattern, label, count=1):
            found = list(re.finditer(pattern, texts[page - 1], re.I | re.S))
            if len(found) != count:
                raise ValueError(f"Zona de página {page}: se esperaban {count}, hay {len(found)}")
            for match in found:
                start, end = match.span("private")
                ranges[page].append((start, end, label))

        hide(1, r"Entre la Sra\.\s*(?P<private>.*?)en adelante llamados", "[DATOS LOCADOR OMITIDOS]", 1)
        hide(1, r"y la Sra\.\s*(?P<private>.*?),?\s*y en adelante llamada", "[DATOS LOCATARIO OMITIDOS]", 1)
        hide(1, r"inmueble sito en calle\s*(?P<private>.*?);\s*de ahora en adelante", "[UBICACION OMITIDA]", 1)
        hide(2, r"(?P<private>\d{2}/\d{2}/\d{4})", "[FECHA]", 2)
        hide(2, r"precio mensual de\s*(?P<private>.*?),\s*pagadero", "[IMPORTE OMITIDO]", 1)
        hide(3, r"oficinas comerciales de\s*(?P<private>.*?);\s*o en el domicilio", "[ADMINISTRACION Y DOMICILIO]", 1)
        hide(5, r"por la administraci[oó]n\s*(?P<private>.*?)\s*a efectos", "[ADMINISTRACION]", 1)
        hide(8, r"DECIMO QUINTA:\s*Garant[ií]as\.\s*(?P<private>.*)$", "[IDENTIFICACION DE FIADORES OMITIDA]", 1)
        hide(9, r"^(?P<private>.*?)quienes manifiestan", "[CONTINUACION: DATOS DE FIADORES OMITIDOS]", 1)
        hide(11, r"(?P<private>1\.\s*El LOCADOR fija.*)$", "[DOMICILIOS Y CONTACTOS OMITIDOS]", 1)
        hide(12, r"^(?P<private>.*?)En todos los casos,", "[CONTINUACION: CONTACTOS OMITIDOS]", 1)
        hide(12, r"Tribunales Ordinarios de la ciudad de\s*(?P<private>.*?)\.\s*VIG", "[JURISDICCION OMITIDA]", 1)
        hide(12, r"de la firma\s*(?P<private>.*?)\s*en la negociaci[oó]n", "[ADMINISTRACION]", 1)
        hide(12, r"suma de\s*(?P<private>PESOS.*?)\s*m[aá]s IVA", "[IMPORTE OMITIDO]", 1)
        hide(12, r"a la firma\s*(?P<private>.*?),?\s*como administradora", "[ADMINISTRACION Y DOMICILIO]", 1)
        hide(13, r"en la ciudad de\s*(?P<private>.*?)(?:\.\s*)$", "[LUGAR Y FECHA OMITIDOS]", 1)

        # Construir desde cero evita copiar metadatos, anotaciones, adjuntos,
        # texto oculto, revisiones incrementales u objetos del PDF original.
        target.parent.mkdir(parents=True, exist_ok=True)
        writer = canvas.Canvas(str(target), invariant=1, pageCompression=1)
        writer.setTitle("HU30 - Contrato de ejemplo anonimizado 01")
        writer.setAuthor("AARI - Material de prueba")
        writer.setSubject("Copia anonimizada; no es un contrato para uso ni una evaluación jurídica")
        kept_by_page = []
        removed_by_page = []
        char_counts = []
        for number, page in enumerate(pdf.pages, start=1):
            page_chars = all_chars[number - 1]
            writer.setPageSize((page.width, page.height))
            omitted = set()
            for start, end, _ in ranges[number]:
                if omitted.intersection(range(start, end)):
                    raise ValueError("Zonas superpuestas")
                omitted.update(range(start, end))
            kept, removed = [], []
            run = []
            for index, char in enumerate(page_chars):
                if index in omitted:
                    draw_run(writer, run)
                    run = []
                    removed.append(char["text"])
                    continue
                kept.append(char["text"])
                if run and (abs(run[-1]["matrix"][5] - char["matrix"][5]) > 0.1
                            or run[-1]["fontname"] != char["fontname"]
                            or run[-1]["size"] != char["size"]):
                    draw_run(writer, run)
                    run = []
                run.append(char)
            draw_run(writer, run)
            # Mantener las líneas de subrayado originales, sin copiar sus objetos.
            for line in page.lines:
                writer.setStrokeColorRGB(0, 0, 0)
                writer.setLineWidth(max(0.3, line.get("linewidth", 0.5)))
                writer.line(line["x0"], line["y0"], line["x1"], line["y1"])
            for start, end, label in ranges[number]:
                rows = defaultdict(list)
                for char in page_chars[start:end]:
                    rows[round(char["top"], 1)].append(char)
                ordered_rows = sorted(rows.items())
                row_widths = [max(c["x1"] for c in chars) - min(c["x0"] for c in chars) for _, chars in ordered_rows]
                desired_width = pdfmetrics.stringWidth(label, "SampleRegular", 8)
                label_row = next((i for i, width in enumerate(row_widths) if width >= desired_width), max(range(len(row_widths)), key=row_widths.__getitem__))
                for row_index, (_, chars) in enumerate(ordered_rows):
                    x0, x1 = min(c["x0"] for c in chars), max(c["x1"] for c in chars)
                    top, bottom = min(c["top"] for c in chars), max(c["bottom"] for c in chars)
                    writer.setFillColorRGB(0.94, 0.94, 0.94)
                    writer.rect(x0, page.height - bottom - 1, max(x1 - x0, 1), bottom - top + 2, stroke=0, fill=1)
                    if row_index == label_row:
                        size = min(9, (x1 - x0) / max(pdfmetrics.stringWidth(label, "SampleRegular", 1), 1))
                        writer.setFont("SampleRegular", size)
                        writer.setFillColorRGB(0.25, 0.25, 0.25)
                        writer.drawString(x0, chars[0]["matrix"][5], label)
            writer.setFillColorRGB(0.4, 0.4, 0.4)
            writer.setFont("SampleRegular", 8)
            writer.drawCentredString(page.width / 2, 25, f"HU30 - COPIA ANONIMIZADA DE PRUEBA - {number}/13")
            writer.showPage()
            kept_by_page.append("".join(kept))
            removed_by_page.append("".join(removed))
            char_counts.append({"page": number, "kept": len(kept), "removed": len(removed), "zones": len(ranges[number])})
        writer.save()

    generated = PdfReader(target)
    assert len(generated.pages) == 13
    assert not generated.get_fields()
    assert not generated.attachments
    assert not generated.trailer["/Root"].get("/OpenAction")
    assert not generated.trailer["/Root"].get("/AcroForm")
    output_texts = [pg.extract_text() or "" for pg in generated.pages]
    assert "CONTRATO DE LOCACION" in output_texts[0]
    assert "por motivos culposos" in " ".join(output_texts[5].split()) or "motivos culposos" in output_texts[5]
    for page in generated.pages:
        assert not page.get("/Annots")
    # Contrastar todos los caracteres conservados en orden de dibujo. Las etiquetas
    # y el pie se dibujan después del texto; no pueden ocultar pérdidas de cláusulas.
    with pdfplumber.open(target) as check:
        for number, page in enumerate(check.pages):
            chars = "".join(c["text"] for c in page.chars)
            if not chars.startswith(kept_by_page[number]):
                raise AssertionError(f"Texto conservado diferente en página {number + 1}")
    all_output = normalized("\n".join(output_texts))
    all_removed = " ".join(removed_by_page)
    # Los DNI, mails y números de contacto presentes en las zonas suprimidas no
    # deben aparecer en la salida. Los datos se mantienen exclusivamente en RAM.
    identifiers = re.findall(r"\b\d{2}\.\d{3}\.\d{3}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d{10}\b", all_removed)
    if any(normalized(value) in all_output for value in identifiers):
        raise AssertionError("Se detectó un identificador residual")
    # Control adicional: secuencias de tres palabras del texto retirado que no
    # sean lenguaje compartido con el cuerpo contractual conservado.
    retained_original = normalized(" ".join(kept_by_page))
    words = re.findall(r"[\w@.+-]+", all_removed)
    unique_sequences = {normalized(" ".join(words[i:i + 3])) for i in range(len(words) - 2)}
    unique_sequences = {s for s in unique_sequences if len(s) > 9 and s not in retained_original}
    if any(s in all_output for s in unique_sequences):
        raise AssertionError("Se detectó una secuencia retirada en el texto de salida")
    assert before == digest(source), "El original cambió"
    report = {
        "example": "hu30-ejemplo-01", "pages": 13,
        "source_unchanged": True, "output_sha256": digest(target),
        "preserved_characters_match": True, "redaction_zones": sum(len(v) for v in ranges.values()),
        "identifiers_checked": len(identifiers), "residual_identifier_matches": 0,
        "removed_unique_sequences_checked": len(unique_sequences),
        "attachments": 0, "annotations": 0, "form_fields": 0,
        "original_objects_copied": False,
        "external_api_calls_during_preparation": 0,
        "visual_review": "pending", "page_checks": char_counts,
        "limitations": "Documento concreto; no garantiza anonimización de otros PDF. Requiere inspección visual."
    }
    report_path = target.with_suffix(".verificacion.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(target), "report": str(report_path), "checks": "passed", "pages": 13}, ensure_ascii=True))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("target", type=Path)
    cli.add_argument("--font-dir", type=Path, required=True)
    args = cli.parse_args()
    prepare(args.source, args.target, args.font_dir)
