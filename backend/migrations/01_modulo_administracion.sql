-- ============================================================
-- AARI — Módulo 1: Administración
-- Tablas: usuarios, propietarios, propiedades, inquilinos,
--         proveedores, especialidades, proveedor_especialidades
-- ============================================================

-- Extensión necesaria para gen_random_uuid()
create extension if not exists "pgcrypto";

-- ------------------------------------------------------------
-- Función auxiliar: actualizar updated_at automáticamente
-- ------------------------------------------------------------
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;


-- ------------------------------------------------------------
-- 1. usuarios (HU5, HU6, HU7)
-- ------------------------------------------------------------
create type rol_usuario as enum ('administrador', 'operador', 'inquilino', 'propietario');

create table usuarios (
    id                  uuid primary key default gen_random_uuid(),
    email               text not null unique,
    password_hash       text not null,
    rol                 rol_usuario not null,
    primer_ingreso      boolean not null default true,
    intentos_fallidos   int not null default 0,
    bloqueado_hasta     timestamptz,
    activo              boolean not null default true,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create trigger trg_usuarios_updated_at
before update on usuarios
for each row execute function set_updated_at();

-- Validación básica de formato de email a nivel BD (defensa en profundidad;
-- la validación fuerte vive en el backend)
alter table usuarios
    add constraint chk_usuarios_email_formato
    check (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');


-- ------------------------------------------------------------
-- 2. propietarios (HU1)
-- ------------------------------------------------------------
create table propietarios (
    id              uuid primary key default gen_random_uuid(),
    nombre_completo text not null,
    dni             text not null unique,
    email           text not null,
    telefono        text not null,
    usuario_id      uuid references usuarios(id) on delete set null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    constraint chk_propietarios_dni_formato check (dni ~ '^[0-9]{7,8}$'),
    constraint chk_propietarios_email_formato
        check (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

create trigger trg_propietarios_updated_at
before update on propietarios
for each row execute function set_updated_at();


-- ------------------------------------------------------------
-- 3. propiedades (HU2)
-- ------------------------------------------------------------
create type tipo_propiedad as enum ('departamento', 'casa', 'local', 'otro');

create table propiedades (
    id              uuid primary key default gen_random_uuid(),
    direccion       text not null,
    zona            text not null,
    tipo            tipo_propiedad not null,
    piso            text,               -- solo aplica si tipo = 'departamento'
    numero          text,               -- solo aplica si tipo = 'departamento'
    propietario_id  uuid not null references propietarios(id) on delete restrict,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    constraint chk_propiedades_direccion_largo check (char_length(direccion) <= 200)
);

create trigger trg_propiedades_updated_at
before update on propiedades
for each row execute function set_updated_at();

-- Unicidad de dirección: si es depto, la combinación direccion+piso+numero debe ser única;
-- si no es depto, la dirección sola debe ser única.
create unique index uq_propiedades_direccion_depto
    on propiedades (direccion, piso, numero)
    where tipo = 'departamento';

create unique index uq_propiedades_direccion_no_depto
    on propiedades (direccion)
    where tipo <> 'departamento';


-- ------------------------------------------------------------
-- 4. inquilinos (HU3)
-- ------------------------------------------------------------
create type estado_inquilino as enum ('activo', 'sin_propiedad_asignada');

create table inquilinos (
    id              uuid primary key default gen_random_uuid(),
    nombre_completo text not null,
    dni             text not null unique,
    email           text not null,
    telefono        text not null,
    propiedad_id    uuid references propiedades(id) on delete set null,
    estado          estado_inquilino not null default 'activo',
    usuario_id      uuid references usuarios(id) on delete set null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    constraint chk_inquilinos_dni_formato check (dni ~ '^[0-9]{7,8}$'),
    constraint chk_inquilinos_email_formato
        check (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

create trigger trg_inquilinos_updated_at
before update on inquilinos
for each row execute function set_updated_at();

-- Regla de negocio: una propiedad solo puede tener UN inquilino activo a la vez.
-- Índice único parcial: solo restringe filas donde estado = 'activo'.
create unique index uq_inquilinos_propiedad_activa
    on inquilinos (propiedad_id)
    where estado = 'activo';


-- ------------------------------------------------------------
-- 5. proveedores (HU4)
-- ------------------------------------------------------------
create table proveedores (
    id                      uuid primary key default gen_random_uuid(),
    nombre_razon_social     text not null,
    matricula               text,               -- opcional, según especialidad
    telefono                text not null unique,
    zona_cobertura          text not null,
    activo                  boolean not null default true,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),

    constraint chk_proveedores_zona_largo check (char_length(zona_cobertura) <= 100)
);

create trigger trg_proveedores_updated_at
before update on proveedores
for each row execute function set_updated_at();


-- ------------------------------------------------------------
-- 6. especialidades (HU4) — catálogo predefinido + personalizadas
-- ------------------------------------------------------------
create table especialidades (
    id      uuid primary key default gen_random_uuid(),
    nombre  text not null unique
);

insert into especialidades (nombre) values
    ('plomería'),
    ('gasista'),
    ('electricidad'),
    ('cerrajería'),
    ('pintura'),
    ('albañilería'),
    ('otros');


-- ------------------------------------------------------------
-- 7. proveedor_especialidades (tabla puente M:N)
-- ------------------------------------------------------------
create table proveedor_especialidades (
    proveedor_id    uuid not null references proveedores(id) on delete cascade,
    especialidad_id uuid not null references especialidades(id) on delete cascade,
    primary key (proveedor_id, especialidad_id)
);


-- ------------------------------------------------------------
-- Índices adicionales para búsquedas frecuentes
-- ------------------------------------------------------------
create index idx_propiedades_propietario on propiedades (propietario_id);
create index idx_inquilinos_propiedad on inquilinos (propiedad_id);
create index idx_proveedores_zona on proveedores (zona_cobertura);
create index idx_proveedores_activo on proveedores (activo);