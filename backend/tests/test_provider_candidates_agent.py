"""Grafo y llamador productivo HU15, sin cuota ni servicios externos."""

from threading import Event
from uuid import uuid4

import pytest

from app.agents.provider_candidates import build_provider_candidates_graph, build_specialty_prompt
from app.services.provider_candidates_worker import ProviderCandidatesWorker

SPECIALTY = uuid4()
DESCRIPTION = "Pierde agua la cañería debajo de la pileta."
CATALOG = [{"id": SPECIALTY, "nombre": "Plomería"}]


class Resolver:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result or {"especialidad_id": str(SPECIALTY), "fundamento": "Problema de cañería.", "evidencia": "la cañería"}
        self.error = error

    def invoke(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.result


def run(resolver=None, specialty=None, catalog=CATALOG, external=False):
    saves = []
    graph = build_provider_candidates_graph(lambda state: saves.append(dict(state)) or "persisted",
                                            resolver=resolver, external_enabled=external)
    result = graph.invoke({"descripcion": DESCRIPTION, "tipo_id": specialty, "catalogo": catalog})
    assert len(saves) == 1 and result["busqueda"] == "persisted"
    return saves[0]


def test_registered_specialty_reuses_catalog_without_model_call():
    resolver = Resolver()
    result = run(resolver, SPECIALTY)
    assert result["especialidad_id"] == SPECIALTY and result["fuente"] == "registrada"
    assert resolver.calls == [] and result["modelo"] is None


def test_missing_specialty_is_resolved_once_from_description_and_catalog():
    resolver = Resolver()
    result = run(resolver)
    assert result["especialidad_id"] == SPECIALTY and result["fuente"] == "modelo"
    assert result["prompt_version"] == "especialidad_proveedores_v1"
    assert len(resolver.calls) == 1
    assert DESCRIPTION in resolver.calls[0] and str(SPECIALTY) in resolver.calls[0]
    assert "No clasifiques quién paga" in resolver.calls[0]


@pytest.mark.parametrize("response", [
    {"especialidad_id": str(uuid4()), "fundamento": "No existe.", "evidencia": "cañería"},
    {"especialidad_id": str(SPECIALTY), "fundamento": "Inventado.", "evidencia": "cortocircuito"},
    {"especialidad_id": str(SPECIALTY), "fundamento": "Vacío.", "evidencia": ""},
    {"especialidad_id": "plomeria", "fundamento": "Incorrecto.", "evidencia": "cañería"},
    {"especialidad_id": [str(SPECIALTY)], "fundamento": "Dos rubros.", "evidencia": "cañería"},
    {"especialidad_id": str(SPECIALTY), "fundamento": "Otro campo.", "evidencia": "cañería", "autorizado": True},
    "no es json", {},
])
def test_invalid_response_never_invents_a_specialty_or_retries(response):
    resolver = Resolver()
    resolver.result = response
    result = run(resolver)
    assert result["especialidad_id"] is None and result["fuente"] == "revision"
    assert len(resolver.calls) == 1


def test_ambiguous_or_multiple_specialties_request_review():
    result = run(Resolver({"especialidad_id": None, "fundamento": "Falta información.", "evidencia": ""}))
    assert result["especialidad_id"] is None and "única especialidad" in result["motivo"]


@pytest.mark.parametrize("error", [TimeoutError("secret prompt"), RuntimeError("503 secret key"), ValueError("malformed")])
def test_model_failure_is_safe_and_does_not_repeat_call(error):
    resolver = Resolver(error=error)
    result = run(resolver)
    assert result["especialidad_id"] is None and "secret" not in result["motivo"]
    assert len(resolver.calls) == 1


def test_empty_catalog_and_disabled_external_calls_never_construct_model(monkeypatch):
    monkeypatch.setattr("app.agents.provider_candidates.get_specialty_resolver", lambda: pytest.fail("No autorizado."))
    assert run(catalog=[])["especialidad_id"] is None
    assert "no está habilitada" in run()["motivo"]


def test_prompt_carries_only_description_and_catalog():
    prompt = build_specialty_prompt(DESCRIPTION, CATALOG)
    assert '"descripcion"' in prompt and '"catalogo"' in prompt
    for name in ('"contrato"', '"telefono"', '"email"', '"direccion"', '"inquilino"'):
        assert name not in prompt


class Jobs:
    def __init__(self, specialty=None):
        self.job = {"descripcion": DESCRIPTION, "tipo_id": specialty, "catalogo": CATALOG}
        self.saved = []
        self.discovered = 0
        self.valid = True

    def discover(self):
        self.discovered += 1

    def reserve_one(self):
        job, self.job = self.job, None
        return job

    def renew(self, job):
        return self.valid

    def finish(self, job, state):
        self.saved.append(dict(state))
        return "saved"


@pytest.mark.parametrize("specialty", [None, SPECIALTY])
def test_real_worker_calls_graph_and_search_without_operator_or_authorization(specialty):
    repo, resolver = Jobs(specialty), Resolver()
    worker = ProviderCandidatesWorker(repo, resolver=resolver)
    assert worker.process_one() is True
    assert repo.saved[0]["especialidad_id"] == SPECIALTY
    assert len(resolver.calls) == (0 if specialty else 1)
    assert worker.process_one() is False and len(repo.saved) == 1


def test_worker_checks_lease_before_calling_model():
    repo, resolver = Jobs(), Resolver()
    repo.valid = False
    assert ProviderCandidatesWorker(repo, resolver=resolver).process_one() is False
    assert resolver.calls == [] and repo.saved == []


def test_lost_heartbeat_discards_response():
    repo = Jobs()
    lost = Event()
    count = 0
    def renew(job):
        nonlocal count
        count += 1
        if count > 1:
            lost.set()
            return False
        return True
    repo.renew = renew
    class SlowResolver(Resolver):
        def invoke(self, prompt):
            assert lost.wait(timeout=2)
            return super().invoke(prompt)
    resolver = SlowResolver()
    ProviderCandidatesWorker(repo, resolver=resolver, heartbeat_seconds=0.01).process_one()
    assert len(resolver.calls) == 1 and repo.saved == []


def test_lifespan_worker_is_opt_in_and_disabled_in_tests(monkeypatch):
    from app.main import _provider_worker_enabled
    monkeypatch.delenv("PROVIDER_CANDIDATES_WORKER_ENABLED", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert not _provider_worker_enabled()
    monkeypatch.setenv("PROVIDER_CANDIDATES_WORKER_ENABLED", "true")
    assert _provider_worker_enabled()
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")
    assert not _provider_worker_enabled()
