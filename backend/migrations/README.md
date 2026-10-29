# Migraciones de base de datos

Scripts SQL para crear y actualizar el esquema de Supabase.

## HU19 — Canal AARI (aplicada en desarrollo el 27/10/2026)

`20261027130000_hu19_canal_aari.sql` requiere HU16, HU17, coberturas/HU15 y las
dos migraciones de HU32. No requiere las tres migraciones del intento Meta que
se conservan más abajo como evidencia local. Agrega rondas/solicitudes/eventos
privados y procedencia, moneda y tipo de importe exacto/mínimo a presupuestos.
No etiqueta registros históricos con valores inventados. RLS y revocaciones
quedan en el SQL, sin políticas públicas. El DDL no publica pedidos ni envía correo.

Aplicada con autorización en Supabase AARI de desarrollo, con respaldo previo,
DDL/historial atómicos y controles RLS. No repetir la migración al hacer pull.
Se validó el recorrido con datos ficticios y un aviso real acotado; los workers
generales permanecen apagados. El worker SMTP requiere autorización para envíos
reales adicionales. Detalle y
orden operativo: [HU19 AARI](../../docs/hu19_canal_aari_presupuestos.md).

## HU32 — Acceso de proveedores (aplicada en desarrollo el 26/10/2026)

Orden obligatorio: `20261026180000_hu32_rol_proveedor.sql` y, en una transacción
posterior, `20261026180100_hu32_acceso_proveedor.sql`. PostgreSQL requiere
confirmar el enum nuevo antes de utilizarlo. No se reescriben migraciones previas.
Agregan correo/vínculo opcionales al padrón, identidad consistente, invitaciones
privadas por hash, vencimiento, consumo único y auditoría de envío. Proveedores
legados preservados, sin altas de cuentas ni invitaciones automáticas.

**Aplicadas con autorización en Supabase AARI el 26/10/2026**, versiones de
historial `20261026180000` y `20261026180100`. Se verificaron RLS, ausencia de
políticas/grants públicos en invitaciones, triggers y conteos de las 35 tablas
anteriores. Sólo se verifican conteos/metadatos, no igualdad fila por fila.
Cero mensajes y cero registros de negocio creados por la aplicación del DDL.
No repetir por integrante, pull o merge. Si la segunda etapa falla, la primera
adición del enum puede quedar confirmada: comprobar historial y retomar la
etapa faltante, sin borrar ni renombrar objetos.

Preflight de sólo lectura: `python -m scripts.apply_provider_access --env-root
<raíz-local-con-env>`. Aplicación sólo autorizada con `--apply --authorized`.
El script valida el destino AARI, confirma DDL/historial por etapa y no imprime
credenciales. La publicación de esta rama no activa workers ni envía correo.
Detalle de alcance y límites: `docs/hu32_acceso_proveedor.md` desde la raíz.

## HU17 — Elección de tipo de proveedor (aplicada en desarrollo)

`20261018235315_hu17_eleccion_proveedor.sql`, generada con Supabase CLI 2.81.3,
requiere HU16 y outbox HU10/HU12/HU14. Agrega etapa/auditoría privada, plazos
48/72 h, triggers de apertura, FK e índices del outbox y el estado pendiente de
datos de proveedor propio, sin derivación anticipada ni backfill en DDL.
RLS y permisos revocados; funciones SECURITY INVOKER. Extiende el mensaje de
estado con guarda, conservando la función y permisos anteriores. Límites 5s/30s.
**Aplicada con autorización el 18/10/2026 (Argentina)** al Supabase AARI de
desarrollo, historial remoto `20261019003825_hu17_eleccion_proveedor` (19/10 UTC).
El archivo local conserva `20261018235315`; no renombrar ni repetir por pull,
integrante o merge. 39 tablas anteriores/58 filas con conteos conservados;
RLS/permisos, políticas, numeración, FK, CHECK, índices y funciones verificados.
Nueva tabla vacía y sin avisos vinculados. Sin escrituras de negocio ni envíos.
Control de privacidad impidió extraer huellas de contenido privado: se verifican
conteos/metadatos, no igualdad fila por fila ni un respaldo de datos.
Reactivar el worker es una acción separada: puede recuperar solicitudes previas
y procesar sus plazos sin reiniciarlos. No repetir HU16 por este incremento.
Detalles y controles en `docs/hu17_eleccion_proveedor.md` desde la raíz.

## HU16 — Autorización de gasto (aplicada en desarrollo)

`20261015212745_hu16_autorizacion_gasto.sql` fue generado con Supabase CLI
2.81.3 y se validó en PostgreSQL local. Agrega la auditoría privada de
autorización/rechazo con RLS, revocaciones, FK e idempotencia. Ajusta el índice
de reclamos activos para excluir el rechazo terminal, sin borrar historial.
Requiere el esquema integrado de main, responsables HU12 y outbox HU10/HU14.
El circuito de autorización no requiere la migración de HU21 del PR #34.
**16/10/2026: aplicada con autorización al Supabase AARI compartido de desarrollo**,
historial `20261016053335_hu16_autorizacion_gasto`, asignado por el conector.
No renombrar el archivo local ni repetir por integrante o pull. Preflight,
guardas atómicas, RLS/permisos, FK, restricciones e índices verificados; las 38
tablas anteriores conservaron conteos/huellas, seguridad y numeración. Tabla
nueva vacía, sin decisiones, cambios de estado ni mensajes. Límites 5s/30s.
Asesores sin advertencias nuevas ni FK nuevas sin índice; avisos informativos
de tabla privada sin políticas e índices todavía sin uso documentados.
Flujo, pruebas, comandos y límites en `docs/hu16_autorizacion_gasto.md`.

## HU14 — Migración aplicada al entorno compartido de desarrollo

`20261007133447_hu14_derivacion_expensas.sql` es una migración aditiva generada
con versión única por Supabase CLI 2.120.0. Requiere
`23_notificaciones_actor_responsable.sql`; las versiones 24/25 de HU30 y 26 de
HU13 se reservan sin renombrar archivos históricos. Antes de aplicar, contrastar
el orden de archivos completos con el historial de la base, especialmente los
dos archivos `23_*` de las ramas en integración.

