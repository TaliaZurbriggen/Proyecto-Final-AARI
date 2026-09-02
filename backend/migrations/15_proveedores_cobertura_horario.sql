-- ============================================================
-- AARI-46 — Preparación de cobertura estructurada y horario habitual
-- Fase 1 para bases creadas con 01_modulo_administracion.sql.
-- Conserva temporalmente zona_cobertura para migrar proveedores existentes.
-- ============================================================

begin;

-- Los proveedores nuevos ya escriben coberturas estructuradas. La columna
-- anterior queda nullable y disponible únicamente como referencia durante la
-- migración manual. La fase 2 (migración 16) la elimina cuando no quedan
-- proveedores sin cobertura estructurada.
do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = current_schema()
          and table_name = 'proveedores'
          and column_name = 'zona_cobertura'
    ) then
        alter table proveedores alter column zona_cobertura drop not null;
    end if;
end
$$;

alter table proveedores
    add column if not exists hora_inicio time,
    add column if not exists hora_fin time;

alter table proveedores
    drop constraint if exists chk_proveedores_nombre_largo,
    drop constraint if exists chk_proveedores_nombre_con_letra,
    drop constraint if exists chk_proveedores_matricula_largo,
    drop constraint if exists chk_proveedores_telefono_whatsapp,
    drop constraint if exists chk_proveedores_horario_completo,
    drop constraint if exists chk_proveedores_horario_orden;

alter table proveedores
    add constraint chk_proveedores_nombre_largo
        check (char_length(btrim(nombre_razon_social)) between 2 and 150),
    add constraint chk_proveedores_nombre_con_letra
        check (nombre_razon_social ~ '[[:alpha:]]'),
    add constraint chk_proveedores_matricula_largo
        check (matricula is null or char_length(btrim(matricula)) between 1 and 80),
    add constraint chk_proveedores_telefono_whatsapp
        check (telefono ~ '^\+[0-9]{8,15}$'),
    add constraint chk_proveedores_horario_completo
        check ((hora_inicio is null) = (hora_fin is null)),
    add constraint chk_proveedores_horario_orden
        check (hora_inicio is null or hora_fin > hora_inicio);

create table if not exists proveedor_coberturas (
    id                      uuid primary key default gen_random_uuid(),
    proveedor_id            uuid not null references proveedores(id) on delete cascade,
    provincia               text not null,
    localidad               text not null,
    cubre_toda_localidad    boolean not null default true,

    constraint chk_proveedor_cobertura_provincia_valida
        check (provincia in (
            'Buenos Aires', 'Ciudad Autónoma de Buenos Aires', 'Catamarca',
            'Chaco', 'Chubut', 'Córdoba', 'Corrientes', 'Entre Ríos',
            'Formosa', 'Jujuy', 'La Pampa', 'La Rioja', 'Mendoza',
            'Misiones', 'Neuquén', 'Río Negro', 'Salta', 'San Juan',
            'San Luis', 'Santa Cruz', 'Santa Fe', 'Santiago del Estero',
            'Tierra del Fuego, Antártida e Islas del Atlántico Sur',
            'Tucumán'
        )),
    constraint chk_proveedor_cobertura_localidad_largo
        check (char_length(btrim(localidad)) between 2 and 100),
    constraint chk_proveedor_cobertura_localidad_con_letra
        check (localidad ~ '[[:alpha:]]')
);

create unique index if not exists uq_proveedor_cobertura_localidad_normalizada
    on proveedor_coberturas (
        proveedor_id, lower(btrim(provincia)), lower(btrim(localidad))
    );
create index if not exists idx_proveedor_coberturas_ubicacion
    on proveedor_coberturas (provincia, localidad);

create table if not exists proveedor_cobertura_barrios (
    id              uuid primary key default gen_random_uuid(),
    cobertura_id    uuid not null references proveedor_coberturas(id) on delete cascade,
    barrio          text not null,

    constraint chk_proveedor_cobertura_barrio_largo
        check (char_length(btrim(barrio)) between 2 and 100),
    constraint chk_proveedor_cobertura_barrio_con_letra
        check (barrio ~ '[[:alpha:]]')
);

create unique index if not exists uq_proveedor_cobertura_barrio_normalizado
    on proveedor_cobertura_barrios (cobertura_id, lower(btrim(barrio)));
create index if not exists idx_proveedor_cobertura_barrios_barrio
    on proveedor_cobertura_barrios (barrio);

alter table especialidades
    drop constraint if exists especialidades_nombre_key,
    drop constraint if exists chk_especialidades_nombre_largo,
    drop constraint if exists chk_especialidades_nombre_con_letra;
alter table especialidades
    add constraint chk_especialidades_nombre_largo
        check (char_length(btrim(nombre)) between 2 and 80),
    add constraint chk_especialidades_nombre_con_letra
        check (nombre ~ '[[:alpha:]]');

create unique index if not exists uq_especialidades_nombre_normalizado
    on especialidades (lower(btrim(nombre)));

insert into especialidades (nombre) values
    ('plomería'),
    ('gasista'),
    ('electricidad'),
    ('cerrajería'),
    ('pintura'),
    ('albañilería'),
    ('otros')
on conflict do nothing;

-- Estas tablas se consultan únicamente desde FastAPI. Se explicita la
-- protección para que una instalación nueva o actualizada no dependa de la
-- configuración manual del panel de Supabase.
alter table proveedores enable row level security;
alter table especialidades enable row level security;
alter table proveedor_especialidades enable row level security;
alter table proveedor_coberturas enable row level security;
alter table proveedor_cobertura_barrios enable row level security;

revoke all privileges on table
    proveedores,
    especialidades,
    proveedor_especialidades,
    proveedor_coberturas,
    proveedor_cobertura_barrios
from anon, authenticated;

commit;
