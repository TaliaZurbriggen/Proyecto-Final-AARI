-- ============================================================
-- AARI — Módulo 2: Gestión de Reclamos
-- Tablas: reclamos, reclamo_fotos, reclamo_historial_estados,
--         notificaciones, notas_internas
-- Requiere: 01_modulo_administracion.sql ya ejecutado
-- ============================================================

-- ------------------------------------------------------------
-- Tipos (ENUM) para dominios pequeños y estables
-- ------------------------------------------------------------
create type urgencia_reclamo as enum ('baja', 'media', 'alta');
create type tipo_gasto_reclamo as enum ('ordinario', 'extraordinario', 'expensa');


-- ------------------------------------------------------------
-- 8. reclamos (HU8, HU9, HU12, HU14, HU16, HU20, HU23, HU25)
-- ------------------------------------------------------------
-- Nota sobre "estado": se usa TEXT + CHECK en vez de ENUM porque
-- son muchos valores (>15) y es más simple de ampliar/ajustar
-- durante el desarrollo (ALTER TABLE ... DROP/ADD CONSTRAINT)
-- que un ENUM (ALTER TYPE ADD VALUE tiene más restricciones).
create table reclamos (
    id                          uuid primary key default gen_random_uuid(),
    descripcion                 text not null,
    urgencia                    urgencia_reclamo not null,
    tipo_id                     uuid not null references especialidades(id),
    inquilino_id                uuid not null references inquilinos(id),
    propiedad_id                uuid not null references propiedades(id),

    estado                      text not null default 'Recibido',
    tipo_gasto                  tipo_gasto_reclamo,          -- null hasta clasificar
    confianza_clasificacion     numeric(5,4),                -- 0.0000 a 1.0000

    -- Se completa en el flujo de coordinación (Módulo 3);
    -- la FK a presupuestos se agrega en el script del Módulo 3
    -- porque presupuestos todavía no existe en este punto.
    presupuesto_seleccionado_id uuid,
    monto_seleccionado          numeric(12,2),
    proveedor_seleccionado_id   uuid references proveedores(id),

    fecha_visita                timestamptz,
    creado_en                   timestamptz not null default now(),
    resuelto_en                 timestamptz,
    updated_at                  timestamptz not null default now(),

    constraint chk_reclamos_descripcion_largo
        check (char_length(descripcion) between 20 and 1000),

    constraint chk_reclamos_estado_valido check (estado in (
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
    ))
);

create trigger trg_reclamos_updated_at
before update on reclamos
for each row execute function set_updated_at();

create index idx_reclamos_propiedad on reclamos (propiedad_id);
create index idx_reclamos_inquilino on reclamos (inquilino_id);
create index idx_reclamos_estado on reclamos (estado);
create index idx_reclamos_tipo_gasto on reclamos (tipo_gasto);


-- ------------------------------------------------------------
-- 9. reclamo_fotos (HU8) — hasta 3 fotos por reclamo
-- ------------------------------------------------------------
create table reclamo_fotos (
    id              uuid primary key default gen_random_uuid(),
    reclamo_id      uuid not null references reclamos(id) on delete cascade,
    url             text not null,          -- path en Supabase Storage
    formato         text not null check (formato in ('JPG', 'JPEG', 'PNG')),
    tamanio_bytes   bigint not null check (tamanio_bytes <= 5242880), -- 5 MB
    created_at      timestamptz not null default now()
);

create index idx_reclamo_fotos_reclamo on reclamo_fotos (reclamo_id);

-- Trigger: máximo 3 fotos por reclamo (no se puede expresar con CHECK simple,
-- porque es una regla que depende de contar filas relacionadas)
create or replace function chk_max_fotos_por_reclamo()
returns trigger as $$
begin
    if (select count(*) from reclamo_fotos where reclamo_id = new.reclamo_id) >= 3 then
        raise exception 'Un reclamo no puede tener más de 3 fotos adjuntas';
    end if;
    return new;
end;
$$ language plpgsql;

create trigger trg_max_fotos_por_reclamo
before insert on reclamo_fotos
for each row execute function chk_max_fotos_por_reclamo();


-- ------------------------------------------------------------
-- 10. reclamo_historial_estados (HU11, RN-04 — trazabilidad)
-- ------------------------------------------------------------
create table reclamo_historial_estados (
    id              uuid primary key default gen_random_uuid(),
    reclamo_id      uuid not null references reclamos(id) on delete cascade,
    estado_anterior text,
    estado_nuevo    text not null,
    origen          text not null check (origen in
                        ('sistema', 'agente', 'operador', 'administrador', 'inquilino', 'propietario')),
    usuario_id      uuid references usuarios(id),   -- null si el cambio lo hizo el agente/sistema
    timestamp       timestamptz not null default now()
);

create index idx_historial_reclamo on reclamo_historial_estados (reclamo_id, timestamp);

-- Trigger: cada vez que cambia el estado de un reclamo, se registra
-- automáticamente en el historial. Garantiza trazabilidad sin depender
-- de que el backend se acuerde de loguearlo manualmente.
create or replace function log_cambio_estado_reclamo()
returns trigger as $$
begin
    if new.estado is distinct from old.estado then
        insert into reclamo_historial_estados (reclamo_id, estado_anterior, estado_nuevo, origen)
        values (new.id, old.estado, new.estado, 'sistema');
    end if;
    return new;
end;
$$ language plpgsql;

create trigger trg_log_cambio_estado
after update on reclamos
for each row execute function log_cambio_estado_reclamo();


-- ------------------------------------------------------------
-- 11. notificaciones (HU10, HU12, HU14)
-- ------------------------------------------------------------
create table notificaciones (
    id                  uuid primary key default gen_random_uuid(),
    reclamo_id          uuid not null references reclamos(id) on delete cascade,
    destinatario_tipo   text not null check (destinatario_tipo in
                            ('inquilino', 'propietario', 'operador', 'administrador', 'proveedor', 'inmobiliaria')),
    destinatario_contacto text not null,        -- email o teléfono usado en el envío
    canal               text not null check (canal in ('email', 'whatsapp')),
    mensaje             text not null,
    estado_envio        text not null default 'pendiente'
                            check (estado_envio in ('pendiente', 'enviado', 'fallido')),
    intentos            int not null default 0,
    enviado_en          timestamptz,
    created_at          timestamptz not null default now()
);

create index idx_notificaciones_reclamo on notificaciones (reclamo_id);
create index idx_notificaciones_estado on notificaciones (estado_envio);


-- ------------------------------------------------------------
-- 12. notas_internas (HU14) — notas de la inmobiliaria sobre expensas
-- ------------------------------------------------------------
create table notas_internas (
    id          uuid primary key default gen_random_uuid(),
    reclamo_id  uuid not null references reclamos(id) on delete cascade,
    usuario_id  uuid not null references usuarios(id),
    contenido   text not null,
    created_at  timestamptz not null default now()
);

create index idx_notas_internas_reclamo on notas_internas (reclamo_id);