Agrega el snapshot privado del reporte, FK de notificación/reclamo, evento de
correo de expensa e índices; protege notas y configuración con RLS/revocaciones.
No clasifica casos, no cambia estados ni encola correos retroactivos. La
restricción de notas conserva filas históricas y valida las escrituras nuevas.

**07/10/2026: aplicada con autorización al Supabase compartido AARI de
desarrollo**, historial `20261007143153_hu14_derivacion_expensas`. La versión
local generada por CLI sigue siendo `20261007133447`; conservar ambos registros
sin renombrar ni volver a ejecutar por integrante o pull. Tabla, restricciones,
índices, RLS, permisos y lecturas reales de FastAPI verificados. Sin datos de
prueba, cambios de estado ni correos. Los conteos previos se conservaron.
El aviso de índice compuesto en la FK de reportes quedó corregido mediante
la incremental autorizada siguiente, sin editar esta migración ya aplicada.
Detalles, comandos y evidencia en `docs/hu14_derivacion_expensas.md` desde la raíz.

### HU14 — Índice compuesto incremental

`20261007150410_hu14_indice_fk_derivacion_expensas.sql`, generado por Supabase
CLI 2.120.0, se aplica **después** de
`20261007133447_hu14_derivacion_expensas.sql`. Agrega únicamente un índice B-tree
no único sobre `(notificacion_id, reclamo_id)` en la tabla de reportes. Conserva
FK, unicidad previa, RLS, permisos y datos; límites de bloqueo/ejecución 5s/30s.

**Aplicada con autorización el 07/10/2026** al Supabase AARI de desarrollo,
historial `20261007150923_hu14_indice_fk_derivacion_expensas`. No repetir por
integrante o pull ni modificar la migración principal para incluir este cambio.
Índice válido/listo verificado, aviso de esa FK eliminado de los asesores,
conteos y seguridad sin cambios. Backend final: 385 aprobadas/26 omitidas.

## HU15 — Auditoría de búsqueda de proveedores (aplicada en desarrollo)

`20261009120000_hu15_proveedores_candidatos.sql` es aditiva y se aplica después
del esquema integrado del Sprint 3: administración/coberturas, reclamos,
especialidades, responsables y outbox de notificaciones. No renombrar los
archivos históricos ni repetir esta migración por integrante o pull.

Crea `reclamo_busquedas_proveedores`, sus FK, controles de resultado/origen,
unicidad por reclamo e intento e índices de historial/cola. Habilita RLS y
revoca permisos de public/anon/authenticated; no habilita acceso del Data API.
La versión usa timestamp único conforme al convenio de migraciones vigente.
No convierte ni clasifica reclamos, no genera búsquedas retroactivas y no
envía correos. La transacción limita bloqueos a 5 s y sentencias a 30 s.

**11/10/2026: aplicada con autorización al Supabase compartido de desarrollo**,
historial `20261009120000_hu15_proveedores_candidatos`. Antes de aplicar se
verificaron las dependencias y la ausencia de instalación parcial. Tabla,
cinco índices válidos/listos, cuatro FK, unicidad, siete CHECK, RLS, ausencia
de políticas/permisos públicos y conservación de los conteos de las trece
tablas existentes verificados. No repetir por integrante o pull.

El script `backend/scripts/check_provider_candidates_postgres.py` ofrece los
modos `check`, `apply` y `test`. Los dos últimos requieren autorización
explícita; `test` usa únicamente sus registros sintéticos y rollback, no los
fixtures destructivos de PostgreSQL local. No envía correos ni llama a Gemini.
Ver `docs/hu15_proveedores_candidatos.md`.

## Instalación nueva

Ejecutar desde el SQL Editor, en este orden:

1. `01_modulo_administracion.sql`
2. `02_modulo_reclamos.sql`
3. `03_modulo_coordinacion.sql`
4. `04_configuracion_sistema.sql`
5. `05_seed_admin.sql` — reemplazar los valores de ejemplo antes de ejecutarlo.
6. `06_clasificacion_agente.sql`

La instalación nueva debe aplicar además, en orden:

1. `13_autenticacion_usuarios.sql` — restricciones e índices de acceso seguro.
2. `14_acceso_propietarios_inquilinos.sql` — cuentas vinculadas, backfill y
   seguimiento del correo de bienvenida.
3. `17_usuarios_operadores.sql` — nombres de operadores y asignación de
   reclamos. También es necesaria en instalaciones nuevas.
4. `18_revalidar_operador_al_escalar.sql` — revalida asignaciones al pasar a
   `Escalado`, aunque no cambie el operador.
5. `19_alta_reclamos.sql` — habilita el alta inicial sin rubro, agrega número
   visible, evita reclamos activos duplicados, protege fotos/notificaciones y
   configura el bucket privado `reclamos-fotos`.
6. `20_contratos_alquiler.sql` — contratos, versiones, historial, protección de
   períodos firmados superpuestos y bucket privado `contratos-alquiler`.
7. `21_actualizaciones_estado_reclamo.sql` — registra cada transición con su
   origen, genera una notificación durable para el inquilino y agrega reintentos
   seguros de entrega.
8. `22_corregir_alerta_cancelaciones.sql` — adapta la alerta histórica de tres
   cancelaciones al contrato obligatorio de la bandeja de salida de la 21.
9. `23_notificaciones_actor_responsable.sql` — registra al actor responsable
   de cada reclamo clasificado, sus plazos y notificaciones idempotentes.
10. `23_clausulas_contractuales.sql` — análisis durable de documentos,
    cláusulas revisables, auditoría y contexto contractual de clasificación.
11. `24_evidencia_clausulas_contractuales.sql` — evidencia por página y
    propuestas rechazadas.
12. `25_extraccion_asistida_literal.sql` — origen e historial de extracción asistida.
13. `26_resolucion_escalados.sql` — cola y auditoría de clasificación manual.
14. `20261007224000_hu13_destinatario_habilitado.sql` — sólo después de 26;
    excluye cuentas pendientes de primer ingreso del aviso de cola.

