-- ============================================================
-- AARI — Persistencia del resultado del agente clasificador
-- Requiere: 01_modulo_administracion.sql y 02_modulo_reclamos.sql
-- ============================================================

-- Se agregan campos de explicabilidad sin alterar migraciones históricas.
alter table reclamos
    add column fundamento_clasificacion text,
    add column motivo_escalado text,
    add column origen_clasificacion text,
    add column clasificado_en timestamptz,
    add constraint chk_reclamos_motivo_escalado
        check (motivo_escalado is null or motivo_escalado in (
            'respuesta_modelo_invalida',
            'riesgo_seguridad',
            'multiples_rubros',
            'causa_no_identificable',
            'confianza_insuficiente'
        )),
    add constraint chk_reclamos_origen_clasificacion
        check (origen_clasificacion is null or origen_clasificacion in (
            'agente', 'operador', 'administrador'
        ));

-- El backend define app.origen_reclamo dentro de la transacción. Sin esa
-- configuración, el trigger conserva el comportamiento histórico: sistema.
create or replace function log_cambio_estado_reclamo()
returns trigger as $$
declare
    origen_evento text := coalesce(current_setting('app.origen_reclamo', true), 'sistema');
begin
    if origen_evento not in ('sistema', 'agente', 'operador', 'administrador', 'inquilino', 'propietario') then
        origen_evento := 'sistema';
    end if;

    if new.estado is distinct from old.estado then
        insert into reclamo_historial_estados (reclamo_id, estado_anterior, estado_nuevo, origen)
        values (new.id, old.estado, new.estado, origen_evento);
    end if;
    return new;
end;
$$ language plpgsql;
