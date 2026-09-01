-- ============================================================
-- AARI-46 — Finalización de la cobertura estructurada
-- Fase 2: ejecutar después de revisar los proveedores existentes.
-- ============================================================

begin;

-- No se elimina la referencia anterior mientras exista un proveedor sin al
-- menos una cobertura estructurada. La excepción revierte esta fase sin
-- eliminar datos y permite completarlos antes de volver a ejecutarla.
do $$
declare
    proveedores_sin_cobertura bigint;
    coberturas_parciales_sin_barrios bigint;
begin
    select count(*)
    into proveedores_sin_cobertura
    from proveedores p
    where not exists (
        select 1
        from proveedor_coberturas pc
        where pc.proveedor_id = p.id
    );

    if proveedores_sin_cobertura > 0 then
        raise exception using
            message = format(
                'AARI-46 no puede eliminar zona_cobertura: %s proveedor(es) no tienen cobertura estructurada.',
                proveedores_sin_cobertura
            );
    end if;

    select count(*)
    into coberturas_parciales_sin_barrios
    from proveedor_coberturas pc
    where not pc.cubre_toda_localidad
      and not exists (
          select 1
          from proveedor_cobertura_barrios pcb
          where pcb.cobertura_id = pc.id
      );

    if coberturas_parciales_sin_barrios > 0 then
        raise exception using
            message = format(
                'AARI-46 no puede finalizar: %s cobertura(s) parciales no tienen barrios.',
                coberturas_parciales_sin_barrios
            );
    end if;
end
$$;

drop index if exists idx_proveedores_zona;

alter table proveedores
    drop constraint if exists chk_proveedores_zona_largo,
    drop column if exists zona_cobertura;

commit;
