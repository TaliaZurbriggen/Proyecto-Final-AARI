-- ============================================================
-- HU10 / AARI-116 — Corrección de alertas por cancelaciones
-- Requiere: migración 21 aplicada
-- Redefine la función histórica sin modificar migraciones aplicadas.
-- ============================================================

begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

-- La migración 21 volvió obligatorios asunto y estado_reclamo, y agregó
-- proximo_intento_en a la bandeja de salida. La función original de la
-- migración 03 no completaba esos campos y hacía fallar la tercera
-- cancelación junto con su alerta.
create or replace function public.chk_alerta_cancelaciones()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_total_cancelaciones integer;
    v_estado_reclamo text;
    v_numero bigint;
begin
    select pg_catalog.count(*)
    into v_total_cancelaciones
    from public.cancelaciones
    where reclamo_id = new.reclamo_id;

    if v_total_cancelaciones >= 3 then
        select r.estado, r.numero
        into v_estado_reclamo, v_numero
        from public.reclamos as r
        where r.id = new.reclamo_id;

        if not found then
            return new;
        end if;

        insert into public.notificaciones (
            reclamo_id,
            destinatario_tipo,
            destinatario_contacto,
            canal,
            asunto,
            mensaje,
            estado_reclamo,
            estado_envio,
            proximo_intento_en
        ) values (
            new.reclamo_id,
            'operador',
            'operador@sistema',
            'email',
            pg_catalog.format(
                'AARI - Reclamo #%s con cancelaciones reiteradas',
                pg_catalog.lpad(v_numero::text, 6, '0')
            ),
            'El reclamo acumula 3 o más cancelaciones de coordinación. Requiere revisión manual.',
            v_estado_reclamo,
            'pendiente',
            now()
        );
    end if;

    return new;
end;
$$;

revoke all on function public.chk_alerta_cancelaciones()
    from public, anon, authenticated;

commit;
