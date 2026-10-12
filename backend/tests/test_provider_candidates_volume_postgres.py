"""HU15: padrones grandes, expectativas independientes y ninguna API externa.

Cada caso crea una base PostgreSQL local descartable. Los grupos esperados
son explícitos: no se reproduce el predicado SQL para calcular los aciertos.
"""

from concurrent.futures import ThreadPoolExecutor
from math import ceil
import os
from statistics import median
from threading import Event
from time import perf_counter
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import bindparam, event, text

from app.api.auth import get_current_user
from app.api.provider_candidates import get_candidates_repository, router
from app.schemas.auth import AuthenticatedUser
from app.services.provider_candidates_worker import ProviderCandidatesWorker
from tests.test_provider_candidates_agent_postgres import automatic_case
from tests.test_provider_candidates_postgres import ready_case, command, execute
from tests.test_responsible_actor_postgres import claim_case, local_engine, snapshot

pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"),
                               reason="Requiere PostgreSQL local dedicado; nunca Supabase.")

GROUPS = (
    "localidad_completa", "barrio_exacto", "multiespecialidad_multicobertura",
    "inactivo", "otra_especialidad", "otra_localidad", "otra_provincia",
    "barrio_parecido", "sin_cobertura", "geografia_en_coberturas_distintas",
    "caracteres_literales", "mayusculas_y_extremos",
)


