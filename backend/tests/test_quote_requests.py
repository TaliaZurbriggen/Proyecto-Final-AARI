"""Reglas/worker HU19 sin red, base compartida ni mensajes reales."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.main import _quote_requests_worker_enabled
from app.schemas.quote_requests import QuoteReservation
from app.schemas.whatsapp import WhatsAppSendReceipt
from app.services.quote_requests import QuoteRequestsWorker, quote_message, request_content
from app.services.whatsapp_sender import WhatsAppSendError
from tests.whatsapp_helpers import SETTINGS


def content_row(**changes):
    return {"descripcion": "Pierde agua la cañería debajo de la pileta.", "direccion": "Calle Ficticia 100",
        "localidad": "Localidad sintética", "provincia": "Córdoba", "barrio": "Centro", "piso": 0, "unidad": "B",
        "tipo_id": uuid4(), "propiedad_id": uuid4(), "inquilino_id": uuid4(), "propietario_id": uuid4(),
        "usuario_id": uuid4(), "tipo_gasto": "ordinario", **changes}


def test_template_has_reference_location_description_and_24h_not_a_hiring():
    data, _ = request_content(content_row())
    reference = uuid4()
    parameters, message = quote_message(reference, data)
    assert len(parameters) == 4 and parameters[0] == str(reference)
    assert "Calle Ficticia 100" in message and "Córdoba" in message and "Piso 0" in message and "Unidad B" in message
    assert "24 horas" in message and "no confirma una contratación ni una visita" in message
    assert "importe, moneda y descripción" in message


@pytest.mark.parametrize("key", ["descripcion", "direccion", "localidad", "provincia", "barrio", "piso", "unidad", "tipo_id", "usuario_id"])
def test_fingerprint_detects_changed_disclosed_data_or_authorization(key):
    row = content_row()
    changed = {**row, key: 2 if key == "piso" else "changed"}
    assert request_content(row)[1] != request_content(changed)[1]


def test_fingerprint_does_not_track_unrelated_update_timestamp():
    row = content_row()
    assert request_content(row) == request_content({**row, "updated_at": "irrelevant"})


@pytest.mark.parametrize("value", ["", "x" * 4097, "\x00", "\ud800"])
def test_invalid_template_parameters_never_reach_sender(value):
    data, _ = request_content(content_row())
    with pytest.raises(ValueError):
        quote_message(uuid4(), {**data, "descripcion": value})


class Repo:
    def __init__(self, *, allow=True):
        self.trace, self.allow, self.results = [], allow, []
        self.job = QuoteReservation(uuid4(), uuid4(), uuid4(), "15555550100", ("reference", "problem", "address", "24 horas"))
    def discover(self, **_kwargs):
        self.trace.append("discover")
        return 1
    def recover_expired(self, **_kwargs):
        self.trace.append("recover")
    def reserve_one(self, **kwargs):
        self.trace.append("reserve")
        assert kwargs["recipients"] == ("15555550100",)
        return self.job
    def begin_send(self, job, **_kwargs):
        self.trace.append("begin")
        assert job is self.job
        return self.allow
    def finish(self, job, **kwargs):
        self.trace.append("finish")
        self.results.append(kwargs)


def worker(*, settings=SETTINGS, failure=None, allow=True, template="synthetic_quote"):
    repo = Repo(allow=allow)
    def send(**_kwargs):
        repo.trace.append("HTTP")
        if failure:
            raise failure
        return WhatsAppSendReceipt("wamid.synthetic.quote")
    service = QuoteRequestsWorker(repo, SimpleNamespace(send_template=send), settings=settings, template_name=template)
    return repo, service


def test_send_is_after_durable_begin_and_receipt_is_not_delivery():
    repo, service = worker()
    assert service.tick() == 2
    assert repo.trace == ["discover", "recover", "reserve", "begin", "HTTP", "finish"]
    assert repo.results == [{"outcome": "aceptada", "message_id": "wamid.synthetic.quote"}]


def test_changed_or_expired_reservation_never_calls_http():
    repo, service = worker(allow=False)
    service.tick()
    assert repo.trace == ["discover", "recover", "reserve", "begin"] and not repo.results


@pytest.mark.parametrize("changes", [{"outbound_enabled": False}, {"access_token": ""}, {"test_recipients": ()}])
def test_disabled_or_incomplete_config_does_not_reserve_or_send(changes):
    repo, service = worker(settings=replace(SETTINGS, **changes))
    service.tick()
    assert repo.trace == ["discover", "recover"]


@pytest.mark.parametrize("name", ["", "Invalid template", "../template"])
def test_missing_or_invalid_approved_template_does_not_reserve(name):
    repo, service = worker(template=name)
    service.tick()
    assert repo.trace == ["discover", "recover"]


@pytest.mark.parametrize("failure,outcome", [(WhatsAppSendError("synthetic", outcome="unknown"), "desconocida"),
    (WhatsAppSendError("synthetic", outcome="rejected"), "rechazada"), (RuntimeError("private"), "desconocida")])
def test_one_attempt_no_retry_or_private_error_persisted(failure, outcome):
    repo, service = worker(failure=failure)
    service.tick()
    assert repo.trace.count("HTTP") == 1 and repo.results == [{"outcome": outcome}]


def test_startup_flag_off_and_does_not_start_worker_during_pytest(monkeypatch):
    monkeypatch.delenv("QUOTE_REQUESTS_WORKER_ENABLED", raising=False)
    assert not _quote_requests_worker_enabled()
    monkeypatch.setenv("QUOTE_REQUESTS_WORKER_ENABLED", "true")
    assert not _quote_requests_worker_enabled()
