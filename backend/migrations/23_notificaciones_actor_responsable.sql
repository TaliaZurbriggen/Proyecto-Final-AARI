-- ============================================================
-- HU12 / AARI-135 — Notificación al actor responsable
-- Requiere: migraciones 01 a 22 aplicadas
-- La CLI de Supabase no estaba disponible en el entorno local; este archivo
-- sigue la numeración incremental existente y debe registrarse al aplicarlo.
-- ============================================================

begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.propietarios
    add column if not exists canal_notificacion text not null default 'email';

alter table public.propietarios
    drop constraint if exists chk_propietarios_canal_notificacion;
alter table public.propietarios
    add constraint chk_propietarios_canal_notificacion
    check (canal_notificacion in ('email', 'whatsapp'));

alter table public.notificaciones
    add column if not exists tipo_evento text,
    add column if not exists clave_idempotencia text;

update public.notificaciones
set tipo_evento = case
    when historial_estado_id is not null then 'estado_reclamo'
    when estado_reclamo = 'Recibido' and destinatario_tipo = 'inquilino'
        then 'alta_reclamo'
    when destinatario_tipo in ('operador', 'administrador')
        then 'alerta_operador'
    else 'estado_reclamo'
end
where tipo_evento is null;

alter table public.notificaciones
    alter column tipo_evento set default 'estado_reclamo',
    alter column tipo_evento set not null;

alter table public.notificaciones
    drop constraint if exists chk_notificaciones_tipo_evento;
alter table public.notificaciones
    add constraint chk_notificaciones_tipo_evento
    check (tipo_evento in (
        'alta_reclamo',
        'estado_reclamo',
        'responsable_inicial',
        'responsable_recordatorio',
        'responsable_vencido',
        'alerta_operador'
    ));

create unique index if not exists uq_notificaciones_clave_idempotencia
    on public.notificaciones (clave_idempotencia)
    where clave_idempotencia is not null;

create table public.reclamo_responsables (
    reclamo_id uuid primary key
        references public.reclamos(id) on delete cascade,
    actor_tipo text not null
        check (actor_tipo in ('inquilino', 'propietario', 'inmobiliaria')),
    destinatario_contacto text,
    canal text check (canal is null or canal in ('email', 'whatsapp')),
    contacto_error text,
    solicitado_en timestamptz not null default now(),
    recordatorio_programado_en timestamptz not null,
    respuesta_vence_en timestamptz not null,
    recordatorio_generado_en timestamptz,
    escalado_en timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_reclamo_responsables_contacto check (
        (
            destinatario_contacto is not null
            and canal is not null
            and contacto_error is null
        ) or (
            destinatario_contacto is null
            and canal is null
            and contacto_error is not null
        )
    ),
    constraint chk_reclamo_responsables_plazos check (
        recordatorio_programado_en > solicitado_en
        and respuesta_vence_en > recordatorio_programado_en
    )
);

drop trigger if exists trg_reclamo_responsables_updated_at
    on public.reclamo_responsables;
create trigger trg_reclamo_responsables_updated_at
before update on public.reclamo_responsables
for each row execute function public.set_updated_at();

create index idx_reclamo_responsables_recordatorio_pendiente
    on public.reclamo_responsables (recordatorio_programado_en, reclamo_id)
    where recordatorio_generado_en is null and escalado_en is null;

create index idx_reclamo_responsables_vencimiento_pendiente
    on public.reclamo_responsables (respuesta_vence_en, reclamo_id)
    where escalado_en is null;

alter table public.reclamo_responsables enable row level security;
revoke all on table public.reclamo_responsables from anon, authenticated;

-- HU12 puede consolidar la actualización genérica y el pedido de acción cuando
-- ambos mensajes tendrían al mismo inquilino como destinatario. La omisión es
-- local a la transacción y solo se activa desde el backend.
create or replace function public.crear_notificacion_cambio_estado_reclamo()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_numero bigint;
    v_nombre text;
    v_email text;
    v_telefono text;
    v_canal text;
    v_contacto text;
    v_detalle text;