@pytest.fixture(autouse=True)
def no_external_services(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("La prueba de volumen no puede consumir Gemini, SMTP ni Storage.")
    monkeypatch.setattr("app.agents.provider_candidates.get_specialty_resolver", forbidden)
    monkeypatch.setattr("app.agents.classification.nodes.get_gemini_classifier", forbidden)
    monkeypatch.setattr("app.services.claim_notifications.SmtpClaimEmailSender.send", forbidden)
    monkeypatch.setattr("app.services.claim_storage.SupabaseClaimPhotoStorage.download", forbidden)


def seed(case, per_group):
    db, _, _, _, specialty = case
    other_specialty = uuid4()
    rows, specialties, coverages, neighborhoods = [], [], [], []
    ids = {group: set() for group in GROUPS}
    names = {}

    def coverage(identifier, suffix, *, province="Córdoba", city="Localidad de prueba", areas=()):
        coverage_id = uuid5(identifier, suffix)
        coverages.append({"id": coverage_id, "provider": identifier, "province": province,
                          "city": city, "whole": not areas})
        neighborhoods.extend({"id": uuid5(coverage_id, area), "coverage": coverage_id, "area": area} for area in areas)

    for group_index, group in enumerate(GROUPS):
        for index in range(per_group):
            number = group_index * per_group + index
            identifier = uuid5(NAMESPACE_URL, f"aari-hu15-volume/{group}/{index}")
            # Nombres repetidos a propósito: se verifica el desempate por UUID.
            name = f"Proveedor ficticio QA {number % 7}"
            names[identifier] = name
            ids[group].add(identifier)
            rows.append({"id": identifier, "name": name, "phone": f"+549000{number:08d}",
                         "active": group != "inactivo"})
            specialties.append({"provider": identifier, "specialty": other_specialty if group == "otra_especialidad" else specialty})
            if group == "multiespecialidad_multicobertura":
                specialties.append({"provider": identifier, "specialty": other_specialty})
                coverage(identifier, "canonical")
                coverage(identifier, "other", city="Otra localidad", areas=("Centro", "Norte", "Sur"))
            elif group == "sin_cobertura":
                pass  # Dato heredado incompleto: nunca es candidato.
            elif group == "otra_localidad":
                coverage(identifier, "other", city="Otra localidad")
            elif group == "otra_provincia":
                coverage(identifier, "other", province="Santa Fe")
            elif group == "geografia_en_coberturas_distintas":
                coverage(identifier, "city", province="Santa Fe")
                coverage(identifier, "province", city="Otra localidad")
            elif group == "barrio_exacto":
                coverage(identifier, "canonical", areas=("Centro", "Oeste"))
            elif group == "barrio_parecido":
                coverage(identifier, "canonical", areas=("Centro Norte",))
            elif group == "caracteres_literales":
                coverage(identifier, "canonical", areas=("Centro%", "Centro_"))
            elif group == "mayusculas_y_extremos":
                coverage(identifier, "canonical", city="  LOCALIDAD DE PRUEBA  ", areas=("  cEnTrO  ",))
            else:
                coverage(identifier, "canonical")
    with db.begin() as c:
        c.execute(text("INSERT INTO especialidades (id,nombre) VALUES (:id,'Otra especialidad ficticia QA')"),
                  {"id": other_specialty})
        c.execute(text("""
            INSERT INTO proveedores (id,nombre_razon_social,telefono,activo,hora_inicio,hora_fin)
            VALUES (:id,:name,:phone,:active,'08:00','17:00')
        """), rows)
        c.execute(text("INSERT INTO proveedor_especialidades (proveedor_id,especialidad_id) VALUES (:provider,:specialty)"), specialties)
        c.execute(text("""
            INSERT INTO proveedor_coberturas (id,proveedor_id,provincia,localidad,cubre_toda_localidad)
            VALUES (:id,:provider,:province,:city,:whole)
        """), coverages)
        c.execute(text("INSERT INTO proveedor_cobertura_barrios (id,cobertura_id,barrio) VALUES (:id,:coverage,:area)"), neighborhoods)
        assert c.execute(text("SELECT count(*) FROM proveedores")).scalar_one() == per_group * len(GROUPS)
    return SimpleNamespace(case=case, ids=ids, names=names, other_specialty=other_specialty,
                           per_group=per_group, total=per_group * len(GROUPS))


@pytest.fixture
def large_case(automatic_case, request):
    case, jobs = automatic_case
    data = seed(case, getattr(request, "param", 100))
    data.jobs = jobs
    return data


def expected(data, *groups):
    identifiers = set().union(*(data.ids[group] for group in groups))
    return sorted(identifiers, key=lambda identifier: (data.names[identifier].lower(), identifier.int))


def locate(data, *, province="Córdoba", city="Localidad de prueba", area="Centro", specialty=None):
    db, _, claim, _, primary = data.case
    with db.begin() as c:
        c.execute(text("""
            UPDATE propiedades SET provincia=:province,localidad=:city,barrio=:area
            WHERE id=(SELECT propiedad_id FROM reclamos WHERE id=:id)
        """), {"id": claim, "province": province, "city": city, "area": area})
        c.execute(text("UPDATE reclamos SET tipo_id=:specialty WHERE id=:id"),
                  {"id": claim, "specialty": specialty or primary})


@pytest.mark.parametrize(("province", "city", "area", "groups"), [
    ("Córdoba", "Localidad de prueba", "Centro", ("localidad_completa", "barrio_exacto", "multiespecialidad_multicobertura", "mayusculas_y_extremos")),
    ("Córdoba", "Localidad de prueba", None, ("localidad_completa", "multiespecialidad_multicobertura")),
    ("Córdoba", "Localidad de prueba", "Centro Norte", ("localidad_completa", "multiespecialidad_multicobertura", "barrio_parecido")),
    ("Córdoba", "Localidad de prueba", "Barrio inexistente", ("localidad_completa", "multiespecialidad_multicobertura")),
    ("Córdoba", "Localidad de prueba", "Centro%", ("localidad_completa", "multiespecialidad_multicobertura", "caracteres_literales")),
    ("Córdoba", "Localidad de prueba", "Centro_", ("localidad_completa", "multiespecialidad_multicobertura", "caracteres_literales")),
    ("Córdoba", "Localidad de prueba", "Centro' OR true --", ("localidad_completa", "multiespecialidad_multicobertura")),
    ("Córdoba", "LOCALIDAD DE PRUEBA", "  CENTRO  ", ("localidad_completa", "barrio_exacto", "multiespecialidad_multicobertura", "mayusculas_y_extremos")),
    ("Córdoba", "Otra localidad", "Centro", ("multiespecialidad_multicobertura", "otra_localidad", "geografia_en_coberturas_distintas")),
    ("Santa Fe", "Localidad de prueba", "Centro", ("otra_provincia", "geografia_en_coberturas_distintas")),
    ("Córdoba", "Localidad sin cobertura", "Centro", ()),
])
def test_exact_eligibility_against_explicit_groups(large_case, province, city, area, groups):
    data = large_case
    locate(data, province=province, city=city, area=area)
    view = data.case[1].get(data.case[2], page_size=100)
    wanted = expected(data, *groups)
    saved = execute(data.case, command(data.case[1], data.case[2], data.case[-1]))
    assert saved.candidato_ids == wanted  # Todos los IDs, no sólo la primera página.
    assert view.total == len(wanted)
    assert [item.id for item in view.candidatos] == wanted[:100]
    assert view.resultado == ("candidatos_encontrados" if wanted else "sin_candidatos")
    assert all(item.activo for item in view.candidatos)


def test_other_specialty_is_not_confused_with_primary(large_case):
    data = large_case
    locate(data, specialty=data.other_specialty)
    wanted = expected(data, "multiespecialidad_multicobertura", "otra_especialidad")
    view = data.case[1].get(data.case[2], page_size=100)
    saved = execute(data.case, command(data.case[1], data.case[2], data.other_specialty))
    assert saved.candidato_ids == wanted
    assert view.total == len(wanted)
    assert [item.id for item in view.candidatos] == wanted[:100]
    assert all(data.other_specialty in {specialty.id for specialty in item.especialidades} for item in view.candidatos)


@pytest.mark.parametrize("page_size", [20, 37, 100])
def test_all_pages_are_stable_complete_unique_and_read_only(large_case, page_size):
    data = large_case
    db, repo, claim, _, specialty = data.case
    locate(data)
    saved = execute(data.case, command(repo, claim, specialty))
    wanted = expected(data, "localidad_completa", "barrio_exacto", "multiespecialidad_multicobertura", "mayusculas_y_extremos")
    assert saved.candidato_ids == wanted
    before = snapshot(db, claim)
    seen = []
    page_count = ceil(len(wanted) / page_size)
    for page in range(1, page_count + 1):
        view = repo.get(claim, page=page, page_size=page_size)
        assert view.total == len(wanted) and view.total_pages == page_count
        assert len(view.candidatos) == min(page_size, len(wanted) - len(seen))
        assert all(item.hora_inicio is not None and item.hora_fin is not None for item in view.candidatos)
        seen.extend(item.id for item in view.candidatos)
    assert seen == wanted and len(set(seen)) == len(wanted)
    assert [item.id for item in repo.get(claim, page=1, page_size=page_size).candidatos] == wanted[:page_size]
    outside = repo.get(claim, page=page_count + 1, page_size=page_size)
    assert outside.total == len(wanted) and outside.candidatos == []
    assert snapshot(db, claim) == before and repo.get(claim).historial_total == 1


def test_real_http_returns_bounded_pages_and_complete_totals(large_case):
    data = large_case
    _, repo, claim, actor, _ = data.case
    locate(data)
    wanted = expected(data, "localidad_completa", "barrio_exacto", "multiespecialidad_multicobertura", "mayusculas_y_extremos")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=actor,email="qa@example.com",rol="operador",primer_ingreso=False)
    app.dependency_overrides[get_candidates_repository] = lambda: repo
    with TestClient(app) as client:
        url = f"/reclamos/{claim}/proveedores-candidatos"
        response = client.get(url, params={"page": 2, "page_size": 100})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 400 and body["total_pages"] == 4
        assert [item["id"] for item in body["candidatos"]] == [str(identifier) for identifier in wanted[100:200]]
        assert client.get(url, params={"page_size": 101}).status_code == 422
        assert client.get(url, params={"page": 0}).status_code == 422