Las dos migraciones con prefijo `23_` corresponden a historias independientes
y ambas ya fueron aplicadas en desarrollo. Se identifican por el nombre completo
del archivo, no sólo por el número; no reemplazar una por la otra ni repetirlas.
El orden publicado es explícito: `23_notificaciones_actor_responsable.sql`,
`23_clausulas_contractuales.sql`, `24_evidencia_clausulas_contractuales.sql` y
`25_extraccion_asistida_literal.sql`. HU14 utiliza las versiones únicas con
timestamp documentadas arriba, después de sus dependencias. Para futuras
migraciones, acordar una versión única y verificar el historial completo;
`26_` está reservado para HU13. No renombrar las ya aplicadas para corregir
la colisión histórica de prefijos.

El módulo de administración inicial ya incorpora el resultado de las
migraciones incrementales 07, 08, 09, 10, 11, 12, 15 y 16. No deben repetirse
en una instalación nueva.

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
8. `14_acceso_propietarios_inquilinos.sql` — crea cuentas para propietarios e
   inquilinos existentes, vincula cada persona con un único usuario y agrega el
   estado persistente del envío de credenciales. La migración se detiene si
   detecta emails repetidos entre identidades de acceso para evitar asignaciones
   ambiguas.
9. `15_proveedores_cobertura_horario.sql` — agrega el horario habitual y las
   tablas de cobertura estructurada. Conserva temporalmente `zona_cobertura`
   para revisar proveedores existentes sin perder información.
10. Completar las coberturas estructuradas de los proveedores que devuelve la
   consulta indicada abajo.
11. `16_finalizar_cobertura_proveedores.sql` — verifica que todos los
    proveedores tengan cobertura válida y recién entonces elimina
    `zona_cobertura`.
12. `17_usuarios_operadores.sql` — agrega el nombre del operador, una referencia
    opcional desde reclamos, su índice y validación de asignaciones a operadores
    activos. Aplicar después de la revisión indicada abajo.
13. `18_revalidar_operador_al_escalar.sql` — corrige el trigger y su función
    para revalidar también al entrar al estado `Escalado`. No reemplaza la 17.
14. `19_alta_reclamos.sql` — agrega el contrato de persistencia de HU8 y el
    bucket privado. Antes de aplicarla, revisar el control de duplicados activos.
15. `20_contratos_alquiler.sql` — contratos de alquiler, versiones, auditoría,
    permisos y bucket privado de PDF. Aplicar después de 19.
16. `21_actualizaciones_estado_reclamo.sql` — amplía la bandeja de salida,
    crea la notificación por cambio de estado y conserva email como canal
    inicial. WhatsApp permanece desacoplado hasta su historia específica.
17. `22_corregir_alerta_cancelaciones.sql` — redefine la función de alerta de
    cancelaciones para completar asunto, estado y próxima fecha de intento.
18. `23_notificaciones_actor_responsable.sql` — agrega el seguimiento durable
    del responsable, los eventos de notificación y los trabajos de recordatorio
    y vencimiento. Aplicar después de 22.
19. `23_clausulas_contractuales.sql` — agrega análisis y revisión de cláusulas
    contractuales. Aplicar después de 22 y de la migración 20 de contratos.
20. `24_evidencia_clausulas_contractuales.sql` — conserva evidencia por página,
    propuestas rechazadas y el uso operativo/contextual de cada cláusula. Aplicar
    después de `23_clausulas_contractuales.sql`.
21. `25_extraccion_asistida_literal.sql` — origen e historial del análisis
    asistido/literal. Aplicar después de `24_evidencia_clausulas_contractuales.sql`.
22. `26_resolucion_escalados.sql` — resolución manual y avisos de cola.
23. `20261007224000_hu13_destinatario_habilitado.sql` — después de 26;
    no reemplaza ni reaplica la migración histórica.

## HU30: migración 24

Aplicada el **21/09/2026 al Supabase compartido de desarrollo** mediante
`scripts/check_contract_clauses_postgres.py --mode apply`. La ejecución no creó
análisis ni llamó a Gemini. Se volvió a comprobar que las tablas mantienen RLS
activo y no conceden lectura pública. No repetirla al actualizar la rama.

La migración aditiva agrega JSONB de propuestas
rechazadas al análisis y, en cada cláusula, evidencia separada por página y una
clasificación `operativa`, `contexto` o `excluir`. Los registros anteriores
conservan sus campos originales, reciben evidencia vacía y uso `operativa`; no se
inventan fragmentos por página durante la migración.

No crea tablas expuestas ni cambia las políticas existentes: las columnas quedan
protegidas por el RLS y las revocaciones de las tablas de la migración 23. Antes
de aplicarla en otra base, comprobar que 23 esté instalada y que no existan
columnas homónimas agregadas manualmente.

## HU30: migración 23

Aplicada el **21/09/2026 al Supabase compartido de desarrollo** mediante
`scripts/check_contract_clauses_postgres.py --mode apply`. No repetirla al hacer
pull. La ejecución no creó análisis ni llamó a Gemini: únicamente agregó la cola
durable, las cláusulas revisables, su auditoría y el snapshot contractual de cada
clasificación. Las tres tablas nuevas tienen RLS activo y no conceden lectura a
`public`, `anon` ni `authenticated`.

Antes de aplicarla en otra base, ejecutar el mismo script en modo `check`. La
prueba PostgreSQL crea un esquema aislado, recorre solicitud idempotente,
procesamiento, confirmación, consulta del contexto y permisos, y termina con
`ROLLBACK`. El análisis externo continúa deshabilitado por defecto y no forma
parte de esta migración.

## HU13: migración 26 — aplicada en el entorno compartido

`26_resolucion_escalados.sql` se aplica después de las migraciones 21, 22 y
`23_notificaciones_actor_responsable.sql`. Tanto una instalación nueva como una
existente necesitan esta migración para utilizar la resolución manual.

Los números 24 y 25 están reservados por HU30. Su rama también incorpora
`23_clausulas_contractuales.sql`: existe otro script con prefijo 23. No ordenar
solo por el prefijo ni renombrar scripts ya aplicados. Antes de la próxima
instalación, coordinar el inventario y orden con HU30, identificando cada archivo
por su nombre completo y el historial del entorno. HU13 no depende de las tablas
de cláusulas y su migración no las modifica.

