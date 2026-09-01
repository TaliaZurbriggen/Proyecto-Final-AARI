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

    constraint chk_propietarios_nombre_largo
        check (char_length(btrim(nombre_completo)) between 2 and 120),
    constraint chk_propietarios_nombre_formato
        check (
            btrim(nombre_completo)
            ~ '^[[:alpha:]]+([- ''’][[:alpha:]]+)*$'
        ),
    constraint chk_propietarios_dni_formato check (dni ~ '^[0-9]{7,8}$'),
    constraint chk_propietarios_email_formato
        check (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

create trigger trg_propietarios_updated_at
before update on propietarios
for each row execute function set_updated_at();

-- El email se utilizará como identidad de acceso en HU6. La normalización en
-- backend y este índice evitan duplicados que solo difieran por mayúsculas.
create unique index uq_propietarios_email_normalizado
    on propietarios (lower(email));


-- ------------------------------------------------------------
-- 3. propiedades (HU2)
-- ------------------------------------------------------------
create type tipo_propiedad as enum ('departamento', 'casa', 'local', 'otro');

create table propiedades (
    id              uuid primary key default gen_random_uuid(),
    direccion       text not null,
    provincia       text not null,
    localidad       text not null,
    barrio          text,
    tipo            tipo_propiedad not null,
    piso            integer,            -- 0 representa planta baja
    numero          text,               -- solo aplica si tipo = 'departamento'
    propietario_id  uuid not null references propietarios(id) on delete restrict,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    constraint chk_propiedades_direccion_largo
        check (char_length(btrim(direccion)) between 2 and 200),
    constraint chk_propiedades_direccion_con_letra
        check (direccion ~ '[[:alpha:]]'),
    constraint chk_propiedades_provincia_largo
        check (char_length(btrim(provincia)) between 2 and 100),
    constraint chk_propiedades_provincia_valida
        check (provincia in (
            'Buenos Aires', 'Ciudad Autónoma de Buenos Aires', 'Catamarca',
            'Chaco', 'Chubut', 'Córdoba', 'Corrientes', 'Entre Ríos',
            'Formosa', 'Jujuy', 'La Pampa', 'La Rioja', 'Mendoza',
            'Misiones', 'Neuquén', 'Río Negro', 'Salta', 'San Juan',
            'San Luis', 'Santa Cruz', 'Santa Fe', 'Santiago del Estero',
            'Tierra del Fuego, Antártida e Islas del Atlántico Sur',
            'Tucumán'
        )),
    constraint chk_propiedades_localidad_largo
        check (char_length(btrim(localidad)) between 2 and 100),
    constraint chk_propiedades_localidad_con_letra
        check (localidad ~ '[[:alpha:]]'),
    constraint chk_propiedades_barrio_largo
        check (barrio is null or char_length(btrim(barrio)) between 2 and 100),
    constraint chk_propiedades_barrio_con_letra
        check (barrio is null or barrio ~ '[[:alpha:]]'),
    constraint chk_propiedades_numero_largo
        check (numero is null or char_length(btrim(numero)) between 1 and 30),
    constraint chk_propiedades_unidad_segun_tipo
        check (tipo = 'departamento' or (piso is null and numero is null))
);

create trigger trg_propiedades_updated_at
before update on propiedades
for each row execute function set_updated_at();

-- La identidad geográfica incluye provincia y localidad. Para departamentos
-- también se consideran piso y número de unidad.
create unique index uq_propiedades_direccion_depto_normalizada
    on propiedades (
        lower(btrim(provincia)),
        lower(btrim(localidad)),
        lower(btrim(direccion)),
        coalesce(piso, -2147483648),
        lower(coalesce(btrim(numero), ''))
    )
    where tipo = 'departamento';

create unique index uq_propiedades_direccion_no_depto_normalizada
    on propiedades (
        lower(btrim(provincia)),
        lower(btrim(localidad)),
        lower(btrim(direccion))
    )
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

    constraint chk_inquilinos_nombre_largo
        check (char_length(btrim(nombre_completo)) between 2 and 120),
    constraint chk_inquilinos_nombre_formato
        check (
            btrim(nombre_completo)
            ~ '^[[:alpha:]]+([- ''’][[:alpha:]]+)*$'
        ),
    constraint chk_inquilinos_dni_formato check (dni ~ '^[0-9]{7,8}$'),
    constraint chk_inquilinos_email_formato
        check (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    constraint chk_inquilinos_telefono_largo
        check (char_length(btrim(telefono)) between 6 and 30),
    constraint chk_inquilinos_estado_propiedad check (
        (propiedad_id is not null and estado = 'activo')
        or
        (propiedad_id is null and estado = 'sin_propiedad_asignada')
    )
);

create trigger trg_inquilinos_updated_at
before update on inquilinos
for each row execute function set_updated_at();

-- Regla de negocio: una propiedad solo puede tener UN inquilino activo a la vez.
-- Índice único parcial: solo restringe filas donde estado = 'activo'.
create unique index uq_inquilinos_propiedad_activa
    on inquilinos (propiedad_id)
    where estado = 'activo';

-- El email será la identidad de acceso del inquilino en HU7.
create unique index uq_inquilinos_email_normalizado
    on inquilinos (lower(email));


-- ------------------------------------------------------------
-- 5. proveedores (HU4)
-- ------------------------------------------------------------
create table proveedores (
    id                      uuid primary key default gen_random_uuid(),
    nombre_razon_social     text not null,
    matricula               text,               -- opcional, según especialidad
    telefono                text not null unique,
    activo                  boolean not null default true,
    hora_inicio             time,
    hora_fin                time,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),

    constraint chk_proveedores_nombre_largo
        check (char_length(btrim(nombre_razon_social)) between 2 and 150),
    constraint chk_proveedores_nombre_con_letra
        check (nombre_razon_social ~ '[[:alpha:]]'),
    constraint chk_proveedores_matricula_largo
        check (matricula is null or char_length(btrim(matricula)) between 1 and 80),
    constraint chk_proveedores_telefono_whatsapp
        check (telefono ~ '^\+[0-9]{8,15}$'),
    constraint chk_proveedores_horario_completo
        check ((hora_inicio is null) = (hora_fin is null)),
    constraint chk_proveedores_horario_orden
        check (hora_inicio is null or hora_fin > hora_inicio)
);