class CapturingResolver:
    def __init__(self, specialty):
        self.specialty = specialty
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return {"especialidad_id": self.specialty, "fundamento": "Prueba sintética.", "evidencia": "Descripción sintética"}


@pytest.mark.parametrize("large_case", [100, 1000], indirect=True)
def test_automatic_graph_persists_all_candidates_without_sending_the_directory(large_case):
    data = large_case
    db, repo, claim, _, specialty = data.case
    model = CapturingResolver(specialty)
    wanted = expected(data, "localidad_completa", "barrio_exacto", "multiespecialidad_multicobertura", "mayusculas_y_extremos")
    before = snapshot(db, claim)
    worker = ProviderCandidatesWorker(data.jobs, resolver=model)
    assert worker.process_one() and not worker.process_one()
    assert len(model.prompts) == 1
    assert "Proveedor ficticio QA" not in model.prompts[0] and '"telefono"' not in model.prompts[0]
    assert not any(str(identifier) in model.prompts[0] for identifiers in data.ids.values() for identifier in identifiers)
    view = repo.get(claim)
    assert view.tarea_agente == "completada" and view.total == data.per_group * 4
    assert view.historial_total == 1 and view.historial_busquedas[0].candidato_ids == wanted
    assert view.historial_busquedas[0].origen == "agente"
    after = snapshot(db, claim)
    for key in ("estado", "tipo_gasto", "confianza_clasificacion", "fundamento_clasificacion", "proveedor_seleccionado_id"):
        assert after["reclamos"][0][key] == before["reclamos"][0][key]
    for table in ("reclamo_responsables", "reclamo_historial_estados", "notificaciones"):
        assert after[table] == before[table]
    with db.connect() as c:
        for table in ("presupuestos", "visitas", "proveedores_externos"):
            assert c.execute(text(f"SELECT count(*) FROM {table} WHERE reclamo_id=:id"), {"id": claim}).scalar_one() == 0