La 26 es aditiva y transaccional, con `lock_timeout = 5s` y
`statement_timeout = 30s`. Crea `reclamo_decisiones_clasificacion` con RLS y
revocación de permisos a `anon` y `authenticated`, más índices para auditoría
y cola. Un trigger encola un único aviso por entrada a clasificación pendiente
o escalado sin responsable; pasar entre ambos estados no repite el aviso. Usa
operador asignado activo, otro operador activo o administrador activo, sin
difusión a todas las cuentas. No crea notificaciones retroactivas ni envía SMTP.

**Aplicación confirmada:** ejecutada con autorización en Supabase AARI de
desarrollo el **05/10/2026 (Argentina)**, registrada como
`20261005191504_hu13_resolucion_escalados`. No modificó reclamos existentes.
Se verificaron tabla, índices, función, trigger, RLS y permisos después del
commit; **9 pruebas reales HU13 aprobadas** con datos ficticios y rollback,
sin Gemini, SMTP ni Storage. No quedaron registros de prueba ni se consumió la
secuencia normal de reclamos. La aplicación y el registro comparten una transacción: un fallo revierte
ambos; una segunda ejecución verifica lo instalado y no repite la migración.

Desde `backend`, `scripts/check_escalados_postgres.py --mode check` realiza
solo lectura. `--mode apply` aplica si falta; `--mode test` ejecuta exclusivamente
las pruebas sintéticas HU13 con rollback. Los dos últimos requieren autorización
expresa; no habilitan Gemini, SMTP ni Storage reales. Se puede indicar
`--env-file` sin imprimir su contenido. Comandos, resultados y pendientes en
`docs/hu13_resolucion_escalados.md`.

## HU13: corrección incremental de destinatario — aplicada en Supabase

`20261007224000_hu13_destinatario_habilitado.sql` requiere la 26 y redefine
únicamente `notificar_clasificacion_pendiente()`: conserva el destinatario
determinista y agrega `AND NOT primer_ingreso`. Sin cuentas habilitadas, el
reclamo permanece en la cola pero no se encola un correo sin destinatario.
No cambia asignaciones, RLS, tablas, reclamos ni alertas históricas. Conserva
`SECURITY INVOKER`, `search_path` vacío y permisos revocados. No ejecuta SMTP.

**Aplicada con autorización el 07/10/2026 en Supabase AARI de desarrollo**,
registro `20261007224000_hu13_destinatario_habilitado`. La comprobación previa
confirmó que la 26 estaba instalada de forma coherente: sólo se aplicó la
incremental. La 26 y su registro `20261005191504_hu13_resolucion_escalados`
permanecen intactos. Objetos, función, RLS, permisos e historial verificados;
**9 pruebas reales HU13 aprobadas**, con datos ficticios, rollback y limpieza
comprobada por sus IDs. No se consumió la secuencia de reclamos ni se llamó
a Gemini, SMTP o Storage. No repetir ninguna de las dos migraciones al hacer pull.

El script `check_escalados_postgres.py` comprueba objetos y registro antes de
decidir: una instalación vieja coherente muestra la incremental como pendiente;
una nueva aplica ambas en la misma transacción; una segunda ejecución no las
repite. Registra la incremental con versión única `20261007224000` y nombre
`hu13_destinatario_habilitado`. Si hay objetos sin historial, historial sin
objetos o desacuerdo en la función corregida, se detiene sin reparaciones
automáticas. Un fallo de registro revierte el cambio de función. El modo
`test` requiere ambas migraciones verificadas y continúa usando datos ficticios
con rollback, sin Gemini, SMTP ni Storage.

El orden de HU14 sigue documentado al comienzo y es independiente de esta
corrección, después de `23_notificaciones_actor_responsable.sql`. No ordenar
todos los scripts únicamente por su prefijo numérico.
Evidencia: `docs/hu13_correcciones_pr29_2026-10-07.md` desde la raíz.

## HU12: preparación de la migración 23

La migración es aditiva, transaccional y limita la espera de bloqueos a cinco
segundos y cada sentencia a treinta segundos. Agrega la preferencia de canal
del propietario, tipifica los eventos de la bandeja de salida y crea
`reclamo_responsables` con RLS habilitado y permisos revocados para `anon` y
`authenticated`.

Los plazos se leen de `configuracion_sistema`: el recordatorio se programa con
`plazo_recordatorio_horas` (48 horas por defecto) y el vencimiento suma
`plazo_escalado_horas` (24 horas por defecto). El worker materializa los
eventos con `FOR UPDATE ... SKIP LOCKED` y claves de idempotencia, sin mantener
la transacción abierta durante la llamada al proveedor de correo.

La migración también redefine las funciones de notificación de estados y de
alertas por cancelaciones para completar `tipo_evento` y
`clave_idempotencia`. No modifica reclamos existentes, no genera
notificaciones por sí sola y no envía correos.

**Aplicación confirmada:** se ejecutó con autorización en el Supabase
compartido AARI de desarrollo el **17/09/2026 (Argentina)** y quedó registrada
como `20260917200108_hu12_notificaciones_actor_responsable`. No repetirla al
hacer pull. Se recorrieron gasto ordinario, extraordinario, expensa,
recordatorio y vencimiento; el QA finalizó con `ROLLBACK` y no invocó SMTP.
Evidencia y decisiones: `docs/hu12_notificacion_actor_responsable.md`.

## HU29: migración 20

Aplicada el **13/09/2026 al Supabase compartido de desarrollo** mediante
`scripts/check_contracts_postgres.py --mode apply`. No repetir al hacer pull.
Es aditiva y transaccional, con límites de bloqueo/sentencia. Instala
`btree_gist` si falta, crea tres tablas con RLS y revoca permisos públicos.
No carga cuentas, contratos ni PDFs, y no agrega una fecha de firma manual.

La exclusión GiST rechaza períodos firmados superpuestos para una misma
propiedad. Las FK restrictivas conservan personas e inmuebles con historial.
El bucket `contratos-alquiler` queda privado, limitado a PDF de 10 MiB.

Antes de aplicarla en otra base, revisar `to_regclass('public.contratos')`.
Si ya existe, no volver a ejecutar ni borrar tablas para continuar: verificar
la instalación existente. No existe una migración de rollback destructivo.

