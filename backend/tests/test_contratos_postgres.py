"""HU29: SQL PostgreSQL real aislado, con rollback de esquema y filas."""
import os
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.contratos import SqlAlchemyContractsRepository
from app.schemas.contratos import ContractCreate, ContractEnd
from tests.test_contratos import user, uid

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CONTRATOS_POSTGRES_TESTS") != "1",
    reason="Requiere autorización explícita para probar SQL en Supabase con rollback.",
)


def test_real_migration_repository_rls_overlap_and_rollback():
    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 10})
    schema = "aari318_test_" + uuid4().hex
    sql = (Path(__file__).parents[1] / "migrations" / "20_contratos_alquiler.sql").read_text(encoding="utf-8")
    # Misma migración, solo cambia el destino. Ninguna tabla de public/Storage se modifica.
    sql = "\n".join(line for line in sql.splitlines() if line.strip() not in {"begin;", "commit;"})
    sql = sql.replace("public.", f'"{schema}".').replace("storage.buckets", f'"{schema}".buckets')
    sql = sql.replace("set local search_path = public, extensions;", f'set local search_path = "{schema}", extensions;')
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path = "{schema}", public'))
            for ddl in [
                "CREATE TABLE usuarios (id uuid PRIMARY KEY)",
                "CREATE TABLE propietarios (id uuid PRIMARY KEY, usuario_id uuid, nombre_completo text)",
                "CREATE TABLE propiedades (id uuid PRIMARY KEY, propietario_id uuid, direccion text, localidad text, provincia text)",
                "CREATE TABLE inquilinos (id uuid PRIMARY KEY, usuario_id uuid, propiedad_id uuid, nombre_completo text)",
                "CREATE TABLE buckets (id text PRIMARY KEY, name text, public boolean, file_size_limit bigint, allowed_mime_types text[])",
            ]:
                connection.execute(text(ddl))
            connection.exec_driver_sql(sql)
            for n in (1, 2, 3, 4):
                connection.execute(text("INSERT INTO usuarios VALUES (:id)"), {"id": uid(n)})
            connection.execute(text("INSERT INTO propietarios VALUES (:id,:id,'Titular sintético')"), {"id": uid(2)})
            connection.execute(text("INSERT INTO inquilinos VALUES (:id,:id,:p,'Inquilino sintético')"), {"id": uid(3), "p": uid(20)})
            connection.execute(text("INSERT INTO propiedades VALUES (:id,:owner,'Dirección sintética','Localidad','Provincia')"), {"id": uid(20), "owner": uid(2)})
            factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
            repo = SqlAlchemyContractsRepository(factory)
            first = repo.create(ContractCreate(inquilino_id=uid(3), propiedad_id=uid(20), fecha_inicio="2026-09-01", fecha_fin="2027-08-31"), uid(1))
            metadata = {"id": str(uuid4()), "storage_path": f"{first}/test.pdf", "nombre_archivo": "test.pdf", "tamano": 50, "sha256": "a" * 64}
            repo.save_document(first, metadata, True, 1, uid(1))
            assert repo.get(first, user(3, "inquilino"))["estado"] == "firmado"
            assert repo.list(user(4, "propietario"))[1] == 0
            # Fuerza la barrera SQL (incluye el último día); no depende de la validación Python.
            with pytest.raises(IntegrityError) as overlap, connection.begin_nested():
                connection.execute(text("""INSERT INTO contratos (id,inquilino_id,propietario_id,propiedad_id,fecha_inicio,fecha_fin,estado)
                    VALUES (:id,:tenant,:owner,:property,'2027-08-31','2028-08-31','firmado')"""),
                    {"id": str(uuid4()), "tenant": uid(3), "owner": uid(2), "property": uid(20)})
            assert overlap.value.orig.pgcode == "23P01"
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("UPDATE contratos SET estado='finalizado' WHERE id=:id"), {"id": first})
            for table, key in (("inquilinos", uid(3)), ("propietarios", uid(2)), ("propiedades", uid(20))):
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id": key})
            repo.end(first, ContractEnd(fecha_finalizacion="2026-09-12", revision=2), uid(1), date(2026, 9, 12))
            assert repo.get(first, user(2, "propietario"))["estado"] == "finalizado"
            renewed = repo.create(ContractCreate(inquilino_id=uid(3), propiedad_id=uid(20), fecha_inicio="2026-09-13", fecha_fin="2027-09-12", contrato_anterior_id=UUID(first)), uid(1))
            assert renewed != first
            security = connection.execute(text("""
                SELECT c.relname, c.relrowsecurity,
                    has_table_privilege('anon', c.oid, 'SELECT') AS anon_select,
                    has_table_privilege('authenticated', c.oid, 'SELECT') AS authenticated_select
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=:schema AND c.relname in ('contratos','contrato_documentos','contrato_eventos')
            """), {"schema": schema}).all()
            assert len(security) == 3 and all(row[1:] == (True, False, False) for row in security)
            assert connection.execute(text("SELECT public FROM buckets WHERE id='contratos-alquiler'")).scalar_one() is False
        finally:
            transaction.rollback()
        assert connection.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname=:schema"), {"schema": schema}).scalar_one() == 0
    engine.dispose()
