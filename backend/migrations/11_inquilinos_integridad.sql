-- AARI-34 — Integridad del padrón de inquilinos.
-- Complementa instalaciones que ya ejecutaron el módulo 1.

update inquilinos
set nombre_completo = regexp_replace(btrim(nombre_completo), '\s+', ' ', 'g'),
    dni = btrim(dni),
    email = lower(btrim(email)),
    telefono = regexp_replace(btrim(telefono), '\s+', ' ', 'g'),
    estado = case
        when propiedad_id is null then 'sin_propiedad_asignada'::estado_inquilino
        else 'activo'::estado_inquilino
    end;

do $$
begin
    if exists (
        select lower(email)
        from inquilinos
        group by lower(email)
        having count(*) > 1
    ) then
        raise exception
            'No se puede crear el índice único: existen emails de inquilinos duplicados.';
    end if;
end $$;

create unique index if not exists uq_inquilinos_email_normalizado
    on inquilinos (lower(email));

alter table inquilinos
    drop constraint if exists chk_inquilinos_nombre_largo,
    drop constraint if exists chk_inquilinos_telefono_largo,
    drop constraint if exists chk_inquilinos_estado_propiedad;

alter table inquilinos
    add constraint chk_inquilinos_nombre_largo
        check (char_length(btrim(nombre_completo)) between 2 and 120) not valid,
    add constraint chk_inquilinos_telefono_largo
        check (char_length(btrim(telefono)) between 6 and 30) not valid,
    add constraint chk_inquilinos_estado_propiedad check (
        (propiedad_id is not null and estado = 'activo')
        or
        (propiedad_id is null and estado = 'sin_propiedad_asignada')
    ) not valid;

alter table inquilinos
    validate constraint chk_inquilinos_nombre_largo,
    validate constraint chk_inquilinos_telefono_largo,
    validate constraint chk_inquilinos_estado_propiedad;