Prueba real aislada y verificación de RLS/privacidad aprobadas. La prueba de
carga/descarga real del PDF todavía requiere configurar Storage en el `.env`
local. Evidencia, comandos y pendientes: `docs/hu29_gestion_contratos.md`.

## HU10: preparación de la migración 21

El archivo vacío fue generado con `supabase migration new` y luego se adaptó a
la numeración incremental que utiliza este repositorio. La migración es
transaccional, limita la espera de bloqueos a 5 segundos y cada sentencia a 30
segundos. No modifica estados de reclamos, no envía mensajes y no aplica el
cambio al proyecto remoto por sí sola.

**Aplicación confirmada:** en el proyecto compartido AARI de desarrollo se
ejecutó el 10/09/2026 (Argentina) y quedó registrada como
`20260911003055_hu10_actualizaciones_estado_reclamo` (versión UTC). Se verificó
la estructura instalada, RLS, ausencia de lectura para `anon` y
`authenticated`, funciones `SECURITY INVOKER` con `search_path` vacío y que el
conteo de notificaciones no cambió durante la migración.

La tabla `notificaciones` funciona como bandeja de salida: persiste asunto,
mensaje, estado que originó el aviso, próxima fecha de intento y una reserva
temporal configurable con `NOTIFICATION_LEASE_SECONDS` (120 segundos por
defecto) para recuperar trabajos abandonados. Cada
intento fallido se reprograma; después del tercero queda en `fallido`. Los
workers reclaman filas con `FOR UPDATE SKIP LOCKED` y confirman la transacción
antes de llamar a SMTP, por lo que no mantienen bloqueos durante una operación
de red. El resultado solo actualiza la fila si todavía corresponde al mismo
número de intento; un worker demorado no puede sobrescribir el resultado de un
intento posterior. Si un proceso se interrumpe durante el tercer intento, la
fila se marca como fallida cuando vence su reserva en lugar de quedar
indefinidamente en `procesando`. La entrega es al menos una vez: si SMTP acepta
el mensaje y la conexión se corta antes de confirmarlo, un reintento todavía
puede producir un duplicado.

El trigger de historial genera una notificación únicamente cuando existe un
estado anterior. La confirmación inicial de HU8 se conserva separada y no se
duplica. La preferencia de todos los inquilinos existentes comienza en `email`;
el puerto de WhatsApp queda explícitamente desacoplado y las pruebas utilizan
un doble hasta implementar su integración real.

Antes de aplicar, verificar que no haya notificaciones con `intentos` fuera del
rango 0..3. Si las hubiera, la transacción aborta sin corregir ni eliminar datos
automáticamente. Después de aplicar en un entorno autorizado, validar:

- columnas, constraints, índices parciales y FK hacia el historial;
- que una transición cree exactamente una notificación y el alta inicial no;
- origen `agente` cuando el backend define ese contexto y `sistema` como valor
  seguro en los demás casos;
- aislamiento de reclamos por inquilino en los endpoints de listado y detalle;
- tres intentos, recuperación de una fila `procesando` vencida y ausencia de
  reclamos duplicados de una misma fila con dos workers concurrentes;
- RLS y ausencia de permisos públicos inesperados, además de los asesores de
  seguridad y rendimiento de Supabase.

Las pruebas reales de SMTP o WhatsApp y la aplicación al Supabase compartido
requieren autorización específica. La suite automatizada local no consume
servicios externos. La evidencia del recorrido transaccional de los 20 estados,
realizado con `ROLLBACK` y sin SMTP, está en
`docs/hu10_validacion_actualizaciones_estado.md`.

### HU10: corrección incremental 22 (PR #25)

La migración 21 ya está aplicada en el Supabase compartido y no se modifica.
La corrección 22 redefine `chk_alerta_cancelaciones()` para que, desde la
tercera cancelación, la alerta complete `asunto`, el estado actual del reclamo
y `proximo_intento_en`. Sin esos datos obligatorios, el `INSERT` del trigger
fallaba y revertía también la cancelación que originaba la alerta.

La migración conserva el trigger y el umbral históricos, utiliza
`SECURITY INVOKER` con `search_path` vacío y revoca la ejecución pública. No
crea cancelaciones ni envía correos.

**Aplicación confirmada:** se ejecutó con autorización en el Supabase
compartido AARI de desarrollo el **14/09/2026 (Argentina)** y quedó registrada
como `20260915005037_hu10_corregir_alerta_cancelaciones` (versión UTC). No
repetirla al hacer pull. El QA PostgreSQL insertó tres cancelaciones dentro de
una transacción, verificó la notificación completa y finalizó con `ROLLBACK`,
sin persistir datos ni invocar SMTP.

## HU8: preparación de la migración 19

La migración es transaccional y no crea reclamos, no sube fotos y no envía
correos. `tipo_id` queda opcional únicamente en el alta: el clasificador puede
completarlo después. El número visible usa una secuencia independiente del UUID
interno y los registros anteriores reciben un número antes de exigir `NOT NULL`.

Se considera activo todo estado salvo `Resuelto` y
`Resuelto (sin confirmación)`. Antes de crear el índice único parcial, la
migración se detiene y revierte si ya existen dos reclamos activos para la misma
combinación de inquilino y propiedad. No elimina ni fusiona datos históricos.

El bucket `reclamos-fotos` queda privado, limitado a 5 MB y a MIME
`image/jpeg`/`image/png`. Los metadatos, el historial inicial y las
notificaciones mantienen RLS sin permisos para `anon` ni `authenticated`. No se
crean políticas públicas: las operaciones pasan por FastAPI y una clave de
servicio exclusiva del backend. Esa clave se guarda solo en `.env`, nunca en
variables `VITE_*`, commits o documentación con valores reales.

Después de aplicar, validar en el entorno autorizado:

- nulabilidad de `reclamos.tipo_id`, secuencia e índice único de `numero`;
- rechazo concurrente de un segundo reclamo activo para la misma unidad;
- bucket privado, límites de tamaño/MIME y ausencia de políticas públicas;
- alta con cero y tres fotos, rollback de metadatos y limpieza de objetos ante
  un fallo de persistencia;
