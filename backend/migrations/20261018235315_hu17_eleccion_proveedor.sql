-- HU17 / AARI-191. Generada con Supabase CLI 2.81.3.
-- Requiere HU16. Preparada para validación LOCAL; no aplicar sin autorización.
begin;
set local lock_timeout='5s';
set local statement_timeout='30s';

alter table public.reclamos drop constraint chk_reclamos_estado_valido;
alter table public.reclamos add constraint chk_reclamos_estado_valido check (estado in (
    'Recibido','Clasificado','Clasificación pendiente','Escalado',
    'Pendiente de respuesta del responsable','Pendiente de respuesta - vencido',
    'Autorizado','Rechazado por propietario','Pendiente de asignación',
    'Sin presupuestos recibidos','Proveedor seleccionado','En proceso','Visita programada',
    'Resuelto','Resuelto (sin confirmación)','Reabierto por disconformidad',
    'Derivado a inmobiliaria (expensa)','Derivado a proveedor externo','Sesión expirada',
    'Pendiente de autorización - vencido','Pendiente de datos de proveedor propio'
));

create table public.reclamo_elecciones_proveedor (
    id uuid primary key default gen_random_uuid(),
    reclamo_id uuid not null references public.reclamos(id) on delete restrict,
    solicitud_responsable_en timestamptz not null,
    actor_tipo text not null check (actor_tipo in ('inquilino','propietario')),
    solicitado_en timestamptz not null,
    recordatorio_programado_en timestamptz not null,
    respuesta_vence_en timestamptz not null,
    estado text not null default 'pendiente' check (estado in ('pendiente','decidida','vencida')),
    recordatorio_generado_en timestamptz,
    request_id uuid unique,
    expected_updated_at timestamptz,
    usuario_id uuid references public.usuarios(id) on delete restrict,
    actor_nombre text,
    tipo_proveedor text check (tipo_proveedor in ('fidelizado','propio')),
    decidido_en timestamptz,
    estado_resultante text,
    siguiente_paso text,
    historial_estado_id uuid references public.reclamo_historial_estados(id) on delete restrict,
    constraint uq_eleccion_solicitud unique (reclamo_id,solicitud_responsable_en),
    constraint uq_eleccion_id_reclamo unique (id,reclamo_id),
    constraint chk_eleccion_plazos check (
        solicitado_en < recordatorio_programado_en and recordatorio_programado_en < respuesta_vence_en),
    constraint chk_eleccion_decision check (
        (estado='decidida' and request_id is not null and usuario_id is not null
         and expected_updated_at is not null and actor_nombre is not null
         and decidido_en is not null and historial_estado_id is not null
         and tipo_proveedor is not null and estado_resultante is not null and siguiente_paso is not null
         and ((tipo_proveedor='fidelizado' and estado_resultante='Pendiente de asignación'
               and siguiente_paso='solicitar_presupuestos')
           or (tipo_proveedor='propio' and estado_resultante='Pendiente de datos de proveedor propio'
               and siguiente_paso='registrar_proveedor_propio')))
        or (estado<>'decidida' and request_id is null and tipo_proveedor is null
            and usuario_id is null and expected_updated_at is null and actor_nombre is null
            and decidido_en is null and estado_resultante is null and siguiente_paso is null
            and historial_estado_id is null)
    )
);
create index idx_elecciones_usuario on public.reclamo_elecciones_proveedor(usuario_id);
create index idx_elecciones_historial on public.reclamo_elecciones_proveedor(historial_estado_id);
create index idx_elecciones_vencimiento on public.reclamo_elecciones_proveedor(respuesta_vence_en,reclamo_id)
    where estado='pendiente';
create index idx_elecciones_recordatorio on public.reclamo_elecciones_proveedor(recordatorio_programado_en,reclamo_id)
    where estado='pendiente' and recordatorio_generado_en is null;
alter table public.reclamo_elecciones_proveedor enable row level security;
revoke all on public.reclamo_elecciones_proveedor from public,anon,authenticated;

