-- ============================================================
-- AARI — Configuración y soporte
-- Tabla: configuracion_sistema
-- Requiere: 01, 02 y 03 ya ejecutados (no tiene FKs a ellos,
--           pero mantiene el orden general del proyecto)
-- ============================================================

-- ------------------------------------------------------------
-- 18. configuracion_sistema (HU14 — correo de contacto de la
--     inmobiliaria, y cualquier otro parámetro configurable:
--     umbral de escalado del agente, plazo de presupuestos, etc.)
-- ------------------------------------------------------------
create table configuracion_sistema (
    clave       text primary key,
    valor       text not null,
    descripcion text,
    updated_at  timestamptz not null default now()
);

create trigger trg_configuracion_sistema_updated_at
before update on configuracion_sistema
for each row execute function set_updated_at();

-- Seed de parámetros iniciales conocidos por los requisitos
insert into configuracion_sistema (clave, valor, descripcion) values
    ('correo_contacto_inmobiliaria', 'gasparotto.claudio@gmail.com',
        'Correo al que se envían los reportes de reclamos clasificados como expensa (HU14)'),
    ('plazo_respuesta_presupuesto_horas', '24',
        'Horas que tiene un proveedor para responder con un presupuesto (HU19)'),
    ('plazo_recordatorio_horas', '48',
        'Horas sin respuesta del actor responsable antes de enviar un recordatorio automático'),
    ('plazo_escalado_horas', '24',
        'Horas adicionales sin respuesta tras el recordatorio antes de escalar al operador'),
    ('umbral_confianza_clasificacion', '0.85',
        'Umbral mínimo de confianza del agente para clasificar sin escalar (HU9)'),
    ('duracion_sesion_agente_horas', '72',
        'Horas de inactividad antes de que una sesión del agente expire (HU21)');