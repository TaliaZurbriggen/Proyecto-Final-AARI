"""Validación optativa de las migraciones AARI-46 en un esquema aislado."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest
from sqlalchemy import create_engine


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SUPABASE_MIGRATION_TESTS") != "1",
    reason="Requiere habilitación explícita para crear un esquema temporal.",
)

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"

PREVIOUS_PROVIDER_SCHEMA = """
create table proveedores (
    id uuid primary key default gen_random_uuid(),
    nombre_razon_social text not null,
    matricula text,
    telefono text not null unique,
    zona_cobertura text not null,
    activo boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_proveedores_zona_largo
        check (char_length(zona_cobertura) <= 100)
);

create index idx_proveedores_zona on proveedores (zona_cobertura);

create table especialidades (
    id uuid primary key default gen_random_uuid(),
    nombre text not null unique
);

create table proveedor_especialidades (
    proveedor_id uuid not null references proveedores(id) on delete cascade,
    especialidad_id uuid not null references especialidades(id) on delete cascade,
    primary key (proveedor_id, especialidad_id)
);

grant all privileges on table
    proveedores,
    especialidades,
    proveedor_especialidades
to anon, authenticated;

insert into proveedores (
    nombre_razon_social,
    telefono,
    zona_cobertura
) values (
    'Proveedor existente',
    '+5493564000046',
    'San Francisco y zona'
);
"""


def test_two_phase_provider_migration_preserves_existing_records() -> None:
    """La fase 1 conserva la zona y la fase 2 exige cobertura estructurada."""

    engine = create_engine(os.environ["DATABASE_URL"])
    schema = f"aari46_migration_{uuid4().hex}"
    migration_15 = (
        MIGRATIONS_DIR / "15_proveedores_cobertura_horario.sql"
    ).read_text(encoding="utf-8")
    migration_16 = (
        MIGRATIONS_DIR / "16_finalizar_cobertura_proveedores.sql"
    ).read_text(encoding="utf-8")
    raw_connection = engine.raw_connection()
    raw_connection.autocommit = True
    cursor = raw_connection.cursor()

    try:
        cursor.execute(f'create schema "{schema}"')
        cursor.execute(f'set search_path to "{schema}", public')
        cursor.execute(PREVIOUS_PROVIDER_SCHEMA)

        cursor.execute(migration_15)
        cursor.execute(
            """
            select is_nullable
            from information_schema.columns
            where table_schema = %s
              and table_name = 'proveedores'
              and column_name = 'zona_cobertura'
            """,
            (schema,),
        )
        assert cursor.fetchone() == ("YES",)

        cursor.execute(
            """
            select count(*)
            from information_schema.tables
            where table_schema = %s
              and table_name in (
                  'proveedor_coberturas',
                  'proveedor_cobertura_barrios'
              )
            """,
            (schema,),
        )
        assert cursor.fetchone() == (2,)

        cursor.execute(
            """
            select c.relname, c.relrowsecurity
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = %s
              and c.relname in (
                  'proveedores',
                  'especialidades',
                  'proveedor_especialidades',
                  'proveedor_coberturas',
                  'proveedor_cobertura_barrios'
              )
            order by c.relname
            """,
            (schema,),
        )
        assert cursor.fetchall() == [
            ("especialidades", True),
            ("proveedor_cobertura_barrios", True),
            ("proveedor_coberturas", True),
            ("proveedor_especialidades", True),
            ("proveedores", True),
        ]

        cursor.execute(
            """
            select count(*)
            from information_schema.role_table_grants
            where table_schema = %s
              and table_name in (
                  'proveedores',
                  'especialidades',
                  'proveedor_especialidades',
                  'proveedor_coberturas',
                  'proveedor_cobertura_barrios'
              )
              and grantee in ('anon', 'authenticated')
            """,
            (schema,),
        )
        assert cursor.fetchone() == (0,)

        cursor.execute(
            """
            insert into proveedores (nombre_razon_social, telefono)
            values ('Proveedor nuevo', '+5493564000047')
            """
        )

        with pytest.raises(
            psycopg2.Error,
            match=r"2 proveedor\(es\) no tienen cobertura estructurada",
        ):
            cursor.execute(migration_16)
        cursor.execute("rollback")

        cursor.execute(
            """
            insert into proveedor_coberturas (
                proveedor_id,
                provincia,
                localidad,
                cubre_toda_localidad
            )
            select id, 'Córdoba', 'San Francisco', true
            from proveedores
            """
        )

        cursor.execute(migration_16)
        cursor.execute(
            """
            select count(*)
            from information_schema.columns
            where table_schema = %s
              and table_name = 'proveedores'
              and column_name = 'zona_cobertura'
            """,
            (schema,),
        )
        assert cursor.fetchone() == (0,)

        cursor.execute(migration_16)
    finally:
        try:
            cursor.execute("rollback")
            cursor.execute("set search_path to public")
            cursor.execute(f'drop schema if exists "{schema}" cascade')
        finally:
            cursor.close()
            raw_connection.close()
            engine.dispose()
