"""Delimita cláusulas locales y exige que cada cita pertenezca a la suya."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from app.schemas.clausulas_contrato import (
    ClauseEvidence,
    ExtractedClause,
    ExtractedClauseBatch,
    RejectedClause,
)
from app.services.contract_clause_evidence import anchor_evidence


VALIDATOR_VERSION = "hu30-v4-tramos-v2"

_ORDINALS = {
    "PRIMERA": 1, "PRIMERO": 1, "SEGUNDA": 2, "SEGUNDO": 2,
    "TERCERA": 3, "TERCERO": 3, "CUARTA": 4, "CUARTO": 4,
    "QUINTA": 5, "QUINTO": 5, "SEXTA": 6, "SEXTO": 6,
    "SEPTIMA": 7, "SEPTIMO": 7, "OCTAVA": 8, "OCTAVO": 8,
    "NOVENA": 9, "NOVENO": 9, "DECIMA": 10, "DECIMO": 10,
    "UNDECIMA": 11, "UNDECIMO": 11,
    "DUODECIMA": 12, "DUODECIMO": 12,
}
for _index, _root in enumerate(
    ("PRIMER", "SEGUND", "TERCER", "CUART", "QUINT", "SEXT", "SEPTIM", "OCTAV", "NOVEN"),
    start=1,
):
    for _prefix in ("DECIMO", "DECIMA"):
        for _ending in ("A", "O"):
            _ORDINALS[f"{_prefix} {_root}{_ending}"] = 10 + _index
_ORDINAL_PATTERN = (
    r"D[ÉE]CIM[OA][ \t]+(?:PRIMER[AO]|SEGUND[AO]|TERCER[AO]|CUART[AO]|"
    r"QUINT[AO]|SEXT[AO]|S[ÉE]PTIM[AO]|OCTAV[AO]|NOVEN[AO])|"
    r"PRIMER[AO]|SEGUND[AO]|TERCER[AO]|CUART[AO]|QUINT[AO]|SEXT[AO]|"
    r"S[ÉE]PTIM[AO]|OCTAV[AO]|NOVEN[AO]|D[ÉE]CIM[AO]|"
    r"UND[ÉE]CIM[AO]|DUOD[ÉE]CIM[AO]"
)
_LABEL_PATTERN = rf"(?:{_ORDINAL_PATTERN}|\d{{1,3}}(?:\.\d{{1,2}}){{0,2}}|[IVXLCDM]{{1,8}})"
_PREFIX = r"(?:CL[ÁA]USULA|ART[ÍI]CULO|ART\.)"
_HEADING = re.compile(
    rf"(?m)^[ \t]*(?:(?P<prefix>{_PREFIX})[ \t]+)?"
    rf"(?P<label>{_LABEL_PATTERN})[ \t]*[º°]?[ \t]*"
    r"(?::|\.(?:[ \t]*[-–—])?|\)|[-–—])",
    re.IGNORECASE,
)
_UNKNOWN_HEADING = re.compile(
    rf"(?m)^[ \t]*{_PREFIX}[ \t]+[^\n]{{1,60}}?(?::|\.[ \t]*[-–—]?|[ \t]+[-–—])",
    re.IGNORECASE,
)
_DECLARED_LABEL = re.compile(
    rf"^(?:(?P<prefix>{_PREFIX})[ \t]+)?(?P<label>{_LABEL_PATTERN})"
    r"(?=$|[ \t\(\):.\-–—])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClauseFragment:
    page: int
    text: str


@dataclass(frozen=True)
class ClauseSegment:
    label: str | None
    kind: str | None
    fragments: tuple[ClauseFragment, ...]

    @property
    def pages(self) -> list[int]:
        return list(dict.fromkeys(fragment.page for fragment in self.fragments))


def _fold(text: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFD", text.upper())
        if not unicodedata.combining(character)
    )


def _roman_number(value: str) -> int | None:
    numerals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for character in reversed(value):
        current = numerals[character]
        total += -current if current < previous else current
        previous = current
    # Rechazamos combinaciones no canónicas que aparenten un número de cláusula.
    units = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    remaining = total
    canonical = ""
    for amount, symbol in units:
        canonical += symbol * (remaining // amount)
        remaining %= amount
    return total if 1 <= total <= 30 and canonical == value else None


def normalize_clause_label(value: str | None) -> str | None:
    """Normaliza la referencia principal; ignora 'Parte 1' o incisos del modelo."""

    if not value:
        return None
    match = _DECLARED_LABEL.match(value.strip())
    if not match:
        return None
    token = _fold(match.group("label"))
    if token in _ORDINALS:
        return str(_ORDINALS[token])
    if token[0].isdigit():
        return ".".join(str(int(part)) for part in token.split("."))
    roman = _roman_number(token)
    return str(roman) if roman is not None else None


def _clause_kind(prefix: str | None, label: str) -> str | None:
    if prefix:
        return "articulo" if _fold(prefix).startswith("ART") else "clausula"
    token = _fold(label)
    if token in _ORDINALS:
        return "clausula" if token.endswith("A") else "articulo"
    return None


def build_clause_segments(pages: dict[int, str]) -> list[ClauseSegment]:
    """Une continuaciones hasta el siguiente encabezado reconocible.

    Una página vacía o faltante interrumpe el tramo: no suponemos que el texto
    posterior continúa una cláusula que no pudimos leer íntegramente.
    """

    segments: list[ClauseSegment] = []
    label: str | None = None
    kind: str | None = None
    fragments: list[ClauseFragment] = []
    previous_page: int | None = None

    def finish() -> None:
        nonlocal label, kind, fragments
        if fragments:
            segments.append(ClauseSegment(label, kind, tuple(fragments)))
        label = None
        kind = None
        fragments = []

    for page, text in sorted(pages.items()):
        if previous_page is not None and page != previous_page + 1:
            finish()
        previous_page = page
        if not text or not text.strip():
            finish()
            continue

        recognized = {}
        for match in _HEADING.finditer(text):
            normalized = normalize_clause_label(match.group("label"))
            # Un número romano inválido sin prefijo puede ser ruido del OCR.
            if normalized is None and match.group("prefix") is None:
                continue
            recognized[match.start()] = (
                match,
                normalized,
                _clause_kind(match.group("prefix"), match.group("label")),
            )
        headings = list(recognized.values())
        headings.extend(
            (match, None, None) for match in _UNKNOWN_HEADING.finditer(text)
            if match.start() not in recognized
        )
        headings.sort(key=lambda item: item[0].start())
        if not headings:
            if fragments:
                fragments.append(ClauseFragment(page, text))
            continue

        prefix = text[:headings[0][0].start()]
        if fragments and prefix.strip():
            fragments.append(ClauseFragment(page, prefix))
        for index, (heading, normalized, heading_kind) in enumerate(headings):
            finish()
            label = normalized
            kind = heading_kind
            end = headings[index + 1][0].start() if index + 1 < len(headings) else len(text)
            fragments.append(ClauseFragment(page, text[heading.start():end]))
    finish()
    return segments


def _cited_in_segment(evidence: ClauseEvidence, segment: ClauseSegment) -> bool:
    return any(
        fragment.page == evidence.pagina
        and anchor_evidence(evidence, fragment.text)[0] is not None
        for fragment in segment.fragments
    )


def validate_clause_segments(
    batch: ExtractedClauseBatch,
    pages: dict[int, str],
) -> tuple[list[ExtractedClause], list[RejectedClause], list[str]]:
    """Valida texto, página y pertenencia a una misma cláusula detectada."""

    segments = build_clause_segments(pages)
    valid: list[ExtractedClause] = []
    rejected: list[RejectedClause] = []
    incidents: list[str] = []
    for ordinal, clause in enumerate(batch.clausulas, start=1):
        anchored: list[ClauseEvidence] = []
        invalid: list[ClauseEvidence] = []
        reasons: list[str] = []
        for evidence in clause.evidencias:
            located, reason = anchor_evidence(evidence, pages.get(evidence.pagina, ""))
            if located is None:
                invalid.append(evidence)
                reasons.append(reason or "la cita no se pudo anclar")
            else:
                anchored.append(located)

        declared = normalize_clause_label(clause.numero)
        declared_match = _DECLARED_LABEL.match(clause.numero.strip()) if clause.numero else None
        declared_kind = (
            _clause_kind(declared_match.group("prefix"), declared_match.group("label"))
            if declared_match else None
        )
        if clause.numero and declared is None:
            reasons.append("el número de cláusula no se reconoce")
        elif not segments:
            reasons.append("no se pudieron delimitar cláusulas en el documento")
        elif anchored and not invalid:
            candidates = [
                segment for segment in segments
                if segment.label is not None
                and (declared is None or segment.label == declared)
                and (declared_kind is None or segment.kind == declared_kind)
                and all(_cited_in_segment(item, segment) for item in anchored)
            ]
            if len(candidates) != 1:
                invalid.extend(clause.evidencias)
                reasons.append("las citas no pertenecen a una única cláusula identificada")

        if reasons:
            reason = "; ".join(dict.fromkeys(reasons)) + "."
            rejected.append(RejectedClause(
                ordinal=ordinal,
                propuesta=clause,
                motivo=reason,
                evidencias_invalidas=invalid,
            ))
            incidents.append(f"La propuesta {ordinal} requiere revisión de evidencia: {reason}")
            continue

        payload = clause.model_dump(mode="python")
        payload["evidencias"] = [item.model_dump(mode="python") for item in anchored]
        valid.append(ExtractedClause.model_validate(payload))
    return valid, rejected, incidents
