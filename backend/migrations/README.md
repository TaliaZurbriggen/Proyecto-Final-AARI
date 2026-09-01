# Migraciones de base de datos

Scripts SQL para crear y actualizar el esquema de Supabase.

## Instalación nueva

Ejecutar desde el SQL Editor, en este orden:

1. `01_modulo_administracion.sql`
2. `02_modulo_reclamos.sql`
3. `03_modulo_coordinacion.sql`
4. `04_configuracion_sistema.sql`
5. `05_seed_admin.sql` — reemplazar los valores de ejemplo antes de ejecutarlo.
6. `06_clasificacion_agente.sql`

La instalación nueva debe aplicar además `13_autenticacion_usuarios.sql` para
agregar las restricciones e índices de acceso seguro.

El módulo de administración inicial ya incorpora el resultado de las
migraciones incrementales 07, 08, 09, 10, 11, 12 y 15. No deben repetirse en
una instalación nueva.

## Instalación existente

Aplicar únicamente las migraciones pendientes y respetar este orden:

1. `07_propietarios_email_unico.sql` — normaliza y hace único el email.
2. `08_propiedades_integridad.sql` — normaliza la dirección y evita duplicados.
3. `09_ubicacion_propiedades.sql` — agrega provincia y localidad, reemplaza
   zona por barrio opcional y convierte el piso a entero (`0` representa PB).
4. `10_ubicacion_propiedades_con_letras.sql` — impide direcciones, localidades
   y barrios formados únicamente por números o símbolos.
5. `11_inquilinos_integridad.sql` — normaliza los datos de inquilinos, hace
   único el email y mantiene consistente el estado con la propiedad asignada.
6. `12_nombres_personas_validos.sql` — normaliza espacios y restringe los
   nombres de propietarios e inquilinos a letras, espacios, apóstrofes y
   guiones. Se detiene si existen registros incompatibles para evitar
   corregir nombres reales de forma automática.
7. `13_autenticacion_usuarios.sql` — normaliza el email de acceso y agrega
   restricciones e índices para intentos fallidos y bloqueos temporales.
8. `15_proveedores_cobertura_horario.sql` — reemplaza la zona libre por
   coberturas de provincia, localidad y barrios; agrega el horario habitual y
   refuerza el catálogo de especialidades.

La migración 09 se detiene si encuentra propiedades existentes porque provincia
y localidad no pueden inferirse de manera segura. Esos registros deben
completarse antes de volver a ejecutarla.

La migración 15 también se detiene si encuentra proveedores existentes: una
zona escrita como texto libre no permite inferir con seguridad provincia,
localidad, alcance completo y barrios. Esos registros deben revisarse y
migrarse manualmente antes de aplicarla nuevamente.