- notificación en estado `pendiente` y transición posterior a `enviado` o
  `fallido`, sin revertir el reclamo.

La confirmación visual es inmediata al persistir. El objetivo de 30 segundos se
mide desde esa persistencia hasta que SMTP acepta o rechaza el envío, no hasta
que el mensaje aparece en la bandeja del destinatario. Las pruebas reales de
Storage y SMTP requieren autorización específica; la suite local usa dobles.

La migración 09 se detiene si encuentra propiedades existentes porque provincia
y localidad no pueden inferirse de manera segura. Esos registros deben
completarse antes de volver a ejecutarla.

Las migraciones 01 y 15 habilitan RLS en las cinco tablas de proveedores y
revocan sus permisos a los roles `anon` y `authenticated`. El módulo se consume
exclusivamente a través de FastAPI; por eso no deben agregarse políticas públicas
del Data API sin una nueva decisión de arquitectura y su correspondiente revisión
de seguridad.

La zona anterior no se convierte automáticamente porque un texto libre no
permite inferir con seguridad provincia, localidad, alcance completo y barrios.
Después de aplicar la migración 15, esta consulta identifica los registros que
deben completarse:

```sql
select
    p.id,
    p.nombre_razon_social,
    p.zona_cobertura
from proveedores p
where not exists (
    select 1
    from proveedor_coberturas pc
    where pc.proveedor_id = p.id
)
order by p.nombre_razon_social;
```

Por cada resultado se debe insertar al menos una fila en
`proveedor_coberturas`. Si `cubre_toda_localidad` es `false`, también debe
existir al menos un barrio en `proveedor_cobertura_barrios`. La migración 16 se
puede volver a ejecutar de forma segura: se detendrá sin eliminar la columna
anterior mientras falte algún dato y será un no-op si la columna ya no existe.

## HU7: preparación y validación de la migración 17

La migración es aditiva y transaccional: no crea cuentas, no modifica
contraseñas y no envía correos. Debe aplicarse con autorización al proyecto y
entorno correctos antes de usar la API de operadores. Mantiene RLS en
`usuarios` y `reclamos` y revoca permisos de `anon` y `authenticated`; el acceso
sigue siendo a través del backend, no del Data API de Supabase.

**Aplicación confirmada:** en el proyecto compartido AARI de desarrollo se
ejecutó el 02/09/2026 y quedó registrada como
`20260902235524_hu7_usuarios_operadores`. No repetirla por cada integrante ni
por cada pull. En otras bases, comprobar primero su historial y estructura.
El archivo limita la espera de bloqueos a 5 segundos y cada sentencia a
30 segundos; si vence el límite, la transacción no se confirma.
La evidencia y las pruebas optativas están en `docs/hu7_validacion_supabase.md`
desde la raíz del repositorio.

Antes de ejecutarla, revisar si existen operadores:

```sql
select count(*) as operadores_existentes
from public.usuarios
where rol = 'operador';
```

Si hay operadores previos sin nombre, la migración se detiene y revierte toda
su transacción, incluida la columna nueva. **No se deben inventar nombres ni
borrar cuentas para continuar.** Con autorización, preparar la columna en una
operación separada:

```sql
alter table public.usuarios
    add column if not exists nombre_completo text;
```

Completar después los nombres reales de esas cuentas mediante un canal
administrativo seguro, identificando cada cuenta por su ID. No pegar datos
personales en scripts versionados. Los nombres deben tener entre 2 y 120
caracteres, solo letras Unicode, espacios simples, apóstrofes o guiones, sin
espacios en los extremos. Una vez completados y revisados, ejecutar el script
17 completo. Si una herramienta deja una transacción fallida abierta, cerrarla
con `ROLLBACK` antes de corregir los datos y volver a ejecutar.

Después de aplicarlo, validar:

- Existencia de `usuarios.nombre_completo`, `reclamos.operador_asignado_id`,
  la FK, `idx_reclamos_operador_asignado` y el trigger de asignación.
- Rechazo de nuevas asignaciones a cuentas inactivas o de otro rol. Las
  asignaciones históricas no modificadas pueden conservar un operador inactivo.
- Alta, unicidad global, hash real, primer ingreso y baja transaccional en un
  entorno autorizado. Probar rollback y concurrencia en PostgreSQL: los dobles
  SQLite de la suite local no validan bloqueos ni `pgcrypto`.
- RLS y ausencia de permisos públicos inesperados. Revisar los asesores de
  seguridad y rendimiento de Supabase después del cambio.

Usar un remitente simulado en pruebas automatizadas. El envío SMTP real
requiere autorización específica y un destinatario de prueba acordado.

## HU7: corrección incremental 18 (PR #21)

**Aplicada con autorización al Supabase compartido AARI de desarrollo el
03/09/2026 (Argentina)**, historial
`20260904001512_hu7_revalidar_operador_al_escalar` (versión UTC).
No repetirla por integrante ni por pull. La 17 permanece intacta,
con su historial y hash. En otras bases, aplicar esta corrección después de 17 tanto en
bases existentes como en instalaciones nuevas. No hay cambios de `.env`,
dependencias, cuentas o correos.

El trigger ahora observa `operador_asignado_id` y `estado`; la función valida
inserciones, cambios de operador y transiciones de otro estado a `Escalado`.
La asignación debe ser nula o apuntar a una cuenta con rol `operador` activa.
Reabrir con un operador inactivo se rechaza con SQLSTATE `23514`: el llamador
debe indicar otro operador activo o quitar la asignación en la misma operación.
No se libera automáticamente un reclamo histórico por cambiar otros campos ni
por ejecutar `SET estado=estado` cuando aún no está escalado.

Antes de aplicar, comprobar si el fallo ya dejó asignaciones inválidas. Esta
consulta solo devuelve un conteo, sin datos personales:

```sql
select count(*) as escalados_con_operador_invalido
from public.reclamos r
where r.estado = 'Escalado' and r.operador_asignado_id is not null
  and not exists (
      select 1 from public.usuarios u
      where u.id = r.operador_asignado_id and u.rol = 'operador' and u.activo
  );
```