alter table public.notificaciones add column solicitud_tipo_proveedor_id uuid;
alter table public.notificaciones drop constraint chk_notificaciones_estado_reclamo;
alter table public.notificaciones add constraint chk_notificaciones_estado_reclamo check (estado_reclamo in (
    'Recibido','Clasificado','Clasificación pendiente','Escalado',
    'Pendiente de respuesta del responsable','Pendiente de respuesta - vencido',
    'Autorizado','Rechazado por propietario','Pendiente de asignación',
    'Sin presupuestos recibidos','Proveedor seleccionado','En proceso','Visita programada',
    'Resuelto','Resuelto (sin confirmación)','Reabierto por disconformidad',
    'Derivado a inmobiliaria (expensa)','Derivado a proveedor externo','Sesión expirada',
    'Pendiente de autorización - vencido','Pendiente de datos de proveedor propio'
));
alter table public.notificaciones add constraint fk_notificacion_eleccion
    foreign key (solicitud_tipo_proveedor_id,reclamo_id)
    references public.reclamo_elecciones_proveedor(id,reclamo_id) on delete restrict;
create index idx_notificaciones_eleccion on public.notificaciones(solicitud_tipo_proveedor_id,reclamo_id);
alter table public.notificaciones drop constraint chk_notificaciones_tipo_evento;
alter table public.notificaciones add constraint chk_notificaciones_tipo_evento check (tipo_evento in (
    'alta_reclamo','estado_reclamo','responsable_inicial','responsable_recordatorio',
    'responsable_vencido','alerta_operador','expensa_reporte',
    'eleccion_proveedor_recordatorio','eleccion_proveedor_vencido'));

-- La apertura es atómica con la clasificación (ordinario) o autorización (extraordinario).
-- SECURITY INVOKER, sin exposición como RPC ni nuevos permisos públicos.
create function public.abrir_eleccion_proveedor() returns trigger
language plpgsql security invoker set search_path='' as $$
declare
    claim uuid;
    row_data record;
    started timestamptz;
begin
    if TG_TABLE_NAME='reclamo_responsables' then
        claim := NEW.reclamo_id;
    else
        if NEW.estado is not distinct from OLD.estado then return NEW; end if;
        claim := NEW.id;
    end if;
    select r.estado,r.tipo_gasto,rr.actor_tipo,rr.solicitado_en into row_data
    from public.reclamos r join public.reclamo_responsables rr on rr.reclamo_id=r.id
    where r.id=claim;
    if (row_data.tipo_gasto='ordinario' and row_data.actor_tipo='inquilino'
        and row_data.estado='Pendiente de respuesta del responsable') then
        started := row_data.solicitado_en;
    elsif (row_data.tipo_gasto='extraordinario' and row_data.actor_tipo='propietario'
        and row_data.estado='Autorizado') then
        started := clock_timestamp();
    else return NEW;
    end if;
    insert into public.reclamo_elecciones_proveedor
        (reclamo_id,solicitud_responsable_en,actor_tipo,solicitado_en,
         recordatorio_programado_en,respuesta_vence_en)
    values (claim,row_data.solicitado_en,row_data.actor_tipo,started,
            started+interval '48 hours',started+interval '72 hours')
    on conflict (reclamo_id,solicitud_responsable_en) do nothing;
    return NEW;
end;
$$;
revoke all on function public.abrir_eleccion_proveedor() from public,anon,authenticated;
create trigger trg_responsable_eleccion_proveedor after insert on public.reclamo_responsables
    for each row execute function public.abrir_eleccion_proveedor();
create trigger trg_autorizacion_eleccion_proveedor after update of estado on public.reclamos
    for each row execute function public.abrir_eleccion_proveedor();
-- Extender sólo el mensaje del estado nuevo, conservando la implementación
-- vigente de HU10/HU12 y sus permisos, omisión y claves de idempotencia.
do $migration$
declare
    definition text := pg_catalog.pg_get_functiondef('public.crear_notificacion_cambio_estado_reclamo()'::regprocedure);
    marker text := $needle$when 'Pendiente de asignación' then$needle$;
begin
    if pg_catalog.strpos(definition,marker)=0 then
        raise exception 'La plantilla de estados difiere de la base requerida. Revisar antes de migrar.';
    end if;
    execute pg_catalog.replace(definition,marker,
        $replacement$when 'Pendiente de datos de proveedor propio' then 'Se eligió un proveedor propio; falta registrar sus datos. El reclamo todavía no fue derivado.'
        when 'Pendiente de asignación' then$replacement$);
end;
$migration$;
revoke all on function public.crear_notificacion_cambio_estado_reclamo() from public,anon,authenticated;
-- No backfill en DDL ni cambios de estado históricos. El worker activa casos previos
-- usando la fecha original, nunca reinicia sus plazos ni escribe desde GET.
commit;
