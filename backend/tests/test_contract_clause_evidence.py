"""HU30 v3: anclaje conservador al texto exacto del documento."""

from app.schemas.clausulas_contrato import ClauseEvidence, ExtractedClauseBatch
from app.services.contract_clause_evidence import (
    anchor_evidence,
    validate_and_anchor_evidence,
)


def batch_with(*evidences):
    return ExtractedClauseBatch.model_validate({"clausulas": [{
        "numero": "SEXTA",
        "titulo": "Reparaciones",
        "evidencias": list(evidences),
        "resumen": "La reparación conserva sus condiciones.",
        "categoria": "reparacion",
        "responsable": "condicional",
        "uso_clasificador": "operativa",
        "condiciones": "Según la causa indicada.",
        "referencias": [],
        "confianza": 0.9,
    }]})


def test_anchors_spacing_line_breaks_and_punctuation_to_exact_source_text():
    page = (
        "Serán a cargo del locador las reparaciones, sin derecho a reembolso "
        "a lguno a su favor."
    )
    evidence = ClauseEvidence(
        pagina=5,
        texto="Serán a cargo del locador las reparaciones sin derecho a reembolso alguno a su favor",
    )

    anchored, reason = anchor_evidence(evidence, page)

    assert reason is None
    assert anchored.texto == (
        "Serán a cargo del locador las reparaciones, sin derecho a reembolso "
        "a lguno a su favor"
    )


def test_rejects_changed_words_instead_of_accepting_a_paraphrase():
    evidence = ClauseEvidence(
        pagina=2,
        texto="El propietario debe reparar el inmueble cuando exista una rotura",
    )
    anchored, reason = anchor_evidence(
        evidence,
        "El propietario debe conservar el inmueble cuando exista una rotura.",
    )

    assert anchored is None
    assert "cambia caracteres" in reason


def test_rejects_a_non_unique_or_too_short_fragment():
    repeated = ClauseEvidence(
        pagina=1,
        texto="El locatario debe conservar el inmueble",
    )
    anchored, reason = anchor_evidence(
        repeated,
        "El locatario debe conservar el inmueble. El locatario debe conservar el inmueble.",
    )
    assert anchored is None and "más de una vez" in reason

    short, reason = anchor_evidence(ClauseEvidence(pagina=1, texto="El locatario"), "El locatario paga.")
    assert short is None and "demasiado breve" in reason


def test_anchors_each_page_and_stores_only_original_pdf_fragments():
    batch = batch_with(
        {"pagina": 5, "texto": "El locatario reparará los desperfectos"},
        {"pagina": 6, "texto": "cuando la causa le resulte imputable"},
    )
    valid, rejected, incidents = validate_and_anchor_evidence(batch, {
        5: "El locatario reparará los desper-\nfectos",
        6: "cuando la causa le resulte imputable.",
    })

    assert not rejected and not incidents
    assert valid[0].paginas == [5, 6]
    assert valid[0].evidencias[0].texto == "El locatario reparará los desper-\nfectos"
    assert valid[0].evidencias[1].texto == "cuando la causa le resulte imputable"
