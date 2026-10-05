"""El verificador nuevo no confunde citas de cláusulas vecinas."""

from app.schemas.clausulas_contrato import ExtractedClauseBatch
from app.services.contract_clause_segments import (
    build_clause_segments,
    normalize_clause_label,
    validate_clause_segments,
)


PAGES = {
    1: (
        "PRIMERA: El inmueble se destina a vivienda.\n"
        "QUINTA: El LOCADOR pagará las reparaciones necesarias para mantener "
        "el edificio en buen estado de"
    ),
    2: (
        "conservación durante la vigencia del contrato.\n"
        "SEXTA: Los gastos comunes están sujetos a revisión.\n"
        "SÉPTIMA: El LOCATARIO devolverá el inmueble en buen estado.\n"
        "OCTAVA: No se conservarán elementos que afecten la seguridad."
    ),
}


def proposal(number, evidences):
    return ExtractedClauseBatch.model_validate({"clausulas": [{
        "numero": number,
        "titulo": None,
        "evidencias": evidences,
        "resumen": "Resumen pendiente de revisión humana.",
        "categoria": "mantenimiento",
        "responsable": "no_especificado",
        "uso_clasificador": "contexto",
        "condiciones": None,
        "referencias": [],
        "confianza": 0.5,
    }]})


def test_fifth_clause_continues_on_next_page_until_sixth_heading():
    segments = build_clause_segments(PAGES)

    assert [segment.label for segment in segments] == ["1", "5", "6", "7", "8"]
    assert segments[1].pages == [1, 2]
    assert "conservación durante la vigencia" in segments[1].fragments[1].text
    assert "SEXTA:" not in segments[1].fragments[1].text

    batch = proposal("QUINTA", [
        {"pagina": 1, "texto": "El LOCADOR pagará las reparaciones necesarias"},
        {"pagina": 2, "texto": "conservación durante la vigencia del contrato"},
    ])
    valid, rejected, incidents = validate_clause_segments(batch, PAGES)

    assert len(valid) == 1 and not rejected and not incidents
    assert valid[0].paginas == [1, 2]


def test_sixth_cannot_cite_seventh_even_when_text_exists_on_same_page():
    batch = proposal("SEXTA", [{
        "pagina": 2,
        "texto": "SÉPTIMA: El LOCATARIO devolverá el inmueble en buen estado",
    }])

    valid, rejected, incidents = validate_clause_segments(batch, PAGES)

    assert valid == []
    assert rejected[0].ordinal == 1
    assert "única cláusula" in rejected[0].motivo
    assert len(rejected[0].evidencias_invalidas) == 1
    assert len(incidents) == 1


def test_wrong_page_for_a_continuation_is_rejected_without_rewriting_quote():
    batch = proposal("QUINTA", [{
        "pagina": 2,
        "texto": "El LOCADOR pagará las reparaciones necesarias",
    }])

    valid, rejected, _ = validate_clause_segments(batch, PAGES)

    assert not valid
    assert rejected[0].propuesta.evidencias[0].pagina == 2
    assert "cambia caracteres" in rejected[0].motivo


def test_cross_clause_evidence_is_rejected_even_with_same_document_page():
    batch = proposal(None, [
        {"pagina": 2, "texto": "Los gastos comunes están sujetos a revisión"},
        {"pagina": 2, "texto": "El LOCATARIO devolverá el inmueble en buen estado"},
    ])

    valid, rejected, _ = validate_clause_segments(batch, PAGES)

    assert not valid
    assert "única cláusula" in rejected[0].motivo


def test_unsegmented_or_unreadable_pages_are_not_trusted():
    batch = proposal("SEXTA", [{
        "pagina": 1, "texto": "El LOCADOR pagará las reparaciones necesarias",
    }])
    unsegmented = {1: "El LOCADOR pagará las reparaciones necesarias sin título."}
    valid, rejected, _ = validate_clause_segments(batch, unsegmented)
    assert not valid
    assert "no se pudieron delimitar" in rejected[0].motivo

    interrupted = build_clause_segments({
        1: "QUINTA: El LOCADOR pagará las reparaciones necesarias",
        2: "",
        3: "para mantener el edificio en buen estado. SEXTA: Otra regla.",
    })
    assert interrupted[0].pages == [1]


