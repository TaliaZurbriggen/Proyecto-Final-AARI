-- HU19: sólo bandeja privada de transporte. No crea presupuestos ni cambia reclamos.
-- Pendiente de autorización para aplicar en Supabase; no repetir al hacer pull.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';

create table public.whatsapp_eventos_entrada (
    id uuid primary key default gen_random_uuid(),
    waba_id text not null check (waba_id ~ '^[0-9]{1,32}$'),
    telefono_id text not null check (telefono_id ~ '^[0-9]{1,32}$'),
    clave_evento text not null check (clave_evento ~ '^[0-9a-f]{64}$'),
    mensaje_externo_id text not null check (length(mensaje_externo_id) between 1 and 512),
    tipo_evento text not null check (tipo_evento in ('mensaje','estado')),
    subtipo text not null check (length(subtipo) between 1 and 64),
    participante text not null check (participante ~ '^[1-9][0-9]{5,14}$'),
    ocurrido_en timestamptz not null,
    recibido_en timestamptz not null default clock_timestamp(),
    datos jsonb not null check (jsonb_typeof(datos)='object'),
    estado text not null default 'pendiente' check (estado in ('pendiente','no_soportado')),
    unique (waba_id,telefono_id,clave_evento)
);
create index idx_whatsapp_entrada_pendientes
    on public.whatsapp_eventos_entrada (recibido_en,id) where estado='pendiente';
create index idx_whatsapp_entrada_mensaje
    on public.whatsapp_eventos_entrada (waba_id,telefono_id,mensaje_externo_id);
alter table public.whatsapp_eventos_entrada enable row level security;
revoke all on table public.whatsapp_eventos_entrada from public, anon, authenticated;
commit;