def test_directory_changes_are_live_but_audited_snapshot_is_preserved(large_case):
    data = large_case
    db, repo, claim, _, specialty = data.case
    locate(data)
    saved = execute(data.case, command(repo, claim, specialty))
    wanted = expected(data, "localidad_completa", "barrio_exacto", "multiespecialidad_multicobertura", "mayusculas_y_extremos")
    assert saved.candidato_ids == wanted
    with db.begin() as c:
        c.execute(text("UPDATE proveedores SET activo=false WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                  {"ids": list(data.ids["barrio_exacto"])})
        c.execute(text("UPDATE proveedor_coberturas SET localidad='Localidad modificada QA' WHERE proveedor_id IN :ids")
                  .bindparams(bindparam("ids", expanding=True)), {"ids": list(data.ids["mayusculas_y_extremos"])})
    view = repo.get(claim, page_size=100)
    current = expected(data, "localidad_completa", "multiespecialidad_multicobertura")
    assert view.total == 200 and [item.id for item in view.candidatos] == current[:100]
    assert view.historial_busquedas[0].candidato_ids == wanted
    assert view.historial_total == 1


def test_eight_workers_still_invoke_model_once_with_large_directory(large_case):
    data = large_case
    _, repo, claim, _, specialty = data.case
    entered, release = Event(), Event()
    class SlowResolver(CapturingResolver):
        def invoke(self, prompt):
            entered.set()
            assert release.wait(timeout=10)
            return super().invoke(prompt)
    model = SlowResolver(specialty)
    worker = ProviderCandidatesWorker(data.jobs, resolver=model)
    with ThreadPoolExecutor(max_workers=8) as threads:
        first = threads.submit(worker.process_one)
        assert entered.wait(timeout=5)
        others = [threads.submit(worker.process_one) for _ in range(7)]
        try:
            assert all(future.result(timeout=5) is False for future in others)
        finally:
            release.set()
        assert first.result(timeout=5)
    assert len(model.prompts) == 1 and repo.get(claim).historial_total == 1
    assert repo.get(claim).total == 400


@pytest.mark.parametrize("large_case", [10, 100, 1000], indirect=True)
def test_read_query_count_does_not_grow_per_provider_and_record_local_timings(large_case, record_property):
    data = large_case
    db, repo, claim, _, specialty = data.case
    locate(data)
    wanted = expected(data, "localidad_completa", "barrio_exacto", "multiespecialidad_multicobertura", "mayusculas_y_extremos")
    saved = execute(data.case, command(repo, claim, specialty))
    assert saved.candidato_ids == wanted
    statements, durations, counts = [], [], []
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(db, "before_cursor_execute", capture)
    try:
        for _ in range(10):
            statements.clear()
            start = perf_counter()
            view = repo.get(claim, page_size=20)
            durations.append((perf_counter() - start) * 1000)
            counts.append(len(statements))
            assert view.total == len(wanted) and [item.id for item in view.candidatos] == wanted[:20]
    finally:
        event.remove(db, "before_cursor_execute", capture)
    assert max(counts) <= 12  # No consultas por cada contacto o cobertura.
    p50, p95 = median(durations), sorted(durations)[ceil(len(durations) * .95) - 1]
    record_property("proveedores", data.total)
    record_property("candidatos", len(wanted))
    record_property("sql_por_lectura", max(counts))
    record_property("p50_ms_local", round(p50,2))
    record_property("p95_ms_local", round(p95,2))
    print(f"HU15 volumen local: {data.total} proveedores, {len(wanted)} candidatos, "
          f"SQL/lectura={max(counts)}, p50={p50:.2f} ms, p95={p95:.2f} ms.")
