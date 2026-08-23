-- ============================================================
-- AARI-22 — Ubicaciones con contenido descriptivo
-- Aplicar después de 09_ubicacion_propiedades.sql.
-- ============================================================

begin;

-- Se admiten nombres que incluyen números (por ejemplo, "9 de Julio" o
-- "Ruta 9"), pero cada valor debe contener al menos una letra. La migración
-- se detiene ante datos anteriores incompatibles para que puedan corregirse
-- de forma explícita, sin inventar ubicaciones.
do $$
begin
    if exists (
        select 1
        from propiedades
        where direccion !~ '[[:alpha:]]'
           or localidad !~ '[[:alpha:]]'
           or (barrio is not null and barrio !~ '[[:alpha:]]')
    ) then
        raise exception 'Hay propiedades con dirección, localidad o barrio sin letras; corregirlas antes de aplicar la migración 10';
    end if;
end
$$;

alter table propiedades
    drop constraint if exists chk_propiedades_direccion_con_letra,
    drop constraint if exists chk_propiedades_localidad_con_letra,
    drop constraint if exists chk_propiedades_barrio_con_letra;

alter table propiedades
    add constraint chk_propiedades_direccion_con_letra
        check (direccion ~ '[[:alpha:]]'),
    add constraint chk_propiedades_localidad_con_letra
        check (localidad ~ '[[:alpha:]]'),
    add constraint chk_propiedades_barrio_con_letra
        check (barrio is null or barrio ~ '[[:alpha:]]');

commit;
