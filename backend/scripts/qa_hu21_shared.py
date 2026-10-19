"""QA autorizado de HU21 en AARI: transacción y savepoints con rollback obligatorio.

Sólo registros propios ficticios. Sin DDL, workers, envíos ni llamadas a LLM.
No acredita un reinicio de proceso con datos comprometidos: ese caso fue local.
"""

import argparse
import faulthandler
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from scripts.apply_hu21_shared import PROJECT_REF
from scripts.check_coordination_postgres import verify


PRIVATE_TABLES = ("checkpoint_migrations", "checkpoints", "checkpoint_blobs",
                  "checkpoint_writes", "eventos")


def table_fingerprints(conn, schema, names):
    """Una consulta por esquema; conserva la huella de todas las columnas."""
    if not names:
        return {}
    parts = [sql.SQL("""
            SELECT {name} AS table_name, count(*) AS n,
                   md5(coalesce(string_agg(md5(to_jsonb(t)::text),''
                         ORDER BY md5(to_jsonb(t)::text)),'')) AS digest
            FROM {table} t
        """).format(name=sql.Literal(name), table=sql.Identifier(schema, name))
        for name in names]
    return {row["table_name"]: {"n": row["n"], "digest": row["digest"]}
            for row in conn.execute(sql.SQL(" UNION ALL ").join(parts))}