La migración repite esa comprobación bajo el bloqueo de tabla obtenido al
recrear el trigger. Si hay resultados, aborta y revierte todos sus cambios:
no modifica asignaciones existentes. Revisar su tratamiento con el responsable
y ejecutar `ROLLBACK` si el cliente dejó abierta la transacción fallida.

La operación es transaccional, con espera de bloqueo de 5 segundos y límite de
30 segundos por sentencia. Conserva `SECURITY INVOKER`, `search_path` vacío y
la revocación de ejecución a roles públicos. No cambia RLS ni los permisos de
tablas. `FOR SHARE` sigue serializando la validación con la baja del operador.

Tras aplicarla, comprobar la definición instalada de función y trigger,
permisos y el conteo anterior; ejecutar las pruebas PostgreSQL autorizadas de
reapertura válida/inválida, historial y ambos órdenes de concurrencia con la
baja. No confundir los controles de texto locales con pruebas SQL reales.
Detalles y resultados en `docs/hu7_validacion_supabase.md`.

## HU15 — Búsqueda automática incremental (aplicada en Supabase)

`20261011160000_hu15_busqueda_automatica.sql` se aplica después de
`20261009120000_hu15_proveedores_candidatos.sql`. La base ya está aplicada;
no editar ni repetir esa migración. La nueva crea `reclamo_tareas_proveedores`
con huella de entrada, ID durable, reserva/renovación, estado y motivo,
origen de especialidad y versiones del modelo/prompt. Incluye RLS y revocación
de permisos públicos, sin políticas para anon/authenticated. No cambia estados,
autorizaciones ni datos de reclamos existentes al aplicarse.

**Aplicada con autorización el 11/10/2026 en Supabase de desarrollo**, registrada
como `20261011160000_hu15_busqueda_automatica`. Los conteos de las trece tablas
previas y de la auditoría base se preservaron. RLS activo, sin políticas públicas
ni permisos anon/authenticated; FK, unicidad, CHECK e índice verificados.
No repetir al hacer pull. En otra base requiere autorización e historial.
El worker descubre reclamos abiertos una vez activado. Una reserva vencida pide
revisión, no vuelve a llamar al modelo automáticamente. La habilitación externa
es independiente (`PROVIDER_SPECIALTY_EXTERNAL_ENABLED`), apagada por defecto.
Las pruebas locales crean bases descartables. El comprobador adicional
`scripts/check_provider_candidates_automatic.py --env-file <ruta-al-env-local>
--mode test` requiere autorización: aprobó **14 pruebas** en Supabase con
registros ficticios y rollback verificado. El alcance interno de QA limita el
worker a un único reclamo propio; no procesa reclamos existentes ni llama a
Gemini, SMTP o Storage. `--mode check` sólo inspecciona y `--mode apply` aplica
una única vez, conservando la migración base. Ambos workers HU15/permisos
externos siguen apagados por defecto; habilitarlos es una decisión explícita.

## HU30: migración aditiva 25 — extracción asistida y respaldo literal

**Aplicada con autorización al Supabase compartido de desarrollo el 05/10/2026.**
Las migraciones 23 y 24 ya estaban presentes. No repetir 25 por integrante ni
por pull: agrega columnas sin `IF NOT EXISTS` y debe ejecutarse una sola vez.
En otra base, respetar el orden 20 → 23 → 24 → 25.

`25_extraccion_asistida_literal.sql` agrega:

- `contrato_analisis.modo`, `ejecucion_id` y `propuestas_fuente_rechazadas`.
- `contrato_clausulas.origen` (`ia` o `literal`).
- `contrato_analisis_intentos`: modelo, versiones, estado, resultado y tiempos
  por ejecución. RLS habilitado y permisos revocados a public/anon/authenticated.

No elimina contratos, cláusulas, eventos ni revisiones. El backend accede a la
auditoría con su conexión privada y las rutas de revisión siguen restringidas
a administración. No introducir políticas públicas para facilitar la prueba.
Una respuesta tardía se conserva en su intento, pero no reemplaza la ejecución
actual; los fallos externos requieren una nueva solicitud explícita.

Desde `backend/` del worktree, el comprobador acepta el `.env` compartido:

```bash
../../../backend/venv/Scripts/python.exe scripts/check_contract_clauses_postgres.py --env-file ../../../backend/.env --mode check
```

`--mode apply` aplica solamente las migraciones faltantes y requiere aprobación
explícita. `--mode test` crea un esquema aislado dentro de una transacción y
hace rollback al terminar; también requiere autorización. No analiza contratos
reales ni llama a Gemini. La comprobación final del 05/10 aprobó **1 prueba**,
incluyendo preservación, revisiones, historial, respuestas tardías, falla terminal,
activación explícita y RLS. El esquema de prueba no queda instalado.

El resultado detallado está en
`docs/evaluaciones/hu30/flujo_asistido_2026-10-05.md`. El éxito técnico no acredita
la precisión semántica de las interpretaciones propuestas por Gemini.

## HU19 — transporte y solicitudes (pendientes de aplicar)

- `20261019230000_hu19_whatsapp_base.sql`: bandeja de eventos entrantes autenticados,
  unicidad, índices, RLS y revocaciones. Sin presupuestos ni decisiones automáticas.
- `20261020120000_hu19_solicitudes_presupuesto.sql`: rondas por elección HU17,
  solicitudes por proveedor y auditoría de preparación/reserva/envío. Depende de
  HU15, HU16 y HU17. No modifica sus migraciones, tablas, estados ni datos previos.

Ambas son versionadas de una sola ejecución. **No están aplicadas en Supabase**
y no se ejecutan al iniciar FastAPI. Aplicar sólo con autorización, historial y
preflight. Nuevas tablas privadas, RLS activo y sin permisos/políticas para
PUBLIC/anon/authenticated. No agregar políticas anónimas para hacer funcionar el
webhook: su firma se verifica en el backend antes de escribir con conexión privada.
No hay seeds, envíos, plazos retroactivos ni llamadas de red dentro del DDL.

Validación y límites: `docs/hu19_solicitudes_presupuesto.md`. Las pruebas usan
bases PostgreSQL locales nuevas y descartables; nunca la base compartida.

