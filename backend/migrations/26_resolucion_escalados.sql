-- HU13 / AARI-147. Aditiva; requiere HU10/HU12 (21/23 responsable).
-- 24 y 25 están reservadas por HU30. No renumerar migraciones ya aplicadas.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';

create table public.reclamo_decisiones_clasificacion (
    id uuid primary key default gen_random_uuid(),
    reclamo_id uuid not null references public.reclamos(id) on delete cascade,
    historial_estado_id uuid not null unique references public.reclamo_historial_estados(id),
    usuario_id uuid not null references public.usuarios(id),
    usuario_nombre text not null,
    rol text not null check (rol in ('operador', 'administrador')),
    decidido_en timestamptz not null default now(),
    tipo_gasto public.tipo_gasto_reclamo not null,
    fundamento text not null check (
        char_length(fundamento) between 10 and 1000 and fundamento = btrim(fundamento)
    ),
    resultado_anterior jsonb not null check (jsonb_typeof(resultado_anterior) = 'object')
);
create index idx_decisiones_clasificacion_reclamo
    on public.reclamo_decisiones_clasificacion (reclamo_id, decidido_en, id);
create index idx_reclamos_cola_clasificacion
    on public.reclamos (creado_en, id)
    where estado in ('Escalado', 'Clasificación pendiente') and tipo_gasto is null;
alter table public.reclamo_decisiones_clasificacion enable row level security;
revoke all on table public.reclamo_decisiones_clasificacion from anon, authenticated;

-- Se encola después de registrar el estado. No se envía SMTP desde PostgreSQL,
-- no se agregan avisos retroactivos y no se cambia la asignación de operadores.
create or replace function public.notificar_clasificacion_pendiente()
returns trigger language plpgsql security invoker set search_path = '' as $$
declare
    v_reclamo record;
    v_destinatario record;
begin
    if new.estado_nuevo not in ('Escalado', 'Clasificación pendiente')
       or new.estado_anterior in ('Escalado', 'Clasificación pendiente') then
        return new;
    end if;
    select id, numero, tipo_gasto, operador_asignado_id into v_reclamo
    from public.reclamos where id = new.reclamo_id;
    if not found or v_reclamo.tipo_gasto is not null or exists (
        select 1 from public.reclamo_responsables where reclamo_id = new.reclamo_id
    ) then
        return new;
    end if;
    select id, email, rol::text as rol into v_destinatario
    from public.usuarios
    where activo and rol in ('operador', 'administrador')
    order by case
        when id = v_reclamo.operador_asignado_id and rol = 'operador' then 0
        when rol = 'operador' then 1 else 2 end, created_at, id
    limit 1;
    if not found then
        return new;
    end if;
    insert into public.notificaciones (
        reclamo_id, destinatario_tipo, destinatario_contacto, canal,
        asunto, mensaje, estado_reclamo, historial_estado_id, tipo_evento,
        clave_idempotencia, estado_envio, proximo_intento_en
    ) values (
        new.reclamo_id, v_destinatario.rol, v_destinatario.email, 'email',
        pg_catalog.format('AARI - Reclamo #%s requiere clasificación manual',
            pg_catalog.lpad(v_reclamo.numero::text, 6, '0')),
        'Hay un reclamo pendiente de clasificación. Revisalo desde Casos escalados en AARI.',
        new.estado_nuevo, new.id, 'alerta_operador',
        pg_catalog.format('%s:clasificacion_pendiente:%s', new.reclamo_id, new.id),
        'pendiente', now()
    ) on conflict (clave_idempotencia) where clave_idempotencia is not null do nothing;
    return new;
end;
$$;
revoke all on function public.notificar_clasificacion_pendiente() from public, anon, authenticated;
create trigger trg_notificar_clasificacion_pendiente
after insert on public.reclamo_historial_estados
for each row execute function public.notificar_clasificacion_pendiente();
commit;
