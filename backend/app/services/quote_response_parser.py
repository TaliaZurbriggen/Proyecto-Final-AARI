"""Lectura conservadora de cotizaciones: no usa IA ni calcula importes implícitos."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re
from uuid import UUID


REFERENCE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
CURRENCY = r"(?:ARS|USD|pesos(?: argentinos)?|d[oó]lares(?: estadounidenses)?)"
MONEY = re.compile(
    rf"(?<![\w.,-])(?:(?P<currency_before>{CURRENCY})\s*\$?\s*(?P<before>[0-9][0-9.,]*)"
    rf"|\$?\s*(?P<after>[0-9][0-9.,]*)\s*(?P<currency_after>{CURRENCY}))(?![\w.,])", re.I,
)
UNCERTAIN = re.compile(
    r"\b(?:desde|aproxim\w*|estimad\w*|entre|anticipo|se[nñ]a|cuotas?|depende|"
    r"sin\s+iva|m[aá]s\s+iva|a\s+confirmar|no\s+incluye|no\s+puedo|no\s+acepto)\b|[+%]", re.I,
)


@dataclass(frozen=True)
class ParsedQuote:
    amount: Decimal
    currency: str
    description: str = field(repr=False)


class QuoteNeedsReview(ValueError):
    """Sólo contiene un código seguro; nunca el mensaje del proveedor."""


def references(message: str) -> set[UUID]:
    return {UUID(value) for value in REFERENCE.findall(message)}


def parse_quote(message: str) -> ParsedQuote:
    if not isinstance(message, str) or not 1 <= len(message) <= 4096 or "\x00" in message:
        raise QuoteNeedsReview("texto_invalido")
    content = REFERENCE.sub("", message).strip()
    if UNCERTAIN.search(content):
        raise QuoteNeedsReview("importe_o_alcance_condicional")
    matches = list(MONEY.finditer(content))
    if len(matches) != 1:
        raise QuoteNeedsReview("importe_o_moneda_ambiguos")
    match = matches[0]
    raw = match.group("before") or match.group("after")
    # Formato argentino (12.500,50), entero o decimal sin miles (12500.50).
    if re.fullmatch(r"(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,[0-9]{1,2})?", raw):
        normalized = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[0-9]+\.[0-9]{1,2}", raw):
        normalized = raw
    else:
        raise QuoteNeedsReview("formato_importe_invalido")
    try:
        amount = Decimal(normalized)
        if not Decimal("0") < amount <= Decimal("9999999999.99"):
            raise QuoteNeedsReview("importe_fuera_de_rango")
    except InvalidOperation:
        raise QuoteNeedsReview("formato_importe_invalido") from None
    currency_text = (match.group("currency_before") or match.group("currency_after")).casefold()
    currency = "USD" if currency_text.startswith(("usd", "dólar", "dolar")) else "ARS"
    rest = content[:match.start()] + " " + content[match.end():]
    # No sumar componentes ni elegir entre varios números/precios implícitos.
    if re.search(r"[0-9$€]", rest) or re.search(CURRENCY, rest, re.I):
        raise QuoteNeedsReview("importe_o_moneda_ambiguos")
    rest = re.sub(r"\b(?:solicitud|referencia|presupuesto|monto|total|trabajo|descripci[oó]n)\b\s*:?", " ", rest, flags=re.I)
    description = re.sub(r"\s+", " ", rest).strip(" \t\n:;,.–—-")
    if len(description) < 10 or sum(char.isalpha() for char in description) < 8:
        raise QuoteNeedsReview("falta_descripcion_del_trabajo")
    return ParsedQuote(amount.quantize(Decimal("0.01")), currency, description)