## HU21 — Contexto persistente del agente

`20261011222710_hu21_contexto_persistente.sql` agrega metadatos de sesión y
el esquema privado de PostgresSaver 3.1.2, con RLS/permisos de clientes revocados.
No modifica migraciones anteriores ni procesa reclamos existentes.

**Aplicada con autorización el 11/10/2026 en Supabase AARI de desarrollo**,
historial `20261011222710_hu21_contexto_persistente`. No repetirla por
integrante, cambio de rama o pull. DDL/historial atómicos; las 33 tablas
públicas conservaron conteos y huellas. Restricciones, índices, RLS,
permisos, preflight y lectura nativa del checkpointer verificados.
No creó sesiones de negocio ni envió mensajes; worker apagado.
La migración rechaza contextos anteriores no vacíos para revisarlos
explícitamente sin sobrescribirlos.

QA compartido posterior autorizado el 14/10/2026: 12 casos aprobados con
escrituras ficticias y rollback obligatorio, sin volver a aplicar DDL.
Las 38 tablas públicas/privadas conservaron conteos y huellas; numeración
sin cambios y cero sesiones/checkpoints/eventos de negocio remanentes.
No se enviaron mensajes ni se activaron workers. La recuperación con grafo
y repositorio nuevos se probó dentro de la misma transacción, no con un
reinicio del proceso sobre Supabase. Runner y límites en el documento HU21.

Para otras bases, `scripts/check_coordination_postgres.py --mode check`
verifica instalación y coherencia. Aplicación local explícita con
`--mode apply`; un destino compartido requiere autorización y
`--allow-shared`. La aplicación a AARI usa
`scripts/apply_hu21_shared.py --authorized --env-root <raíz-local>`
con validación de destino y preservación. El flag no sustituye la autorización
humana. No se llama `PostgresSaver.setup()` al arrancar.

Reinstalar requirements antes de usar HU21 y mantener
`COORDINATION_WORKER_ENABLED=false` hasta acordar su activación/integración.
Más detalles y avisos previos del proyecto en
[documentación HU21](../../docs/hu21_contexto_persistente.md).

## HU19 — recepción y cierre de presupuestos (25/10/2026)

`20261025160000_hu19_respuestas_presupuesto.sql` sigue a las dos migraciones HU19
`20261019230000` y `20261020120000`. Agrega plazos/ronda, moneda y procedencia de
presupuestos, FK compuesta y auditoría de procesamiento por mensaje. No atribuye
moneda a presupuestos históricos ni cambia sus importes. RLS habilitado y permisos
revocados a PUBLIC/anon/authenticated, sin políticas públicas.

Las tres están pendientes de autorización/aplicación en Supabase. No ejecutar al
hacer pull ni al iniciar FastAPI. Validar en PostgreSQL local antes de solicitar
aplicación compartida y mantener ambos workers HU19 apagados.
Detalle: [recepción HU19](../../docs/hu19_respuestas_presupuesto.md).

## HU19 — canal privado AARI (27/10/2026)

`20261027130000_hu19_canal_aari.sql` requiere HU16, HU17, HU32 y las coberturas
HU15. Es independiente de las tres migraciones Meta anteriores: no aplicarlas
para habilitar el canal AARI. Agrega rondas, solicitudes y eventos privados,
procedencia y tipo de importe en presupuestos, sin reinterpretar precios antiguos.

**Aplicada con autorización el 27/10/2026 en Supabase AARI de desarrollo**.
Respaldo local privado, ensayo con rollback, DDL/historial atómicos, conteos de
36 tablas existentes preservados y RLS/permisos verificados. No repetirla por
integrante ni al cambiar de rama. No activa workers ni envía correos al aplicar.

QA compartido: dos recorridos autenticados exacto/mínimo con datos ficticios y
rollback; aviso puntual recibido según confirmación de Talía y recorrido visual
con la cuenta real de prueba completado con un mínimo ficticio persistido.
No se activaron envíos generales.
Mantener `AARI_QUOTE_WORKER_ENABLED=false` hasta acordar la puesta en marcha.
Detalle y límites: [canal AARI HU19](../../docs/hu19_canal_aari_presupuestos.md).

## HU33 — Mensajes y consultas técnicas (29/10/2026)

`20261028210000_hu33_conversaciones.sql` requiere el canal AARI de HU19
(`20261027130000`) y sus dependencias. Es una migración aditiva de una sola
ejecución: hilos por solicitud/finalidad/audiencia, participante original,
apertura/cierre explícitos de consultas, mensajes inmutables y lecturas por
usuario. Avisos de agente individuales y consultas proveedor-inquilino separadas;
administración sólo consulta. Incluye índices, RLS y revocación a PUBLIC/anon/authenticated; no crea
políticas públicas. No modifica presupuestos, decisiones ni estados de reclamos.

**Aplicada en Supabase el 29/10/2026 con autorización.** Preflight y huellas:
39 tablas previas preservadas; 42 tras agregar HU33. QA con datos ficticios y
rollback: cinco controles aprobados, todas las filas y numeración preservadas,
sin envíos. Ejecutor `scripts/check_hu33_shared.py --authorized --env-root RUTA
--apply --validate`; no expone configuración ni inicia workers. No volver a
ejecutar el SQL directo: el ejecutor reconoce/verifica un esquema ya instalado.
No renombrar ni volver a ejecutar las migraciones anteriores. No se aplica DDL
al iniciar FastAPI. `AARI_CONVERSATIONS_ENABLED=false` por defecto; habilitar sólo
después de verificar esquema y permisos. No requiere Gemini ni SMTP.

La definición local se ajustó antes de su primera aplicación compartida. No
repetir el SQL directo sobre una base con tablas HU33 ni improvisar cambios a
mano; el ejecutor permite verificar la instalación existente sin reaplicarla.
La finalidad `coordinacion` queda reservada en el modelo, sin acceso público ni
activación automática; HU23 implementará sus acciones y permisos separados. La
primera lectura de una solicitud histórica proyecta sus eventos HU19 de forma
idempotente, conservando fecha de origen y sin notificaciones externas.
Detalle: [HU33](../../docs/hu33_conversaciones_privadas.md).