create trigger trg_proveedores_updated_at
before update on proveedores
for each row execute function set_updated_at();


-- ------------------------------------------------------------
-- 5.a. proveedor_coberturas — localidades atendidas
-- ------------------------------------------------------------
create table proveedor_coberturas (
    id                      uuid primary key default gen_random_uuid(),
    proveedor_id            uuid not null references proveedores(id) on delete cascade,
    provincia               text not null,
    localidad               text not null,
    cubre_toda_localidad    boolean not null default true,

    constraint chk_proveedor_cobertura_provincia_valida
        check (provincia in (
            'Buenos Aires', 'Ciudad Autónoma de Buenos Aires', 'Catamarca',
            'Chaco', 'Chubut', 'Córdoba', 'Corrientes', 'Entre Ríos',
            'Formosa', 'Jujuy', 'La Pampa', 'La Rioja', 'Mendoza',
            'Misiones', 'Neuquén', 'Río Negro', 'Salta', 'San Juan',
            'San Luis', 'Santa Cruz', 'Santa Fe', 'Santiago del Estero',
            'Tierra del Fuego, Antártida e Islas del Atlántico Sur',
            'Tucumán'
        )),
    constraint chk_proveedor_cobertura_localidad_largo
        check (char_length(btrim(localidad)) between 2 and 100),
    constraint chk_proveedor_cobertura_localidad_con_letra
        check (localidad ~ '[[:alpha:]]')
);

create unique index uq_proveedor_cobertura_localidad_normalizada
    on proveedor_coberturas (
        proveedor_id, lower(btrim(provincia)), lower(btrim(localidad))
    );


-- ------------------------------------------------------------
-- 5.b. proveedor_cobertura_barrios — alcance parcial
-- ------------------------------------------------------------
create table proveedor_cobertura_barrios (
    id              uuid primary key default gen_random_uuid(),
    cobertura_id    uuid not null references proveedor_coberturas(id) on delete cascade,
    barrio          text not null,

    constraint chk_proveedor_cobertura_barrio_largo
        check (char_length(btrim(barrio)) between 2 and 100),
    constraint chk_proveedor_cobertura_barrio_con_letra
        check (barrio ~ '[[:alpha:]]')
);

create unique index uq_proveedor_cobertura_barrio_normalizado
    on proveedor_cobertura_barrios (cobertura_id, lower(btrim(barrio)));


-- ------------------------------------------------------------
-- 6. especialidades (HU4) — catálogo predefinido + personalizadas
-- ------------------------------------------------------------
create table especialidades (
    id      uuid primary key default gen_random_uuid(),
    nombre  text not null,

    constraint chk_especialidades_nombre_largo
        check (char_length(btrim(nombre)) between 2 and 80),
    constraint chk_especialidades_nombre_con_letra
        check (nombre ~ '[[:alpha:]]')
);

create unique index uq_especialidades_nombre_normalizado
    on especialidades (lower(btrim(nombre)));

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
create index idx_proveedores_activo on proveedores (activo);
create index idx_proveedor_coberturas_ubicacion
    on proveedor_coberturas (provincia, localidad);
create index idx_proveedor_cobertura_barrios_barrio
    on proveedor_cobertura_barrios (barrio);
