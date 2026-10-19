"""HU21: cinco recorridos multi-turno con módulos de dominio simulados."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
import pytest

from app.agents.coordination.graph import build_coordination_graph
from app.agents.coordination.state import (
    CoordinationResponse, CoordinationSnapshot, DomainContext, ResumeRequest, stage_for,
)
from app.api.coordination import get_coordination_service, require_participant
from app.main import app
from app.db.coordination import PostgresCoordinationRepository
from app.schemas.auth import AuthenticatedUser
from app.services.coordination_service import CoordinationError


def domain(state="Autorizado", expense="extraordinario", claim_id=None):
    return DomainContext(
        reclamo_id=claim_id or uuid4(), estado=state, tipo_gasto=expense,
        actor_responsable="propietario" if expense=="extraordinario" else
                          ("inmobiliaria" if expense=="expensa" else "inquilino"),
        propiedad_id=uuid4(), inquilino_id=uuid4(), propietario_id=uuid4(),
    )


@pytest.mark.parametrize("states,expense,expected", [
    (["Pendiente de respuesta del responsable","Autorizado","Pendiente de asignación",
      "Proveedor seleccionado","Visita programada"], "extraordinario", "visita_programada"),
    (["Pendiente de respuesta del responsable","Rechazado por propietario"],
     "extraordinario", "rechazado"),
    (["Pendiente de respuesta del responsable","Derivado a proveedor externo"],
     "ordinario", "derivado_externo"),
    (["Autorizado","Pendiente de asignación","Sin presupuestos recibidos"],
     "extraordinario", "intervencion_manual"),
    (["Autorizado","Pendiente de asignación","Proveedor seleccionado",
      "Pendiente de asignación","Proveedor seleccionado","Visita programada"],
     "extraordinario", "visita_programada"),
])
def test_multi_turn_domain_adapters_keep_context(states, expense, expected):
    saver = InMemorySaver()
    graph = build_coordination_graph(saver)
    value = domain(states[0], expense)
    config = {"configurable": {"thread_id":str(value.reclamo_id)}}
    attempt = uuid4()
    recent = []
    for version, state in enumerate(states, 1):
        value = value.model_copy(update={"estado":state})
        snapshot = CoordinationSnapshot(reclamo_id=value.reclamo_id, intento_id=attempt,
            version=version, etapa=stage_for(value), dominio=value, eventos_recientes=recent)
        result = graph.invoke({"dominio":value.model_dump(mode="json"),
            "contexto":snapshot.model_dump(mode="json"),"evento_id":str(uuid4())},config)
        recent = result["contexto"]["eventos_recientes"]
        # Nuevo servicio/grafo, mismo checkpoint: simula retomar un turno.
        graph = build_coordination_graph(saver)
        saved = graph.get_state(config).values["contexto"]
        assert saved["version"] == version
        assert saved["dominio"]["propiedad_id"] == str(value.propiedad_id)
        assert len(recent) == version
    assert saved["etapa"] == expected


@pytest.mark.parametrize("state,expense,expected", [
    ("Sesión expirada","ordinario","expirada"),
    ("Pendiente de respuesta del responsable","extraordinario","esperando_autorizacion"),
    ("Pendiente de respuesta del responsable","ordinario","esperando_eleccion_proveedor"),
    ("Derivado a inmobiliaria (expensa)","expensa","finalizado"),
    ("Pendiente de autorización - vencido","extraordinario","intervencion_manual"),
    ("Un estado no acordado","ordinario","intervencion_manual"),
])
def test_safe_stage_projection(state,expense,expected):
    assert stage_for(domain(state,expense)) == expected


@pytest.mark.parametrize("state,has_choice,expected", [
    ("Autorizado", True, "choice"),
    ("Pendiente de respuesta del responsable", True, "choice"),
    ("Pendiente de respuesta del responsable", False, "responsible"),
    ("Autorizado", False, None),
    ("Clasificado", False, None),
])
def test_domain_prioritizes_current_choice_deadline(state, has_choice, expected):
    value = domain(state)
    responsible = datetime(2026, 1, 1, tzinfo=timezone.utc)
    choice = datetime(2026, 1, 4, tzinfo=timezone.utc)
    row = {
        "id": value.reclamo_id, "estado": state, "tipo_gasto": value.tipo_gasto,
        "actor_tipo": value.actor_responsable, "propiedad_id": value.propiedad_id,
        "inquilino_id": value.inquilino_id, "propietario_id": value.propietario_id,
        "proveedor_seleccionado_id": None, "presupuesto_seleccionado_id": None,
        "monto_seleccionado": None, "fecha_visita": None, "cancelacion_id": None,
        "respuesta_vence_en": responsible, "eleccion_vence_en": choice if has_choice else None,
    }
    result = PostgresCoordinationRepository._domain(row)
    assert result.vencimiento_especifico == {"choice": choice, "responsible": responsible, None: None}[expected]


def test_graph_rejects_mixing_two_claims():
    first, second = domain(), domain()
    snapshot = CoordinationSnapshot(reclamo_id=first.reclamo_id, intento_id=uuid4(),
        version=1, etapa=stage_for(first), dominio=first)
    with pytest.raises(ValueError,match="corresponde"):
        build_coordination_graph(InMemorySaver()).invoke({
            "dominio":second.model_dump(mode="json"),
            "contexto":snapshot.model_dump(mode="json"),"evento_id":str(uuid4()),
        }, {"configurable":{"thread_id":str(first.reclamo_id)}})


def test_resume_request_cannot_contain_arbitrary_decisions():
    with pytest.raises(ValueError):
        ResumeRequest(evento_id=uuid4(), version_esperada=0, autorizar=True)


def test_recent_events_are_bounded():
    value = domain()
    snapshot = CoordinationSnapshot(reclamo_id=value.reclamo_id,intento_id=uuid4(),
        version=30,etapa=stage_for(value),dominio=value,
        eventos_recientes=[str(uuid4()) for _ in range(20)])
    result = build_coordination_graph(InMemorySaver()).invoke({
        "dominio":value.model_dump(mode="json"),"contexto":snapshot.model_dump(mode="json"),
        "evento_id":str(uuid4()),
    },{"configurable":{"thread_id":str(value.reclamo_id)}})
    assert len(result["contexto"]["eventos_recientes"]) == 20


@pytest.fixture
def fake_api():
    value = domain()
    snapshot = CoordinationSnapshot(reclamo_id=value.reclamo_id,intento_id=uuid4(),
        version=1,etapa=stage_for(value),dominio=value)
    class Service:
        error = None
        calls = []
        def get(self,*args):
            if self.error: raise self.error
            self.calls.append(("get",args))
            return CoordinationResponse(contexto=snapshot,ultima_actividad=datetime.now(timezone.utc))
        def resume(self,*args):
            self.calls.append(("resume",args))
            return self.get(*args)
    service = Service()
    app.dependency_overrides[get_coordination_service] = lambda: service
    app.dependency_overrides[require_participant] = lambda: AuthenticatedUser(
        id=uuid4(),email="operator@example.com",rol="operador",primer_ingreso=False)
    yield TestClient(app), value.reclamo_id, service
    app.dependency_overrides.pop(get_coordination_service,None)
    app.dependency_overrides.pop(require_participant,None)


def test_http_context_and_resume_contract(fake_api):
    client, claim_id, service = fake_api
    assert client.get(f"/reclamos/{claim_id}/coordinacion").status_code == 200
    assert client.post(f"/reclamos/{claim_id}/coordinacion/retomar",json={
        "evento_id":str(uuid4()),"version_esperada":0,
    }).status_code == 200
    assert [c[0] for c in service.calls] == ["get","resume","get"]


@pytest.mark.parametrize("status,code",[
    (404,"not_found"),(409,"coordination_conflict"),(503,"coordination_unavailable"),
])
def test_http_errors_do_not_expose_db_context(fake_api,status,code):
    client,claim_id,service = fake_api
    service.error = CoordinationError("No disponible.",code=code,status=status)
    response = client.get(f"/reclamos/{claim_id}/coordinacion")
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


def test_no_session_cannot_reach_context():
    response = TestClient(app).get(f"/reclamos/{uuid4()}/coordinacion")
    assert response.status_code == 401


def test_missing_migration_has_safe_error():
    import psycopg
    from app.services.coordination_service import CoordinationService
    class BrokenRepository:
        def get(self,*args):
            raise psycopg.errors.UndefinedTable("database detail must not leak")
    with pytest.raises(CoordinationError) as error:
        CoordinationService(BrokenRepository()).get(uuid4(),None)
    assert error.value.status == 503
    assert "database detail" not in str(error.value)


def test_worker_is_opt_in_and_disabled_by_pytest(monkeypatch):
    from app.main import _coordination_worker_enabled
    monkeypatch.delenv("PYTEST_CURRENT_TEST",raising=False)
    monkeypatch.delenv("COORDINATION_WORKER_ENABLED",raising=False)
    assert _coordination_worker_enabled() is False
    monkeypatch.setenv("COORDINATION_WORKER_ENABLED","true")
    assert _coordination_worker_enabled() is True
    monkeypatch.setenv("PYTEST_CURRENT_TEST","synthetic")
    assert _coordination_worker_enabled() is False
