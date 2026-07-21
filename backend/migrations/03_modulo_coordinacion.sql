-- ============================================================
-- AARI — Módulo 3: Coordinación Agéntica
-- Tablas: presupuestos, proveedores_externos, visitas,
--         cancelaciones, sesiones_agente
-- Requiere: 01_modulo_administracion.sql y
--           02_modulo_reclamos.sql ya ejecutados
-- ============================================================

-- ------------------------------------------------------------
-- 13. presupuestos (HU19, HU20)
-- ------------------------------------------------------------
create table presupuestos (
    id              uuid primary key default gen_random_uuid(),
    reclamo_id      uuid not null references reclamos(id) on delete cascade,
    proveedor_id    uuid not null references proveedores(id),
    monto           numeric(12,2) not null check (monto > 0),
    descripcion     text,
    recibido_en     timestamptz not null default now()
);

create index idx_presupuestos_reclamo on presupuestos (reclamo_id);
create index idx_presupuestos_proveedor on presupuestos (proveedor_id);

-- Ahora que presupuestos existe, cerramos la FK pendiente de reclamos
-- (columna creada en 02_modulo_reclamos.sql como uuid suelto)
alter table reclamos
    add constraint fk_reclamos_presupuesto_seleccionado
    foreign key (presupuesto_seleccionado_id) references presupuestos(id);


-- ------------------------------------------------------------
-- 14. proveedores_externos (HU18)
-- ------------------------------------------------------------
create table proveedores_externos (
    id              uuid primary key default gen_random_uuid(),
    reclamo_id      uuid not null references reclamos(id) on delete cascade,
    propiedad_id    uuid not null references propiedades(id),
    nombre          text not null,
    telefono        text not null,
    created_at      timestamptz not null default now(),

    constraint chk_prov_externos_telefono_formato
        check (telefono ~ '^[0-9]{8,15}$')
);

create index idx_prov_externos_reclamo on proveedores_externos (reclamo_id);
create index idx_prov_externos_propiedad on proveedores_externos (propiedad_id);


-- ------------------------------------------------------------
-- 15. visitas (HU23) — coordinación de turno
-- ------------------------------------------------------------
-- Se permite más de una fila por reclamo (si hay cancelación y se
-- vuelve a coordinar); la más reciente es la vigente.
create table visitas (
    id                          uuid primary key default gen_random_uuid(),
    reclamo_id                  uuid not null references reclamos(id) on delete cascade,
    proveedor_id                uuid references proveedores(id),  -- null si es proveedor externo
    opciones_dias                date[] not null,                  -- mínimo 3 opciones propuestas
    franja_horaria_preferida    text not null check (franja_horaria_preferida in
                                    ('mañana', 'tarde', 'indistinto')),
    fecha_confirmada            date,
    horario_confirmado          text,
    estado                      text not null default 'pendiente_confirmacion'
                                    check (estado in
                                        ('pendiente_confirmacion', 'confirmada', 'realizada', 'no_confirmada', 'cancelada')),
    recordatorio_24h_enviado    boolean not null default false,
    recordatorio_2h_enviado     boolean not null default false,
    created_at                  timestamptz not null default now(),
    updated_at                  timestamptz not null default now(),

    constraint chk_visitas_min_opciones check (array_length(opciones_dias, 1) >= 3)
);

create trigger trg_visitas_updated_at
before update on visitas
for each row execute function set_updated_at();

create index idx_visitas_reclamo on visitas (reclamo_id);
create index idx_visitas_estado on visitas (estado);


-- ------------------------------------------------------------
-- 16. cancelaciones (HU24)
-- ------------------------------------------------------------
create table cancelaciones (
    id              uuid primary key default gen_random_uuid(),
    reclamo_id      uuid not null references reclamos(id) on delete cascade,
    proveedor_id    uuid references proveedores(id),  -- proveedor descartado, si aplica
    etapa           text not null check (etapa in
                        ('esperando_presupuestos', 'revisando_presupuestos', 'esperando_confirmacion_disponibilidad')),
    timestamp       timestamptz not null default now()
);

create index idx_cancelaciones_reclamo on cancelaciones (reclamo_id);

-- Trigger: si un reclamo acumula 3 o más cancelaciones, se registra
-- una notificación de alerta para el operador (HU24, último criterio)
create or replace function chk_alerta_cancelaciones()
returns trigger as $$
declare
    total_cancelaciones int;
begin
    select count(*) into total_cancelaciones
    from cancelaciones
    where reclamo_id = new.reclamo_id;

    if total_cancelaciones >= 3 then
        insert into notificaciones (reclamo_id, destinatario_tipo, destinatario_contacto, canal, mensaje)
        values (
            new.reclamo_id,
            'operador',
            'operador@sistema',  -- placeholder; el backend resuelve el contacto real
            'email',
            'El reclamo acumula 3 o más cancelaciones de coordinación. Requiere revisión manual.'
        );
    end if;

    return new;
end;
$$ language plpgsql;

create trigger trg_alerta_cancelaciones
after insert on cancelaciones
for each row execute function chk_alerta_cancelaciones();


-- ------------------------------------------------------------
-- 17. sesiones_agente (HU21) — checkpointing del grafo de LangGraph
-- ------------------------------------------------------------
create table sesiones_agente (
    id                  uuid primary key default gen_random_uuid(),
    reclamo_id          uuid not null unique references reclamos(id) on delete cascade,
    estado_grafo        jsonb not null default '{}'::jsonb,
    ultima_actividad    timestamptz not null default now(),
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create trigger trg_sesiones_agente_updated_at
before update on sesiones_agente
for each row execute function set_updated_at();

create index idx_sesiones_agente_ultima_actividad on sesiones_agente (ultima_actividad);