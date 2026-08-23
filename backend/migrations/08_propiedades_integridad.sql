-- ============================================================
-- AARI-22 — Integridad y unicidad normalizada de propiedades
-- Aplicar después de 07_propietarios_email_unico.sql.
-- ============================================================

begin;

update propiedades
set direccion = regexp_replace(btrim(direccion), '\s+', ' ', 'g'),
    zona = regexp_replace(btrim(zona), '\s+', ' ', 'g'),
    piso = nullif(regexp_replace(btrim(coalesce(piso, '')), '\s+', ' ', 'g'), ''),
    numero = nullif(regexp_replace(btrim(coalesce(numero, '')), '\s+', ' ', 'g'), ''),
    updated_at = now();

update propiedades
set piso = null,
    numero = null,
    updated_at = now()
where tipo <> 'departamento' and (piso is not null or numero is not null);

do $$
begin
    if exists (
        select 1
        from propiedades
        where tipo = 'departamento'
        group by lower(btrim(direccion)),
                 lower(coalesce(btrim(piso), '')),
                 lower(coalesce(btrim(numero), ''))
        having count(*) > 1
    ) then
        raise exception 'Hay departamentos duplicados por dirección, piso y número normalizados';
    end if;

    if exists (
        select 1
        from propiedades
        where tipo <> 'departamento'
        group by lower(btrim(direccion))
        having count(*) > 1
    ) then
        raise exception 'Hay propiedades duplicadas por dirección normalizada';
    end if;
end
$$;

drop index if exists uq_propiedades_direccion_depto;
drop index if exists uq_propiedades_direccion_no_depto;

create unique index if not exists uq_propiedades_direccion_depto_normalizada
    on propiedades (
        lower(btrim(direccion)),
        lower(coalesce(btrim(piso), '')),
        lower(coalesce(btrim(numero), ''))
    )
    where tipo = 'departamento';

create unique index if not exists uq_propiedades_direccion_no_depto_normalizada
    on propiedades (lower(btrim(direccion)))
    where tipo <> 'departamento';

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_propiedades_direccion_largo'
    ) then
        alter table propiedades add constraint chk_propiedades_direccion_largo
            check (char_length(btrim(direccion)) between 2 and 200);
    else
        alter table propiedades drop constraint chk_propiedades_direccion_largo;
        alter table propiedades add constraint chk_propiedades_direccion_largo
            check (char_length(btrim(direccion)) between 2 and 200);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_propiedades_zona_largo'
    ) then
        alter table propiedades add constraint chk_propiedades_zona_largo
            check (char_length(btrim(zona)) between 2 and 100);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_propiedades_piso_largo'
    ) then
        alter table propiedades add constraint chk_propiedades_piso_largo
            check (piso is null or char_length(btrim(piso)) between 1 and 30);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_propiedades_numero_largo'
    ) then
        alter table propiedades add constraint chk_propiedades_numero_largo
            check (numero is null or char_length(btrim(numero)) between 1 and 30);
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_propiedades_unidad_segun_tipo'
    ) then
        alter table propiedades add constraint chk_propiedades_unidad_segun_tipo
            check (tipo = 'departamento' or (piso is null and numero is null));
    end if;
end
$$;

commit;