begin
    if coalesce(
        pg_catalog.current_setting(
            'app.omitir_notificacion_inquilino',
            true
        ),
        'false'
    ) = 'true' then
        return new;
    end if;

    select r.numero,
           i.nombre_completo,
           i.email,
           i.telefono,
           i.canal_notificacion
    into v_numero, v_nombre, v_email, v_telefono, v_canal
    from public.reclamos as r
    join public.inquilinos as i on i.id = r.inquilino_id
    where r.id = new.reclamo_id;

    if not found then
        return new;
    end if;

    v_contacto := case
        when v_canal = 'whatsapp' then v_telefono
        else v_email
    end;

    v_detalle := case new.estado_nuevo
        when 'Clasificado' then 'El reclamo fue clasificado y continuará con el circuito correspondiente.'
        when 'Clasificación pendiente' then 'La clasificación necesita información o procesamiento adicional.'
        when 'Escalado' then 'El reclamo requiere revisión manual de la inmobiliaria.'
        when 'Pendiente de respuesta del responsable' then 'Estamos esperando la respuesta de la persona responsable.'
        when 'Pendiente de respuesta - vencido' then 'El plazo de respuesta venció y la inmobiliaria debe intervenir.'
        when 'Autorizado' then 'La intervención solicitada fue autorizada.'
        when 'Rechazado por propietario' then 'El propietario rechazó la intervención solicitada.'
        when 'Pendiente de asignación' then 'El reclamo está listo para asignar un proveedor.'
        when 'Sin presupuestos recibidos' then 'Todavía no se recibieron presupuestos para continuar.'
        when 'Proveedor seleccionado' then 'Ya se seleccionó el proveedor que atenderá el reclamo.'
        when 'En proceso' then 'El proveedor comenzó a trabajar en la resolución.'
        when 'Visita programada' then 'Se programó una visita para atender el reclamo.'
        when 'Resuelto' then 'El reclamo fue marcado como resuelto.'
        when 'Resuelto (sin confirmación)' then 'El reclamo se cerró sin una confirmación dentro del plazo previsto.'
        when 'Reabierto por disconformidad' then 'El reclamo fue reabierto por disconformidad con la resolución.'
        when 'Derivado a inmobiliaria (expensa)' then 'El reclamo fue derivado a la inmobiliaria para su tratamiento como expensa.'
        when 'Derivado a proveedor externo' then 'El reclamo fue derivado a un proveedor externo.'
        when 'Sesión expirada' then 'La gestión anterior expiró y requiere una nueva intervención.'
        when 'Pendiente de autorización - vencido' then 'El plazo de autorización venció y la inmobiliaria debe intervenir.'
        else 'El reclamo registró una actualización.'
    end;

    insert into public.notificaciones (
        reclamo_id,
        destinatario_tipo,
        destinatario_contacto,
        canal,
        asunto,
        mensaje,
        estado_reclamo,
        historial_estado_id,
        tipo_evento,
        clave_idempotencia,
        estado_envio,
        proximo_intento_en
    ) values (
        new.reclamo_id,
        'inquilino',
        v_contacto,
        v_canal,
        pg_catalog.format(
            'AARI - Reclamo #%s actualizado',
            pg_catalog.lpad(v_numero::text, 6, '0')
        ),
        pg_catalog.format(
            E'Hola %s,\n\nEl estado de tu reclamo AARI #%s cambió de "%s" a "%s".\n%s\n\nPodés seguir su evolución desde AARI.',
            v_nombre,
            pg_catalog.lpad(v_numero::text, 6, '0'),
            new.estado_anterior,
            new.estado_nuevo,
            v_detalle
        ),
        new.estado_nuevo,
        new.id,
        'estado_reclamo',
        pg_catalog.format('%s:estado:%s', new.reclamo_id, new.id),
        'pendiente',
        now()
    )
    on conflict (historial_estado_id, destinatario_tipo)
    where historial_estado_id is not null
    do nothing;

    return new;
end;
$$;

revoke all on function public.crear_notificacion_cambio_estado_reclamo()
    from public, anon, authenticated;

-- La migración 22 es anterior a tipo_evento/clave_idempotencia. Se redefine
-- la función sin tocar su trigger para que las alertas futuras conserven su
-- semántica y no se dupliquen si la misma cancelación se procesa otra vez.
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
            tipo_evento,
            clave_idempotencia,
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
            'alerta_operador',
            pg_catalog.format(
                '%s:cancelacion:%s',
                new.reclamo_id,
                new.id
            ),
            'pendiente',
            now()
        )
        on conflict (clave_idempotencia)
        where clave_idempotencia is not null
        do nothing;
    end if;

    return new;
end;
$$;

revoke all on function public.chk_alerta_cancelaciones()
    from public, anon, authenticated;

commit;
