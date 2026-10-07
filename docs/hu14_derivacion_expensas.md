# HU14 — Reporte y derivación de expensas

[AARI-157](https://taliazurbriggen.atlassian.net/browse/AARI-157), implementación
del 07/10/2026, con migración aplicada al Supabase compartido de desarrollo.
Rama `codex/AARI-157-derivacion-expensas`, desde `main`
`80afb67`. Propuesta aprobada por la persona responsable. HU y las doce
subtareas AARI-158 a AARI-169 inicialmente **En curso**. El 07/10 la persona
responsable autorizó terminar la entrega de desarrollo y hacer commit/push/PR
para revisión de Talía. Estado de publicación y cierre administrativo abajo;
la revisión y el merge no se dan por realizados al terminar el desarrollo.
Tiempo real confirmado por la persona responsable y registrado el 07/10:
**1 h 20 min** en AARI-157, worklog `10268` (4800 segundos). Se verificó una
única entrada, sin duplicación ni minutos agregados por estimación.

## Comportamiento implementado

Una clasificación confirmada como expensa crea, en su transacción, una copia
estructurada del reporte y una única notificación de tipo `expensa_reporte`.
Reemplaza el aviso genérico HU12 a la inmobiliaria para esa clasificación;
no duplica correos ni envía SMTP desde el grafo o PostgreSQL.

El reporte conserva número/ID, ingreso/clasificación, ubicación/unidad,
descripción, urgencia, contacto mínimo del inquilino, fundamento, origen y
confianza. No contiene DNI, notas internas, credenciales o enlaces públicos
de adjuntos. El enlace usa la base de `APP_LOGIN_URL`, sin userinfo, query ni
fragmento, y el detalle siempre requiere una sesión autorizada.

El worker existente mantiene tres intentos totales, separados 60 segundos,
con fechas y reservas en PostgreSQL. SMTP se invoca fuera de transacciones.
Solo una aceptación SMTP cuyo resultado se registre con una reserva vigente
puede avanzar el reclamo a `Derivado a inmobiliaria (expensa)`. Se bloquea
reclamo antes de actualizar notificación, se verifica el intento y se compara
el vencimiento con `clock_timestamp()`; `CURRENT_TIMESTAMP` queda fijado al
inicio de la transacción y no detectaría un vencimiento durante espera de lock.

Se conserva el estado cuando el reclamo avanzó por otra operación. La entrega
se registra igualmente si es vigente, pero nunca hace retroceder el reclamo.
La aceptación no garantiza bandeja de entrada ni lectura. Una caída después
del envío y antes de confirmarlo en la base todavía puede causar duplicados
SMTP; no se promete entrega exactamente una vez.

El cambio de estado reutiliza el trigger de HU10: historia y un aviso sencillo
al inquilino, sin fundamentos privados ni notas. No se agrega otro correo
paralelo para esa misma transición. Las expensas no participan de recordatorios
y vencimientos por respuesta del responsable de HU12; ordinarios y
extraordinarios conservan ese circuito.

Después de tres fallos se conserva el estado previo y se presenta el fallo
en el panel. Si falta un correo válido, se conserva el reporte sin consumir
intentos SMTP. Cambiar la configuración afecta reportes futuros, no reenvía
pendientes antiguos ni cambia el destinatario congelado. No hay reenvío masivo
o conversión retroactiva de históricos en esta HU.

## API privada y navegación

| Ruta | Permiso y comportamiento |
| --- | --- |
| `GET /expensas` | Administración/operación, página de 20 y total antes de paginar. |
| `GET /expensas/{id}` | Reporte, entrega y notas solo para esos roles. No expone reclamos de otro tipo. |
| `POST /expensas/{id}/notas` | Nota append-only de 1–1000 caracteres; autor de sesión y fecha de servidor. |
| `GET/PUT /configuracion/correo-inmobiliaria` | Solo administración; email validado, sin otras claves de configuración. |

Todos los accesos requieren cuenta activa y primer ingreso completado. El autor
de una nota se revalida bajo bloqueo compartido del usuario, compatible con
bajas de operadores. No se aceptan un autor o timestamp enviados por el cliente.

Filtros: `propiedad_id`, `fecha_desde`, `fecha_hasta`, `situacion` y `page`.
Fechas sobre el ingreso, en `America/Argentina/Buenos_Aires`: inicio inclusive
y medianoche siguiente exclusiva. Rango invertido y filtros inválidos: `422`.
Situaciones: derivados (por defecto), pendientes, fallidos/configuración,
históricos sin reporte HU14 y todas las expensas. Alertas de entrega no se
ocultan porque la vista de derivados esté vacía; respetan propiedad y fechas.

La sección **Expensas** aparece en la navegación administrativa y operativa.
Usa el layout de cada rol, sin agregar otra cabecera o cambiar el Home de HU31.
Listado y detalle conservan filtros en la URL; el administrador puede desplegar
configuración del contacto. Notas, configuración, auditoría y fundamentos no
aparecen en el portal del inquilino. Se reutilizan componentes/tokens de AARI,
con filas etiquetadas y filtros apilados en móvil, carga/vacío/error y abortado
de solicitudes para impedir que respuestas viejas reemplacen una consulta nueva.

## Migración y seguridad

Archivo: `backend/migrations/20261007133447_hu14_derivacion_expensas.sql`.
Versión generada con **Supabase CLI 2.120.0**, mediante `migration new`, en una
carpeta temporal; no se instaló una dependencia runtime del proyecto, no se
creó una vinculación a Supabase ni se ejecutó `db push`.

Requiere `23_notificaciones_actor_responsable.sql`. HU30 tiene reservados sus
24/25 y HU13 su 26; esta versión timestamp es única. No se renombraron archivos
aplicados. Al integrar las otras historias, documentar el orden por nombres
completos y contrastarlo con el historial del entorno, no con un glob por 23.

Cambios aditivos:

- `reclamo_derivaciones_expensa`: una fila por reclamo, copia JSONB y vínculo a
  notificación o motivo seguro de falta de contacto.
- FK compuesta que exige que la notificación corresponda al mismo reclamo.
- Nuevo tipo de evento de reporte, sin borrar tipos existentes.
- Índices de expensas y notas; restricción de longitud para notas nuevas,
  `NOT VALID` para no rechazar o alterar notas históricas.
- RLS y revocación de permisos de `PUBLIC`, `anon` y `authenticated` sobre
  reporte, notas y configuración. Acceso exclusivo por FastAPI/rol de backend;
  sin vistas o funciones `SECURITY DEFINER`, sin nuevas políticas públicas.

La migración se validó primero en bases locales descartables de PostgreSQL
17.11 y se aplicó con autorización al **Supabase compartido AARI de desarrollo
el 07/10/2026**. El historial remoto registró
`20261007143153_hu14_derivacion_expensas`; el nombre local conserva la versión
generada por CLI `20261007133447`. No renombrar el archivo ni editar el historial
para igualar los timestamps, y no repetir la aplicación por integrante o pull.
No hubo backfill, cambios de estado, datos de prueba ni envío de correos.

### Comprobación del entorno compartido

Antes de aplicar se confirmó el proyecto AARI, la dependencia de HU12 y la
migración de HU13 ya instalada (`20261005191504_hu13_resolucion_escalados`).
Los tipos de notificación existentes coincidían con los preservados por HU14;
no se ejecutaron otras migraciones ni se modificó trabajo de las ramas de Talía.

Después de aplicar se comprobó:

- Tabla de reportes, FK compuesta, checks e índices presentes y válidos. El
  check de notas continúa `NOT VALID` por diseño para conservar históricos.
- RLS activo en reporte, notas y configuración; `anon` y `authenticated` sin
  permisos SELECT/INSERT/UPDATE/DELETE sobre esas tres tablas.
- Conexión real de FastAPI al proyecto correcto: rol actual `postgres`, no
  superusuario, con BYPASSRLS y los permisos requeridos. No se crearon roles
  ni se ampliaron sus privilegios. El uso futuro de un rol de aplicación de
  mínimo privilegio requiere una decisión separada del equipo.
- Consultas reales del repositorio para las cinco situaciones y lectura de
  configuración correctas, dentro de una transacción `READ ONLY`. El contacto
  está configurado; su valor no se publica en evidencia ni documentación.
- Conteos antes/después idénticos: 1 reclamo, 2 notificaciones, 0 notas y
  6 entradas de configuración. La tabla nueva tiene 0 reportes; todavía no
  hay expensas en este entorno. No se inició el worker ni la aplicación web.
- Los asesores se compararon antes/después: no aparecieron nuevos WARN/ERROR
  de seguridad. El INFO de RLS sin políticas es intencional para una tabla
  privada servida exclusivamente por FastAPI, con permisos públicos revocados.
- El asesor de rendimiento añadió un INFO por falta de un índice que cubra
  explícitamente `(notificacion_id, reclamo_id)` en la FK nueva. Existe ya
  unicidad sobre `notificacion_id`, pero el asesor pide cobertura compuesta.
  Fue una mejora separada, no un fallo funcional; quedó corregida mediante
  la migración incremental autorizada descrita abajo.
  Los dos índices recién creados también figuran como no usados, esperable
  antes de disponer de expensas; no se eliminan por ese aviso.

Referencias de los asesores:
[FK sin índice compuesto](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys),
[RLS sin políticas](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy),
[índices sin uso](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).
Persisten avisos previos sobre
[`set_updated_at` sin search_path fijo](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)
y ejecución pública de `rls_auto_enable()` SECURITY DEFINER para
[anon](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable)
y [authenticated](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable).
No se modificaron funciones ajenas como parte de HU14; se conservan como deuda
de seguridad para revisión específica. La lectura local del `.env` emitió dos
avisos preexistentes de sintaxis de python-dotenv; no impidieron conectar ni
validar y no se cambiaron valores o archivos de configuración.

### Índice incremental autorizado — 07/10/2026

Archivo generado con Supabase CLI 2.120.0:
`backend/migrations/20261007150410_hu14_indice_fk_derivacion_expensas.sql`.
Aplicado después de la migración principal al Supabase AARI de desarrollo,
historial `20261007150923_hu14_indice_fk_derivacion_expensas`. No repetir por
integrante ni cambiar timestamps locales o remotos para igualarlos.

Agrega únicamente el índice B-tree no único
`idx_derivaciones_expensa_notificacion_reclamo` sobre
`reclamo_derivaciones_expensa (notificacion_id, reclamo_id)`. Conserva la
unicidad existente, la FK, los datos y todos los permisos. Transacción con
`lock_timeout=5s` y `statement_timeout=30s`; en el entorno compartido la tabla
estaba vacía. No se editó la migración principal: su SHA256 antes/después es
`2B08889654469CA2687285F2F580851428E69A100D76520A9F5179A2FFE6269C`.

La fixture PostgreSQL aplica los dos archivos de HU14 por nombre explícito.
Una nueva prueba comprueba índice válido/listo, ambas columnas en ese orden,
carácter no único y FK validada. Prueba individual: **1 aprobada**. Suite
backend final después del ajuste: **385 aprobadas, 26 omitidas**, 18 avisos
preexistentes, sin fallos, en 34,70 segundos. El frontend no cambió en este
ajuste; conserva la validación previa de 122 pruebas, lint y build.

Las primeras corridas encontraron problemas del entorno de QA, no del índice:
el arranque local usó el puerto predeterminado en vez de 55426 y la carpeta
compartida de temporales de pytest tenía permisos restringidos. Se reinició
solo la instancia de QA en loopback/55426 y se usó `--basetemp` con una carpeta
nueva exclusiva de esta tarea, sin borrar caches existentes. La corrida final
completa pasó con todas las integraciones externas desactivadas.

Después de aplicar, PostgreSQL confirmó `indisvalid=true`, `indisready=true`
y la definición compuesta correcta. El asesor dejó de informar la FK de HU14
sin índice: esos INFO bajaron de 17 a 16, todos restantes preexistentes. El
índice nuevo aparece como no usado antes de cargar expensas, lo cual no justifica
eliminarlo. Los asesores de seguridad no cambiaron. RLS/permisos públicos
siguen protegidos y los conteos continuaron idénticos: 1 reclamo,
2 notificaciones, 0 notas, 6 configuraciones y 0 reportes. Sin correos, llamadas
Gemini, datos de prueba compartidos, cambios de `.env`, commit, PR o worklogs.

## Configuración para el equipo

No hay variables `.env` nuevas ni cambios en los `.env` locales existentes.
Se reutilizan `DATABASE_URL`, `JWT_SECRET`, `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`,
`APP_LOGIN_URL` y la configuración del worker de HU10.

El **destinatario** está en `configuracion_sistema.correo_contacto_inmobiliaria`
y se edita desde Expensas como administrador. No es necesariamente el
**remitente** `SMTP_FROM`. Confirmar el destinatario correcto antes de crear
nuevos reportes en el entorno compartido; no se reemplazan silenciosamente
los valores históricos ni se incluyen direcciones reales en esta documentación.

Antes de usar el módulo en una base, aplicar la migración con autorización al
entorno correcto. La falta de esas estructuras no se corrige automáticamente
al levantar la app. Nunca usar el Supabase compartido en la suite aislada.

## Validación local

Con las integraciones externas deshabilitadas, desde `backend/`:

```powershell
$env:DATABASE_URL = 'postgresql://aari_test@127.0.0.1:55426/postgres'
$env:AARI_TEST_POSTGRES_URL = $env:DATABASE_URL
$env:RUN_SUPABASE_INTEGRATION = '0'
$env:RUN_SUPABASE_MIGRATION_TESTS = '0'
$env:RUN_OPERADORES_POSTGRES_TESTS = '0'
$env:RUN_CONTRATOS_POSTGRES_TESTS = '0'
$env:RUN_HU12_SMTP_INTEGRATION = '0'
python -m pytest tests/test_expensas.py tests/test_expensas_postgres.py -q -p no:cacheprovider
python -m pytest -q --tb=short -p no:cacheprovider
```

La fixture restringe la URL a loopback, crea una base `aari_pr26_<uuid>`,
aplica el archivo de HU14 por nombre explícito y la elimina al terminar.
No carga contactos reales de seeds históricos. Se desactiva cache de pytest
porque dos carpetas de cache preexistentes no eran accesibles al sandbox;
no se borran archivos ajenos para resolverlo.

Evidencia obtenida durante implementación:

- Backend completo antes del índice incremental: **384 aprobadas, 26 omitidas**, 18 avisos preexistentes
  de datetime/SQLite; sin fallos, en 33,70 segundos. Incluye la regresión de
  enlace sin userinfo/query/fragmento y vencimiento de reserva durante un lock.
- Casos PostgreSQL: éxito en intentos 1/2/3, tres fallos sin transición,
  falta/contacto inválido, snapshot inmutable, dos workers, reserva vencida,
  caída en último intento, estado avanzado y vencimiento mientras espera lock.
  RLS y ausencia de privilegios SELECT públicos comprobadas.
- Frontend: **122 aprobadas en 26 archivos**, `npm run lint` y
  `npm run build` aprobados. Doce casos nuevos de tabla, alertas, filtros,
  paginación/retorno, notas, configuración, roles, vacío/históricos,
  error y respuestas tardías.
- Navegador con FastAPI/PostgreSQL reales, cinco expensas ficticias y SMTP
  simulado: login administrativo, listado/filtros, fallo 3/3, detalle, retorno,
  nota persistida con autor/fecha y cambio de contacto sin cambiar envíos viejos.
  Operador accede sin configuración y agrega su propia nota. Inquilino ve el
  estado derivado, sin notas/fundamento, y se redirige al intentar `/expensas`.
- Móvil 390 × 844: listado y detalle sin desborde de página; tamaño restaurado.
  Capturas de QA guardadas fuera del repositorio. Base, credencial y procesos
  de prueba retirados al terminar, sin datos de prueba en el entorno compartido.

Las pruebas funcionales locales no hicieron llamadas Gemini ni SMTP real.
La aplicación posterior de la migración y las comprobaciones de solo lectura
en Supabase se describen arriba. El sender simulado no acredita recepción
en un buzón real.

### Revalidación funcional posterior al índice — 07/10/2026

Se repitió el recorrido con FastAPI, autenticación por cookie y PostgreSQL
reales en una base local descartable. Frontend en `127.0.0.2:5181` y backend
en `127.0.0.2:8001`, para no reemplazar sesiones del sitio habitual. Todos los
contactos y cinco unidades/reclamos eran ficticios; cada caso respetó la
restricción existente de un reclamo activo por inquilino/propiedad.
Worker, SMTP real y APIs de clasificación permanecieron desactivados.

- Administración: login, vista de derivados vacía con alertas visibles,
  pendientes, filtros por propiedad/fechas, rechazo del rango invertido y
  conservación de filtros al regresar desde el detalle. Nota vacía deshabilitada;
  nota válida persistida con autor y fecha de servidor.
- Entrega simulada mediante el servicio real: un reporte aceptado, transición
  a derivado y una sola notificación al inquilino en la base. Cambiar el contacto
  de configuración no alteró el destinatario congelado ni el reporte. Las notas
  internas no se incluyeron en el mensaje simulado.
- Fallo 3/3 y contacto inválido: conservaron el estado previo y las alertas;
  el segundo conservó 0 intentos incluso después del cambio de configuración.
  El histórico siguió sin reporte ni envío automático.
- Operación: acceso al listado/detalle, sin configuración, lectura de la nota
  administrativa y guardado de su propia nota con autor/fecha correctos. Tab
  enfocó Guardar nota con anillo visible y Enter realizó el guardado.
- Inquilino: solo su reclamo en Mis reclamos, estado derivado e historial sin
  notas ni fundamento privado. Intentar `/expensas` redirigió al portal personal.
- Comprobación por API con TestClient y PostgreSQL reales: **9 verificaciones
  aprobadas**. Anónimo recibe 401; operador recibe 200 en expensas y 403 en
  configuración; inquilino recibe 403 en expensas/configuración/notas y 200 en
  su reclamo sin campos privados. Las dos notas del navegador persistieron.
- Escritorio y móvil 390 × 844: listado y detalle sin desborde horizontal de
  página, filtros/acciones de 44 px en móvil. Capturas guardadas fuera del repo;
  tamaño de ventana restaurado. Sin errores ni advertencias de consola durante
  el recorrido. `npm run lint` y `npm run build` se ejecutaron otra vez y pasaron.

Las primeras preparaciones del harness corrigieron datos ficticios duplicados
y nombres de columnas de la propia prueba; no se modificaron restricciones ni
código de producto para hacerlas pasar. La verificación final usó el runtime
Python existente en `backend/.venv/python.exe`. Se conservan los resultados de
la suite completa posterior al índice: **385 backend aprobadas/26 omitidas** y
**122 frontend aprobadas**.

Al finalizar se cerró la sesión/pestaña de QA, se detuvieron sus procesos,
se eliminó exclusivamente su base local y se verificaron **0 bases temporales
restantes**. Se retiraron el harness y la credencial ficticia, y se detuvo solo
la instancia PostgreSQL de QA. No hubo cambios en `.env`, datos de prueba
compartidos, correos reales, llamadas Gemini, commit, PR, worklogs ni cierre de
actividades. La evidencia local no sustituye la prueba SMTP real ni la futura
integración con HU13/HU31.

### Revisión de preparación para cierre — 07/10/2026

Con autorización para validar, se comprobó la configuración SMTP existente
sin mostrar sus valores ni modificar `.env`. Gmail aceptó conexión, EHLO,
STARTTLS con certificado verificado, autenticación y NOOP. Se cerró la conexión
sin ejecutar envío: **0 mensajes reales enviados**. Esta comprobación acredita
acceso al servicio, no prueba todavía el reporte completo ni recepción en un
buzón. El destinatario de una prueba con datos ficticios queda por confirmar.

La revisión actual de dependencias confirmó que HU13 sigue en el PR #29 abierto,
head `053236ac5526a79e3ce51b22f70f3b399d5608ac`, base `main` en `80afb67`.
Su helper común incorpora resolución humana y auditoría, mientras que HU14
actual incorpora el reporte en la persistencia automática. Al integrar ambos
hay que conservar las dos rutas, el origen humano y el reporte único; comparar
archivos no equivale a haber probado esa combinación.

HU31 permanece En curso en Jira y existe la rama
`codex/AARI-332-home-administrador`; no apareció un PR al buscar sus
identificadores HU31/AARI-332. Su `App.jsx` añade `/inicio` y no incluye las rutas
nuevas de HU14. Debe conservarse su Home junto con Expensas en la integración.
No se fusionaron, copiaron ni modificaron las ramas de Talía, y no se afirma que
esta compatibilidad pendiente esté validada funcionalmente en `main`.

Esta comprobación inicial fue seguida por el envío y la prueba combinada
descritos abajo. La HU no se cerró ni se cambiaron estados de subtareas.

### SMTP real e integración aislada autorizados — 07/10/2026

Se envió **un único correo real**, con el asunto
`AARI - Reporte de expensa #000001`, al destinatario expresamente autorizado.
El contenido se identificó como `PRUEBA HU14` y solo incluyó un reclamo,
propiedad e inquilino ficticios de una base PostgreSQL local descartable.
No se publica el destinatario ni la configuración SMTP en esta documentación.
La persona responsable **confirmó la recepción en su buzón**.

Ocho comprobaciones del circuito real aprobadas: estado pendiente antes del
envío, aceptación SMTP registrada, un único intento y fecha de envío, estado
derivado posterior, una única notificación al inquilino, exclusión de notas
privadas y fundamento en el aviso sencillo y ausencia de segundo envío al
repetir el procesamiento. El aviso al inquilino se procesó con un sender
simulado; no hubo otro correo real. La base se retiró al terminar. El enlace
local del reporte de prueba no corresponde a una ficha permanente.

Se creó otra copia temporal independiente para combinar:

- `main` / base HU14: `80afb674f80972ebdb0385b1758f6f243cd38975`.
- HU13 / PR #29: `053236ac5526a79e3ce51b22f70f3b399d5608ac`.
- HU31: `f6dd2206561a1661e051f79062309efa33da6e13`.

**No se modificaron las ramas reales, no hubo merge en GitHub y estos
resultados no certifican una integración ya publicada en `main`.**
Se reconciliaron solo en la copia el helper de clasificación, routers y
navegación: auditoría de HU13 más reporte de HU14, con origen humano y confianza
nula, Home de HU31 más Expensas y Casos escalados. La primera suite detectó una
expectativa previa de HU13 que exigía `responsable_inicial` para expensa;
se adaptó únicamente en la copia a `expensa_reporte`, comprobando también que
no existe el evento genérico duplicado. Se agregaron dos casos de integración
para decisiones de administrador y operador, sin consultar al modelo.

Resultados finales de la **copia combinada**:

- Backend: **527 aprobadas, 35 omitidas, 18 avisos previos**. pytest con
  `-q --tb=short -p no:cacheprovider` y `--basetemp` aislado; PostgreSQL 17.11
  local, flags de integración externa apagados y SMTP/modelos desactivados.
- Frontend: **214 aprobadas en 32 archivos**; `npm run lint` y
  `npm run build` aprobados, sin instalar dependencias.
- Navegador con FastAPI/cookies/PostgreSQL reales: Home con un pendiente,
  navegación a Casos escalados, decisión manual de expensa, auditoría del
  resultado anterior, reporte simulado aceptado con 1/3 intentos y origen
  administrador, sin atribuirle confianza del agente. Home actualizado con
  cero pendientes y un reclamo todavía activo: derivar no resuelve la reparación.
- **16 verificaciones API/SQL aprobadas**: permisos por rol, notas con autor
  operativo de servidor, confidencialidad del inquilino, un reporte, un aviso
  simple de derivación y rechazo 409 de una segunda decisión manual.
- Escritorio y móvil 390 × 844: Home, menú, listado y detalle sin desborde
  horizontal; consola final sin errores/avisos. Capturas conservadas fuera
  del repo. El junction a las dependencias existentes requirió permitir sus
  fuentes únicamente en el Vite temporal; no se cambió el Vite del proyecto.

El botón `Revisar casos` dentro del Home sigue deshabilitado, tal como está en
la rama actual de HU31; habilitarlo al integrar HU13 es una tarea pendiente
de coordinación, no un cambio aplicado por HU14. En la combinación probada
el acceso de la navegación a Casos escalados sí funciona.

Al terminar se cerraron las sesiones/pestañas de QA, se restauró el viewport,
se retiraron credenciales y bases y se detuvieron sus servidores y PostgreSQL.
Se comprobaron **0 bases descartables restantes**. No hubo datos de prueba
en Supabase, llamadas a APIs de clasificación, cambios de `.env`, commit,
push, PR, cierre Jira ni tiempo adicional a los **1 h 20 min confirmados**.

### Contrato de integración definitiva y entrega autorizada

Objetivo: trasladar lo demostrado en la copia a una entrega revisable, cuando
las versiones de HU13/HU31 que se integrarán estén aprobadas. Alcance: conservar
la decisión manual y auditoría de HU13, reutilizar un único reporte para
expensas automáticas o humanas y conservar Home/Expensas/Casos escalados.
Archivos previstos: `backend/app/db/reclamos.py`, `backend/app/main.py`,
pruebas de escalados/expensas y `frontend/src/App.jsx`,
`frontend/src/layouts/AdminLayout.jsx`, `frontend/src/layouts/RoleLayout.jsx`.
No modificar la rama de Talía ni habilitar por esta propuesta el botón interno
del Home; esa activación se coordina en HU31. Sin dependencias nuevas, cambios
de `.env`, migraciones compartidas adicionales ni correos reales.

Pruebas: repetir suites backend/frontend, lint/build y flujo manual con
PostgreSQL local y SMTP simulado sobre la combinación definitiva. Riesgo:
las ramas externas pueden cambiar; los ajustes temporales no deben copiarse
a ciegas ni reemplazar modificaciones posteriores. Mantener reportes únicos,
origen y auditoría como invariantes. Commit, push y PR requieren autorización
explícita; commit/push/PR fueron autorizados el 07/10. El cierre definitivo de
la HU queda para después de la revisión/integración. La guía verificable
[hu14_integracion_hu13_hu31.md](hu14_integracion_hu13_hu31.md) preserva este
contrato sin incluir las historias ajenas en el PR de HU14.

### Entrega de desarrollo — validación de la rama real

El 07/10 se confirmó otra vez que `main` sigue en `80afb67`, HU13/PR #29
abierto en `053236ac` y HU31 en su rama `f6dd2206`. No se incorporaron commits
ni archivos de esas historias al PR de HU14. El desarrollo independiente
desde main está terminado; la futura integración de esas historias no se
presenta como un merge ya realizado ni como código incluido en esta entrega.

Se añadieron dos pruebas del contrato de la factory de reporte para origen
operador/administrador: conservan origen y fundamento y omiten confianza de
LLM, incluso si un resultado anterior incluía confianza. No requieren
importar la implementación pendiente de HU13.

Suite final de la **rama real**: backend **387 aprobadas, 26 omitidas y
18 avisos previos**, frontend **122 aprobadas en 26 archivos**, lint/build
aprobados. No confundir estos resultados con las 527/214 de la combinación
temporal. La guía de frontend mantuvo componentes, tokens y navegación de
AARI; PostgreSQL/Supabase mantuvo transacciones cortas, leases y tablas privadas.

Comandos ejecutados desde los directorios correspondientes, usando runtimes
existentes; la instancia PostgreSQL dedicada estaba disponible localmente
y las flags de integración externa, SMTP/modelos y worker estaban desactivados:

```powershell
# backend/: runner compatible con el Python portátil existente
.\.venv\python.exe -c "import sys; from pathlib import Path; sys.path.insert(0,str(Path.cwd())); import pytest; sys.exit(pytest.main(['-q','--tb=short','-p','no:cacheprovider','--basetemp',sys.argv[1]]))" RUTA_TEMPORAL_NUEVA
# frontend/
npm run test
npm run lint
npm run build
```

Se revisaron diff, formato y exclusión de secretos antes de publicar. No se
incluyen `.env`, dependencias, dist, output ni copias de revisión de otros PR.
Las migraciones ya aplicadas no se repiten. Recepción SMTP real y recorrido
funcional previos siguen acreditados arriba; no se enviaron nuevos mensajes.
Tiempo confirmado permanece en **1 h 20 min**; no se infiere tiempo adicional.

### Publicación y cierre de nuestro desarrollo — 07/10/2026

- Rama subida: `codex/AARI-157-derivacion-expensas`, base `main` en `80afb67`.
- Commit de implementación: `734386b6197c45a15d1c976b4389e27a48f18dfa`.
- [PR #30](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/30)
  publicado y verificado abierto, no borrador, con revisión solicitada a Talía.
  La conexión GitHub no permitía crear PR (403); se publicó mediante la sesión
  autenticada del navegador, sin cambiar permisos ni crear credenciales.
- Doce subtareas **AARI-158 a AARI-169 listas**, verificadas tras el cierre
  autorizado de nuestro desarrollo. La HU **AARI-157 sigue En curso** hasta
  revisión e integración; ni el PR ni las dependencias se fusionaron.
- Tiempo real sin cambios: **1 h 20 min**. No se agregó ni estimó otra entrada.
- Solo archivos HU14 y seguimiento del Sprint en la entrega. El cambio previo
  de documentación HU11 y las carpetas de revisión/output quedan fuera del PR.
- README, esta evidencia y contrato de integración actualizados. Notion sigue
  bloqueado por su límite de bloques; el ADR se conserva aquí para sincronizar
  cuando el espacio admita escrituras.

El commit posterior de documentación registra esta entrega sin cambiar código
ni migraciones; las validaciones 387/122 corresponden al código publicado.
La revisión de Talía y la integración de las versiones aprobadas HU13/HU31
son los siguientes pasos externos, no pruebas de desarrollo omitidas.

## Decisión técnica y pendientes

Se descartó enviar SMTP dentro del grafo/transacción porque bloquearía peticiones
y locks. Se descartó marcar derivado antes del envío por informar un éxito falso.
Se conserva el estado previo y una alerta explícita ante fallos. La copia del
reporte evita reconstruir auditoría con datos que cambiaron después; las notas
se mantienen separadas para no filtrarlas a correos o portales personales.

Pendientes para entrega definitiva:

1. SMTP real y recepción confirmados; no quedan pruebas de correo pendientes
   para este alcance ni se autorizan envíos adicionales por esta comprobación.
2. Coordinación de integración con HU13/HU31 cuando se apruebe su
   combinación definitiva; la prueba temporal ya demostró el circuito.
   HU13 confirma clasificaciones humanas en un helper compartido: al integrar,
   conservar su auditoría/origen y reutilizar esta misma cola para expensas
   humanas, sin LLM. No se fusionaron ni editaron las ramas de Talía.
3. Revisión de Talía e integración del PR #30 antes del cierre definitivo de HU.
4. Registro en Notion cuando el espacio permita escrituras; mientras permanece
   bloqueado por el límite de bloques, este documento conserva el ADR y pruebas.

Las subtareas se cerraron por autorización explícita tras validar y publicar;
la HU principal no se cierra antes de revisión/integración ni se registran
minutos automáticamente.