def fingerprints(conn):
    names = [row["tablename"] for row in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
    return table_fingerprints(conn, "public", names)


def private_fingerprints(conn):
    return table_fingerprints(conn, "aari_coordinacion", PRIVATE_TABLES)


def sequence_state(conn):
    return conn.execute("SELECT last_value,is_called FROM public.reclamos_numero_seq").fetchone()


@contextmanager
def borrowed_connection(conn):
    # Nunca invocar Connection.__exit__: podría confirmar o cerrar el outer transaction.
    if conn.closed or conn.info.transaction_status != TransactionStatus.INTRANS:
        raise RuntimeError("La prueba requiere una transacción exterior activa.")
    yield conn
    if conn.info.transaction_status != TransactionStatus.INTRANS:
        raise RuntimeError("Se perdió la transacción exterior de rollback.")


class InjectedFailure(RuntimeError):
    pass


def run_cases(conn):
    from langgraph.checkpoint.postgres import PostgresSaver
    from app.agents.coordination.graph import build_coordination_graph
    from app.agents.coordination.state import ResumeRequest
    from app.db.coordination import PostgresCoordinationRepository
    from app.schemas.auth import AuthenticatedUser
    from app.services.coordination_service import CoordinationError, CoordinationService

    passed = []
    now = datetime.now(timezone.utc)

    def repo(clock=now):
        return PostgresCoordinationRepository(
            lambda: borrowed_connection(conn),clock=lambda:clock)

    def state():
        return fingerprints(conn),private_fingerprints(conn)

    def seed(*, status="Autorizado", expense="extraordinario"):
        token = uuid4().hex
        accounts = {}
        for label,role in (("operator","operador"),("owner","propietario"),
                           ("tenant","inquilino"),("outsider","propietario")):
            uid = uuid4()
            email = f"hu21qa-{token}-{label}@example.com"
            conn.execute("""
                INSERT INTO public.usuarios
                    (id,email,password_hash,rol,primer_ingreso,nombre_completo)
                VALUES (%s,%s,'not-a-credential',%s::public.rol_usuario,false,
                        'Operador Sintetico')
            """,(uid,email,role))
            accounts[label] = AuthenticatedUser(id=uid,email=email,rol=role,primer_ingreso=False)
        owner,property_id,tenant,claim = uuid4(),uuid4(),uuid4(),uuid4()
        # DNIs y dirección deliberadamente ficticios; nunca copiar perfiles existentes.
        owner_dni = str(99000000 + (uuid4().int % 400000))
        tenant_dni = str(99400000 + (uuid4().int % 400000))
        conn.execute("""
            INSERT INTO public.propietarios(id,nombre_completo,dni,email,telefono,usuario_id)
            VALUES (%s,'Titular Sintetico',%s,%s,'00000000',%s)
        """,(owner,owner_dni,str(accounts["owner"].email),accounts["owner"].id))
        conn.execute("""
            INSERT INTO public.propiedades
                (id,direccion,provincia,localidad,tipo,propietario_id)
            VALUES (%s,'Unidad ficticia HU21','Córdoba','Localidad de prueba',
                    'casa',%s)
        """,(property_id,owner))
        conn.execute("""
            INSERT INTO public.inquilinos
                (id,nombre_completo,dni,email,telefono,propiedad_id,usuario_id)
            VALUES (%s,'Inquilino Sintetico',%s,%s,'00000000',%s,%s)
        """,(tenant,tenant_dni,str(accounts["tenant"].email),property_id,accounts["tenant"].id))
        # Número explícito: nextval no se revierte con rollback.
        qa_number = 500_000_000_000 + (uuid4().int % 1_000_000_000)
        conn.execute("""
            INSERT INTO public.reclamos
                (id,numero,descripcion,urgencia,inquilino_id,propiedad_id,estado,
                 tipo_gasto,origen_clasificacion,clasificado_en,
                 fundamento_clasificacion,operador_asignado_id)
            VALUES (%s,%s,'PRUEBA HU21: contexto ficticio, no es un reclamo real.',
                    'media',%s,%s,%s,%s::public.tipo_gasto_reclamo,'operador',%s,
                    'Decisión ficticia para validar persistencia.',%s)
        """,(claim,qa_number,tenant,property_id,status,expense,now,accounts["operator"].id))
        actor = "inmobiliaria" if expense=="expensa" else "propietario"
        conn.execute("""
            INSERT INTO public.reclamo_responsables
                (reclamo_id,actor_tipo,destinatario_contacto,canal,solicitado_en,
                 recordatorio_programado_en,respuesta_vence_en)
            VALUES (%s,%s,%s,'email',%s,%s,%s)
        """,(claim,actor,str(accounts["owner"].email),now,
              now+timedelta(hours=48),now+timedelta(hours=72)))
        return claim,accounts

    def start(r,c,u):
        return r.resume(c,ResumeRequest(evento_id=uuid4(),version_esperada=0),u)

    def resume(r,c,u,previous,**kwargs):
        return r.resume(c,ResumeRequest(evento_id=kwargs.get("event",uuid4()),
            version_esperada=kwargs.get("version",previous.contexto.version),
            intento_id=kwargs.get("attempt",previous.contexto.intento_id)),u)

    def rejected(fn,*,status=409):
        before=state()
        try:
            fn()
        except CoordinationError as error:
            assert error.status==status, "Código de rechazo no esperado."
        else:
            raise AssertionError("La operación debió rechazarse.")
        assert state()==before,"Un rechazo modificó datos."

    def case(name,fn,**seed_args):
        print(json.dumps({"case":name,"stage":"starting"}),flush=True)
        with conn.transaction(force_rollback=True):
            c,users=seed(**seed_args)
            fn(c,users)
            assert conn.info.transaction_status == TransactionStatus.INTRANS
        passed.append(name)
        print(json.dumps({"case":name,"stage":"passed"}),flush=True)

    def http_write(c,users):
        from fastapi.testclient import TestClient
        from app.api.coordination import get_coordination_service,require_participant
        from app.main import app
        r=repo()
        app.dependency_overrides[require_participant]=lambda:users["operator"]
        app.dependency_overrides[get_coordination_service]=lambda:CoordinationService(r)
        try:
            with TestClient(app) as client:
                assert client.get(f"/reclamos/{c}/coordinacion").status_code==404
                event=uuid4()
                body={"evento_id":str(event),"version_esperada":0}
                first=client.post(f"/reclamos/{c}/coordinacion/retomar",json=body)
                assert first.status_code==200 and first.json()["contexto"]["version"]==1
                assert first.json()["contexto"]["etapa"]=="esperando_eleccion_proveedor"
                before=state()
                read=client.get(f"/reclamos/{c}/coordinacion")
                duplicate=client.post(f"/reclamos/{c}/coordinacion/retomar",json=body)
                assert read.status_code==200 and duplicate.json()["duplicado"]
                assert read.json()["ultima_actividad"]==first.json()["ultima_actividad"]
                assert state()==before,"GET/duplicado no deben escribir."
        finally:
            app.dependency_overrides.pop(require_participant,None)
            app.dependency_overrides.pop(get_coordination_service,None)
    case("http_write_read_and_replay",http_write)

    def recovery(c,u):
        first=start(repo(),c,u["operator"])
        second=resume(repo(),c,u["operator"],first)
        fresh=repo().get(c,u["operator"])
        assert fresh.contexto==second.contexto and fresh.contexto.version==2
        conn.execute("SET LOCAL search_path=aari_coordinacion,pg_catalog")
        graph=build_coordination_graph(PostgresSaver(conn))
        saved=graph.get_state({"configurable":{"thread_id":str(c)}}).values
        assert saved["contexto"]==fresh.contexto.model_dump(mode="json")
    case("recover_with_new_repository_and_graph",recovery)

    def old_inputs(c,u):
        r=repo()
        first=start(r,c,u["operator"])
        second=resume(r,c,u["operator"],first)
        rejected(lambda:resume(r,c,u["operator"],first))
        rejected(lambda:resume(r,c,u["operator"],second,attempt=uuid4()))
    case("stale_version_and_attempt",old_inputs)

    def fingerprints_replay(c,u):
        r=repo()
        event=uuid4()
        first=r.resume(c,ResumeRequest(evento_id=event,version_esperada=0),u["operator"])
        rejected(lambda:resume(r,c,u["operator"],first,event=event))
    case("event_id_cannot_be_reused_for_other_input",fingerprints_replay)

    def ownership(c,u):
        r=repo()
        start(r,c,u["operator"])
        for key in ("owner","tenant"):
            assert r.get(c,u[key]).contexto.reclamo_id==c
        rejected(lambda:r.get(c,u["outsider"]),status=404)
        rejected(lambda:r.resume(c,ResumeRequest(evento_id=uuid4(),version_esperada=0),
                                  u["outsider"]),status=404)
    case("participant_ownership_and_outsider",ownership)

    def disabled(c,u):
        r=repo()
        first=start(r,c,u["operator"])
        conn.execute("UPDATE public.usuarios SET activo=false WHERE id=%s",(u["operator"].id,))
        rejected(lambda:r.get(c,u["operator"]),status=403)
        rejected(lambda:resume(r,c,u["operator"],first),status=403)
    case("inactive_account_is_rechecked",disabled)

    def atomic_failure(c,u):
        r=repo()
        first=start(r,c,u["operator"])
        before=state()
        original=r._checkpoint
        def fail(conn,snapshot,event):
            original(conn,snapshot,event)
            raise InjectedFailure("Fallo ficticio después de checkpoint.")
        r._checkpoint=fail
        try:
            resume(r,c,u["operator"],first)
        except InjectedFailure:
            pass
        else:
            raise AssertionError("No se inyectó el fallo.")
        assert state()==before,"Un checkpoint parcial escapó al savepoint."
    case("failure_after_checkpoint_is_atomic",atomic_failure)

    def timeout(c,u):
        first=start(repo(),c,u["operator"])
        assert repo(now+timedelta(hours=71)).expire_due()==0
        late=repo(now+timedelta(hours=73))
        assert late.expire_due()==1 and late.expire_due()==0
        value=late.get(c,u["operator"])
        assert value.contexto.etapa=="expirada" and value.contexto.version==2
        assert conn.execute("SELECT estado FROM public.reclamos WHERE id=%s",(c,)).fetchone()["estado"]=="Sesión expirada"
        alerts=conn.execute("""
            SELECT destinatario_contacto,estado_envio FROM public.notificaciones
            WHERE reclamo_id=%s AND clave_idempotencia LIKE 'hu21:%%'
        """,(c,)).fetchall()
        assert len(alerts)==1 and alerts[0]["estado_envio"]=="pendiente"
        assert alerts[0]["destinatario_contacto"]==str(u["operator"].email)
        rejected(lambda:resume(late,c,u["operator"],first))
    case("72h_expiration_and_unique_pending_alert",timeout)

    def specific_timeout(c,u):
        start(repo(),c,u["operator"])
        before=state()
        assert repo(now+timedelta(hours=96)).expire_due()==0
        assert state()==before
    case("specific_authorization_timeout_has_priority",specific_timeout,
         status="Pendiente de respuesta del responsable")

    def visit(c,u):
        first=start(repo(),c,u["operator"])
        conn.execute("UPDATE public.reclamos SET estado='Visita programada',fecha_visita=%s WHERE id=%s",
                     (now+timedelta(days=10),c))
        before=state()
        late=repo(now+timedelta(days=5))
        assert late.expire_due()==0 and state()==before
        value=late.get(c,u["operator"])
        assert value.estado_reclamo_actual=="Visita programada"
        assert value.requiere_sincronizacion
        rejected(lambda:resume(late,c,u["operator"],first))
    case("programmed_visit_is_not_expired",visit)

    def cancelled(c,u):
        r=repo()
        first=start(r,c,u["operator"])
        conn.execute("""
            INSERT INTO public.cancelaciones(reclamo_id,etapa)
            VALUES (%s,'esperando_presupuestos')
        """,(c,))
        conn.execute("UPDATE public.reclamos SET estado='Pendiente de asignación' WHERE id=%s",(c,))
        second=resume(r,c,u["operator"],first)
        assert second.contexto.intento_id!=first.contexto.intento_id
        rejected(lambda:resume(r,c,u["operator"],second,attempt=first.contexto.intento_id))
    case("confirmed_cancellation_invalidates_old_attempt",cancelled)

    def expenses(c,u):
        rejected(lambda:start(repo(),c,u["operator"]))
        assert conn.execute("SELECT count(*) AS n FROM public.sesiones_agente WHERE reclamo_id=%s",
                            (c,)).fetchone()["n"]==0
    case("expensa_keeps_hu14_circuit",expenses,expense="expensa")
    return passed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--authorized",action="store_true")
    parser.add_argument("--env-root",type=Path,required=True)
    parser.add_argument("--diagnostic-after-seconds",type=int,default=0)
    args=parser.parse_args()
    if not args.authorized:
        raise SystemExit("Se requiere autorización explícita de la prueba compartida.")
    # Diagnóstico de hilos: solo stackframes, nunca variables/credenciales.
    if args.diagnostic_after_seconds > 0:
        faulthandler.dump_traceback_later(args.diagnostic_after_seconds,repeat=True)
    values={}
    for f in (args.env_root/".env",args.env_root/"backend"/".env"):
        if f.is_file():values.update(dotenv_values(f))
    try:
        url=make_url(values["DATABASE_URL"])
        target=(url.host==f"db.{PROJECT_REF}.supabase.co" or
                (bool(url.host) and url.host.endswith(".pooler.supabase.com")
                 and url.username==f"postgres.{PROJECT_REF}"))
        if url.get_backend_name()!="postgresql" or not target:
            raise RuntimeError("Destino no autorizado.")
        # El engine importado por FastAPI queda ficticio. Sólo el repositorio prestado usa AARI.
        os.environ["DATABASE_URL"]="sqlite://"
        for variable in ("NOTIFICATION_WORKER_ENABLED","CONTRACT_ANALYSIS_WORKER_ENABLED",
                         "COORDINATION_WORKER_ENABLED","PROVIDER_CANDIDATES_WORKER_ENABLED",
                         "PROVIDER_SPECIALTY_EXTERNAL_ENABLED","LANGSMITH_TRACING",
                         "LANGCHAIN_TRACING_V2"):
            os.environ[variable]="false"
        kwargs=dict(host=url.host,port=url.port or 5432,dbname=url.database,user=url.username,
                    password=url.password,row_factory=dict_row,prepare_threshold=None,
                    connect_timeout=10,autocommit=True)
        kwargs.update(url.query)
        with psycopg.connect(**kwargs) as conn:
            before=fingerprints(conn),private_fingerprints(conn)
            sequence_before=sequence_state(conn)
            passed=[]
            failure=None
            try:
                with conn.transaction(force_rollback=True):
                    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    conn.execute("SET LOCAL lock_timeout='5s'")
                    conn.execute("SET LOCAL statement_timeout='15s'")
                    verify(conn)
                    if conn.execute("SELECT count(*) AS n FROM public.sesiones_agente").fetchone()["n"]!=0:
                        raise RuntimeError("Hay sesiones reales; se requiere un test con alcance adicional.")
                    passed=run_cases(conn)
            except Exception as error:
                failure={"type":type(error).__name__,"sqlstate":getattr(error,"sqlstate",None),
                         "constraint":getattr(getattr(error,"diag",None),"constraint_name",None)}
            after=fingerprints(conn),private_fingerprints(conn)
            sequence_unchanged=sequence_before==sequence_state(conn)
            preserved=before==after
            print(json.dumps({
                "success":failure is None and preserved and sequence_unchanged,
                "passed":len(passed),"cases":passed,"error":failure,
                "rollback_preserved_38_tables":preserved,
                "claim_sequence_unchanged":sequence_unchanged,
                "messages_sent":0,"workers_enabled":False,
                "recovery_scope":"new repository and graph in the same rollback transaction",
            }))
            if failure is not None or not preserved or not sequence_unchanged:
                raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as error:
        print(json.dumps({"success":False,"error_type":type(error).__name__,
                          "message":"Prueba no confirmada; comprobar rollback de forma independiente."}))
        raise SystemExit(1) from None
    finally:
        if args.diagnostic_after_seconds > 0:
            faulthandler.cancel_dump_traceback_later()


if __name__=="__main__":
    main()
