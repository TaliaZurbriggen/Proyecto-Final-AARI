-- ============================================================
-- AARI-22 — Ubicación precisa y piso numérico de propiedades
-- Aplicar después de 08_propiedades_integridad.sql.
-- ============================================================

begin;

-- Provincia y localidad no pueden inferirse de la antigua "zona". La
-- migración se detiene si hubiera registros que requieran enriquecimiento
-- manual, en lugar de inventar datos geográficos.
do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'propiedades'
          and column_name = 'zona'
    ) and exists (select 1 from propiedades) then
        raise exception 'Hay propiedades existentes: completar provincia y localidad antes de aplicar la migración 09';
    end if;

    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'propiedades'
          and column_name = 'zona'
    ) and not exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'propiedades'
          and column_name = 'barrio'
    ) then
        alter table propiedades rename column zona to barrio;
    end if;
end
$$;

alter table propiedades
    add column if not exists provincia text,
    add column if not exists localidad text,
    add column if not exists barrio text;

alter table propiedades
    alter column provincia set not null,
    alter column localidad set not null,
    alter column barrio drop not null;

-- El piso pasa de texto a entero. Se admite 0 para planta baja y valores
-- negativos para subsuelos.
alter table propiedades
    drop constraint if exists chk_propiedades_piso_largo;

drop index if exists uq_propiedades_direccion_depto_normalizada;
drop index if exists uq_propiedades_direccion_no_depto_normalizada;

do $$
declare
    piso_tipo text;
begin
    select data_type into piso_tipo
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'propiedades'
      and column_name = 'piso';

    if piso_tipo <> 'integer' then
        if exists (
            select 1 from propiedades
            where piso is not null and btrim(piso) !~ '^-?[0-9]+$'
        ) then
            raise exception 'Hay pisos no numéricos; convertir PB a 0 antes de aplicar la migración 09';
        end if;

        execute $migration$
            alter table propiedades
                alter column piso type integer
                using piso::integer
        $migration$;
    end if;
end
$$;

update propiedades
set direccion = regexp_replace(btrim(direccion), '\s+', ' ', 'g'),
    provincia = regexp_replace(btrim(provincia), '\s+', ' ', 'g'),
    localidad = regexp_replace(btrim(localidad), '\s+', ' ', 'g'),
    barrio = nullif(regexp_replace(btrim(coalesce(barrio, '')), '\s+', ' ', 'g'), ''),
    numero = nullif(regexp_replace(btrim(coalesce(numero, '')), '\s+', ' ', 'g'), ''),
    updated_at = now();

update propiedades
set piso = null,
    numero = null,
    updated_at = now()
where tipo <> 'departamento' and (piso is not null or numero is not null);

drop index if exists uq_propiedades_direccion_depto_normalizada;
drop index if exists uq_propiedades_direccion_no_depto_normalizada;

create unique index uq_propiedades_direccion_depto_normalizada
    on propiedades (
        lower(btrim(provincia)),
        lower(btrim(localidad)),
        lower(btrim(direccion)),
        coalesce(piso, -2147483648),
        lower(coalesce(btrim(numero), ''))
    )
    where tipo = 'departamento';

create unique index uq_propiedades_direccion_no_depto_normalizada
    on propiedades (
        lower(btrim(provincia)),
        lower(btrim(localidad)),
        lower(btrim(direccion))
    )
    where tipo <> 'departamento';

alter table propiedades
    drop constraint if exists chk_propiedades_zona_largo,
    drop constraint if exists chk_propiedades_piso_largo,
    drop constraint if exists chk_propiedades_provincia_largo,
    drop constraint if exists chk_propiedades_provincia_valida,
    drop constraint if exists chk_propiedades_localidad_largo,
    drop constraint if exists chk_propiedades_barrio_largo;

alter table propiedades
    add constraint chk_propiedades_provincia_largo
        check (char_length(btrim(provincia)) between 2 and 100),
    add constraint chk_propiedades_provincia_valida
        check (provincia in (
            'Buenos Aires', 'Ciudad Autónoma de Buenos Aires', 'Catamarca',
            'Chaco', 'Chubut', 'Córdoba', 'Corrientes', 'Entre Ríos',
            'Formosa', 'Jujuy', 'La Pampa', 'La Rioja', 'Mendoza',
            'Misiones', 'Neuquén', 'Río Negro', 'Salta', 'San Juan',
            'San Luis', 'Santa Cruz', 'Santa Fe', 'Santiago del Estero',
            'Tierra del Fuego, Antártida e Islas del Atlántico Sur',
            'Tucumán'
        )),
    add constraint chk_propiedades_localidad_largo
        check (char_length(btrim(localidad)) between 2 and 100),
    add constraint chk_propiedades_barrio_largo
        check (barrio is null or char_length(btrim(barrio)) between 2 and 100);

commit;
