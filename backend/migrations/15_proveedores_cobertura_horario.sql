-- ============================================================
-- AARI-46 — Proveedores, cobertura estructurada y horario habitual
-- Migración incremental para bases creadas con 01_modulo_administracion.sql
-- ============================================================

begin;

-- La columna libre no puede convertirse de forma confiable a provincia,
-- localidad y barrios. Evitamos perder datos si ya hubiera proveedores.
do $$
begin
    if exists (select 1 from proveedores limit 1) then
        raise exception using
            message = 'AARI-46 requiere revisar los proveedores existentes antes de reemplazar zona_cobertura.';
    end if;
end
$$;

drop index if exists idx_proveedores_zona;

alter table proveedores
    drop constraint if exists chk_proveedores_zona_largo,
    drop column if exists zona_cobertura,
    add column if not exists hora_inicio time,
    add column if not exists hora_fin time;

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

alter table especialidades drop constraint if exists especialidades_nombre_key;
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

commit;
