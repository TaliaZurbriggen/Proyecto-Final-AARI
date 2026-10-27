"""Precios exactos y rechazos seguros, sin cuota de modelos ni datos reales."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.main import _quote_responses_worker_enabled
from app.services.quote_response_parser import QuoteNeedsReview, parse_quote, references
from app.services.quote_responses import QuoteResponsesWorker


@pytest.mark.parametrize("price,amount,currency", [
    ("ARS 12500", "12500.00", "ARS"), ("12.500,50 pesos", "12500.50", "ARS"),
    ("ARS $ 12500.50", "12500.50", "ARS"), ("USD 100,25", "100.25", "USD"),
    ("150 dólares", "150.00", "USD"), ("1.250.000 pesos argentinos", "1250000.00", "ARS"),
    ("ARS 9999999999,99", "9999999999.99", "ARS"),
])
def test_exact_price_and_explicit_currency(price, amount, currency):
    result = parse_quote(f"Solicitud {uuid4()}\nMonto: {price}\nTrabajo: Reparar la cañería de la cocina.")
    assert result.amount == Decimal(amount) and result.currency == currency
    assert result.description == "Reparar la cañería de la cocina"


@pytest.mark.parametrize("message", [
    "", "Gracias recibido", "Monto: $12.500. Trabajo: reparar la cocina.",
    "ARS 0 Reparar la cañería.", "ARS -12500 Reparar la cañería.",
    "-12500 pesos Reparar la cañería.", "ARS 10000000000 Reparar la cañería.",
    "ARS 12,500.50 Reparar la cañería.", "ARS 12.50,00 Reparar la cañería.",
    "ARS 12,555 Reparar la cañería.", "ARS 12.500.50 Reparar la cañería.",
    "Desde ARS 12000 para reparar la cañería.", "Aproximadamente 12000 pesos para reparar la cañería.",
    "ARS 12000 sin IVA para reparar la cañería.", "ARS 12000 + IVA para reparar la cañería.",
    "ARS 12000 no incluye repuestos para reparar la cañería.",
    "ARS 12000 o USD 10 para reparar la cañería.", "ARS 12000 más 2000 de repuestos para reparar la cañería.",
    "ARS 12000 o 13000 para reparar la cañería.", "ARS 12000 Trabajo: gas.",
    "ARS 100", "ARS 12000\x00 Reparar la cañería.",
])
def test_ambiguous_or_invalid_quotes_require_review(message):
    with pytest.raises(QuoteNeedsReview) as error:
        parse_quote(message)
    assert message not in str(error.value) if message else True


def test_references_are_explicit_unique_and_not_phone_numbers():
    ref = uuid4()
    assert references(f"Solicitud {ref} y {ref}. Teléfono 15555550100") == {ref}
    assert not references("Número 15555550100")


def test_worker_consumes_inbox_before_expiring():
    trace = []
    class Repo:
        def process_pending(self, **kwargs):
            trace.append(("inbox", kwargs))
            return 2
        def finalize_due(self, **kwargs):
            trace.append(("timeout", kwargs))
            return 1
    assert QuoteResponsesWorker(Repo()).tick() == 3
    assert trace == [("inbox", {"limit": 100}), ("timeout", {"limit": 20})]


def test_worker_never_activates_by_default_or_inside_pytest(monkeypatch):
    monkeypatch.delenv("QUOTE_RESPONSES_WORKER_ENABLED", raising=False)
    assert not _quote_responses_worker_enabled()
    monkeypatch.setenv("QUOTE_RESPONSES_WORKER_ENABLED", "true")
    assert not _quote_responses_worker_enabled()