def test_labels_cover_ordinals_arabic_roman_and_parts_without_confusing_words():
    assert normalize_clause_label("Cláusula SÉPTIMA (Parte 1)") == "7"
    assert normalize_clause_label("Artículo IX - reparaciones") == "9"
    assert normalize_clause_label("5.1. Inciso d") == "5.1"
    assert normalize_clause_label("DÉCIMO PRIMERA: llaves") == "11"
    assert normalize_clause_label("ARTICULO DECIMO SEXTO - jurisdicción") == "16"
    assert normalize_clause_label("SÉPTIMAMENTE") is None
    assert normalize_clause_label("IL") is None


def test_repeated_heading_must_match_one_occurrence_not_combined_evidence():
    pages = {
        1: "PRIMERA: La reparación de techos corresponde al locador.",
        2: "PRIMERA: La inspección corresponde al administrador.",
    }
    batch = proposal("PRIMERA", [
        {"pagina": 1, "texto": "La reparación de techos corresponde al locador"},
        {"pagina": 2, "texto": "La inspección corresponde al administrador"},
    ])

    valid, rejected, _ = validate_clause_segments(batch, pages)

    assert not valid
    assert "única cláusula" in rejected[0].motivo


def test_compound_ordinals_close_the_previous_clause():
    pages = {1: (
        "DÉCIMA: El locatario debe mantener el inmueble en buen estado.\n"
        "DÉCIMO PRIMERA: Al finalizar deberá devolver las llaves.\n"
        "DÉCIMO SEGUNDA: El depósito responde sólo por daños atribuibles."
    )}

    assert [segment.label for segment in build_clause_segments(pages)] == ["10", "11", "12"]


def test_unreadable_ocr_heading_stops_previous_segment_without_guessing_number():
    pages = {1: (
        "ARTICULO QUINTO - ENTREGA: El locador entregará el inmueble apto.\n"
        "ARTICULO XTO — OBLIGACIONES: El locador reparará daños estructurales.\n"
        "ARTICULO SEPTIMO - USO: El locatario lo conservará."
    )}
    segments = build_clause_segments(pages)

    assert [segment.label for segment in segments] == ["5", None, "7"]
    invalid = proposal("QUINTO", [{
        "pagina": 1,
        "texto": "El locador reparará daños estructurales",
    }])
    valid, rejected, _ = validate_clause_segments(invalid, pages)
    assert not valid and "única cláusula" in rejected[0].motivo


def test_damaged_ocr_heading_ending_in_period_stops_previous_segment():
    pages = {1: (
        "ARTÍCULO DÉCIMO PRIMERO- CESIÓN: El locatario necesita permiso.\n"
        "ARTÍCULO DÉCIMO SE 'ÓN. La rescisión requiere aviso.\n"
        "ARTÍCULO DÉCIMO TERCERO- NORMAS: Se aplica la normativa vigente."
    )}
    segments = build_clause_segments(pages)

    assert [segment.label for segment in segments] == ["11", None, "13"]
    invalid = proposal("DÉCIMO PRIMERO", [{
        "pagina": 1,
        "texto": "La rescisión requiere aviso",
    }])
    valid, rejected, _ = validate_clause_segments(invalid, pages)
    assert not valid and "única cláusula" in rejected[0].motivo


def test_unprefixed_invalid_roman_ocr_noise_does_not_split_clause():
    pages = {1: (
        "ARTÍCULO TERCERO - CANON: El canon se actualiza anualmente.\n"
        "CI ). Dicho canon será actualizado según el acuerdo.\n"
        "ARTÍCULO CUARTO - PAGO: El pago se realiza cada mes."
    )}
    segments = build_clause_segments(pages)

    assert [segment.label for segment in segments] == ["3", "4"]
    assert "Dicho canon será actualizado" in segments[0].fragments[0].text


def test_article_in_preface_cannot_masquerade_as_contract_clause():
    pages = {
        1: "Artículo 1º.- La ley define el régimen general de vivienda.",
        2: "PRIMERA: La locación comienza el primer día del mes.",
    }
    segments = build_clause_segments(pages)
    assert [(item.label, item.kind) for item in segments] == [
        ("1", "articulo"), ("1", "clausula"),
    ]

    wrong = proposal("PRIMERA", [{
        "pagina": 1,
        "texto": "La ley define el régimen general de vivienda",
    }])
    valid, rejected, _ = validate_clause_segments(wrong, pages)
    assert not valid and "única cláusula" in rejected[0].motivo

    right = proposal("PRIMERA", [{
        "pagina": 2,
        "texto": "La locación comienza el primer día del mes",
    }])
    valid, rejected, _ = validate_clause_segments(right, pages)
    assert len(valid) == 1 and not rejected
