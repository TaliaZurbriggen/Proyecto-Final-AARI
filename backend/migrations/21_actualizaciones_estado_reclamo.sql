-- ============================================================
-- HU10 / AARI-116 — Actualizaciones del estado del reclamo
-- Requiere: migraciones 01 a 19 aplicadas
-- Generada con Supabase CLI y adaptada a la numeración del repositorio.
-- No ejecutar sin validar primero el proyecto y el entorno destino.
-- ============================================================

begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

-- Por ahora todas las personas conservan email como preferencia. WhatsApp
-- queda modelado detrás de un puerto desacoplado hasta su integración real.
alter table public.inquilinos
    add column if not exists canal_notificacion text not null default 'email';

alter table public.inquilinos
    drop constraint if exists chk_inquilinos_canal_notificacion;
alter table public.inquilinos
    add constraint chk_inquilinos_canal_notificacion
    check (canal_notificacion in ('email', 'whatsapp'));

-- La bandeja de salida persiste el mensaje exacto, la transición que lo
-- originó y las fechas necesarias para reintentos seguros.
alter table public.notificaciones
    add column if not exists asunto text,
    add column if not exists estado_reclamo text,
    add column if not exists historial_estado_id uuid,
    add column if not exists proximo_intento_en timestamptz,
    add column if not exists bloqueado_hasta timestamptz;

update public.notificaciones as n
set asunto = coalesce(
        n.asunto,
        pg_catalog.format(
            'AARI - Reclamo #%s actualizado',
            pg_catalog.lpad(r.numero::text, 6, '0')
        )
    ),
    estado_reclamo = coalesce(n.estado_reclamo, r.estado),
    proximo_intento_en = case
        when n.estado_envio = 'pendiente'
            then coalesce(n.proximo_intento_en, n.updated_at, n.created_at, now())
        else n.proximo_intento_en
    end
from public.reclamos as r
where r.id = n.reclamo_id
  and (
      n.asunto is null
      or n.estado_reclamo is null
      or (n.estado_envio = 'pendiente' and n.proximo_intento_en is null)
  );

alter table public.notificaciones
    alter column asunto set not null,
    alter column estado_reclamo set not null;

do $$
begin
    if not exists (
        select 1
        from pg_catalog.pg_constraint
        where conname = 'fk_notificaciones_historial_estado'
          and conrelid = 'public.notificaciones'::regclass
    ) then
        alter table public.notificaciones
            add constraint fk_notificaciones_historial_estado
            foreign key (historial_estado_id)
            references public.reclamo_historial_estados(id)
            on delete cascade;
    end if;
end;
$$;

do $$
begin
    if exists (
        select 1
        from public.notificaciones
        where intentos < 0 or intentos > 3
    ) then
        raise exception using
            errcode = '23514',
            message = 'Existen notificaciones con una cantidad de intentos fuera del rango 0..3.',
            hint = 'Revisar esos registros antes de volver a ejecutar la migración 21.';
    end if;
end;
$$;

alter table public.notificaciones
    drop constraint if exists notificaciones_estado_envio_check;
alter table public.notificaciones
    drop constraint if exists chk_notificaciones_estado_envio;
alter table public.notificaciones
    add constraint chk_notificaciones_estado_envio
    check (estado_envio in ('pendiente', 'procesando', 'enviado', 'fallido'));

alter table public.notificaciones
    drop constraint if exists chk_notificaciones_intentos;
alter table public.notificaciones
    add constraint chk_notificaciones_intentos
    check (intentos between 0 and 3);

alter table public.notificaciones
    drop constraint if exists chk_notificaciones_estado_reclamo;
alter table public.notificaciones
    add constraint chk_notificaciones_estado_reclamo
    check (estado_reclamo in (
        'Recibido',
        'Clasificado',
        'Clasificación pendiente',
        'Escalado',
        'Pendiente de respuesta del responsable',
        'Pendiente de respuesta - vencido',
        'Autorizado',
        'Rechazado por propietario',
        'Pendiente de asignación',
        'Sin presupuestos recibidos',
        'Proveedor seleccionado',
        'En proceso',
        'Visita programada',
        'Resuelto',
        'Resuelto (sin confirmación)',
        'Reabierto por disconformidad',
        'Derivado a inmobiliaria (expensa)',
        'Derivado a proveedor externo',
        'Sesión expirada',
        'Pendiente de autorización - vencido'
    ));

create index if not exists idx_notificaciones_historial_estado
    on public.notificaciones (historial_estado_id)
    where historial_estado_id is not null;

create unique index if not exists uq_notificaciones_cambio_inquilino
    on public.notificaciones (historial_estado_id, destinatario_tipo)
    where historial_estado_id is not null;

create index if not exists idx_notificaciones_entrega_pendiente
    on public.notificaciones (proximo_intento_en, created_at)
    where estado_envio in ('pendiente', 'procesando') and intentos < 3;

-- Registra quién originó cada transición cuando el backend define el contexto
-- transaccional. Si no existe contexto, conserva el origen seguro 'sistema'.
create or replace function public.log_cambio_estado_reclamo()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_origen text;
    v_usuario_texto text;
    v_usuario_id uuid;
begin
    if new.estado is distinct from old.estado then
        v_origen := nullif(
            pg_catalog.current_setting('app.origen_reclamo', true),
            ''
        );
        if v_origen is null or v_origen not in (
            'sistema', 'agente', 'operador', 'administrador',
            'inquilino', 'propietario'
        ) then
            v_origen := 'sistema';
        end if;

        v_usuario_texto := nullif(
            pg_catalog.current_setting('app.usuario_reclamo', true),
            ''
        );
        if v_usuario_texto is not null then
            begin
                v_usuario_id := v_usuario_texto::uuid;
            exception
                when invalid_text_representation then
                    v_usuario_id := null;
            end;
        end if;

        insert into public.reclamo_historial_estados (
            reclamo_id,
            estado_anterior,
            estado_nuevo,
            origen,
            usuario_id
        ) values (
            new.id,
            old.estado,
            new.estado,
            v_origen,
            v_usuario_id
        );
    end if;
    return new;
end;
$$;

revoke all on function public.log_cambio_estado_reclamo()
    from public, anon, authenticated;

-- Cada cambio real genera una sola notificación durable para el inquilino.
-- El alta inicial ya crea su propia confirmación y no debe duplicarse.
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

drop trigger if exists trg_notificar_cambio_estado_reclamo
    on public.reclamo_historial_estados;
create trigger trg_notificar_cambio_estado_reclamo
after insert on public.reclamo_historial_estados
for each row
when (new.estado_anterior is not null)
execute function public.crear_notificacion_cambio_estado_reclamo();

alter table public.reclamo_historial_estados enable row level security;
alter table public.notificaciones enable row level security;
revoke all on table public.reclamo_historial_estados from anon, authenticated;
revoke all on table public.notificaciones from anon, authenticated;

commit;
