-- AARI-34 — Formato válido para nombres de propietarios e inquilinos.
--
-- Esta migración normaliza espacios y se detiene si encuentra nombres que
-- contienen números o símbolos ajenos a letras, espacios, apóstrofes y guiones.
-- No corrige esos datos automáticamente porque el nombre real no puede inferirse.

begin;

update propietarios
set nombre_completo = regexp_replace(btrim(nombre_completo), '[[:space:]]+', ' ', 'g')
where nombre_completo is distinct from
      regexp_replace(btrim(nombre_completo), '[[:space:]]+', ' ', 'g');

update inquilinos
set nombre_completo = regexp_replace(btrim(nombre_completo), '[[:space:]]+', ' ', 'g')
where nombre_completo is distinct from
      regexp_replace(btrim(nombre_completo), '[[:space:]]+', ' ', 'g');

do $$
declare
    propietarios_invalidos integer;
    inquilinos_invalidos integer;
begin
    select count(*)
    into propietarios_invalidos
    from propietarios
    where char_length(btrim(nombre_completo)) not between 2 and 120
       or btrim(nombre_completo)
          !~ '^[[:alpha:]]+([- ''’][[:alpha:]]+)*$';

    select count(*)
    into inquilinos_invalidos
    from inquilinos
    where char_length(btrim(nombre_completo)) not between 2 and 120
       or btrim(nombre_completo)
          !~ '^[[:alpha:]]+([- ''’][[:alpha:]]+)*$';

    if propietarios_invalidos > 0 or inquilinos_invalidos > 0 then
        raise exception
            'Hay nombres incompatibles: % propietario(s), % inquilino(s). Corregirlos antes de repetir la migración.',
            propietarios_invalidos,
            inquilinos_invalidos;
    end if;
end $$;

alter table propietarios
    drop constraint if exists chk_propietarios_nombre_largo,
    drop constraint if exists chk_propietarios_nombre_formato;

alter table propietarios
    add constraint chk_propietarios_nombre_largo
        check (char_length(btrim(nombre_completo)) between 2 and 120),
    add constraint chk_propietarios_nombre_formato
        check (
            btrim(nombre_completo)
            ~ '^[[:alpha:]]+([- ''’][[:alpha:]]+)*$'
        );

alter table inquilinos
    drop constraint if exists chk_inquilinos_nombre_formato;

alter table inquilinos
    add constraint chk_inquilinos_nombre_formato
        check (
            btrim(nombre_completo)
            ~ '^[[:alpha:]]+([- ''’][[:alpha:]]+)*$'
        );

commit;
