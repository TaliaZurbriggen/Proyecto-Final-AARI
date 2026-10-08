# HU31 / AARI-332 — Home del administrador

**Fecha:** entrega inicial 05/10/2026; integración y revalidación 07/10/2026.

**Estado:** implementación y conexión con HU13 validadas; publicación de la continuación autorizada el 07/10, pendiente revisión del PR e integración.

**Rama:** `codex/AARI-332-home-administrador`

**Base inicial:** `origin/main` en `80afb67`, con HU11. **Base actual:** `69d0ec6`, con HU14, HU30 y HU13 integradas.

**Jira:** HU y subtareas AARI-333 a AARI-337 en curso. Se verificaron 3h 15m acumuladas: 2h iniciales más 1h 15m adicional autorizada el 07/10; sin duplicar tiempo en la HU padre ni cambiar la estimación original del Sprint.

**Publicación:** entrega del 05/10 en `f6dd220`. Rebase autorizado el 07/10; esa entrega se recreó localmente como `435812b`. La persona responsable autorizó el commit/push de la continuación después de su revisión final, usando un lease explícito sobre el head remoto anterior. No se autorizó cerrar la HU o fusionarla. El identificador de la entrega queda en Git y en el comentario de Jira.

## Objetivo y alcance aprobado

Un punto de entrada para que administración conozca la situación operativa y
continúe sus tareas. Se implementa la variante **Operativo** aprobada: dos
resúmenes de reclamos, una región con cinco módulos y accesos a contratos e
historial. No es el dashboard analítico de HU26: no hay gráficos, tendencias,
predicciones ni comparaciones por período.

Al entrar con rol administrador se dirige a `/inicio`. La identificación usa
la sesión existente. El primer ingreso exige cambiar la contraseña antes de
ver el Home. Los portales de operador, propietario e inquilino se conservan;
ni la ruta ni el endpoint del resumen están habilitados para esos roles.

## Decisiones y alternativas

### Navegación compartida

El equipo eligió tarjetas compactas y redondeadas en escritorio y un menú
desplegable en móvil. Se implementan en la misma cabecera administrativa y
con una única navegación, no como una barra lateral ni como menús duplicados.
El desplegable indica el módulo actual y se cierra al elegir una opción,
pulsar fuera o presionar Escape; Escape devuelve el foco a su botón.

Se aplica la skill `.agents/skills/aari-frontend`: tokens de la paleta,
Inter, CSS Modules, iconos Lucide y componentes existentes. La variante de
pestañas sigue disponible para los demás layouts. El Home no presenta un
buscador global ni una campana sin comportamiento propio; los módulos
conservan sus controles actuales.

### Contadores reales y consistentes

`GET /admin/resumen` es de solo lectura y reutiliza `require_admin`.
Obtiene todos los agregados con **una sola sentencia SQL**, para que compartan
la instantánea de la consulta. No obtiene listados completos ni suma páginas
del frontend. Los agregados tampoco multiplican proveedores por coberturas o
reclamos por relaciones asociadas. No se añaden tablas ni migraciones.

| Dato | Regla aplicada |
|---|---|
| Propietarios, propiedades e inquilinos | Total de registros de cada tabla, no solamente registros activos. |
| Proveedores | Total registrado y subconjunto con `activo = true`. |
| Operadores | Usuarios con `rol = 'operador'`, más su subconjunto activo; no cuenta administradores. |
| Reclamos activos | Todos salvo `Resuelto` y `Resuelto (sin confirmación)`, según la regla ya usada en el alta de reclamos. Un reabierto sigue activo. |
| Pendientes de clasificación | Estado `Escalado` o `Clasificación pendiente`, sin `tipo_gasto`, sin origen de decisión `operador`/`administrador` y sin fila en `reclamo_responsables`. |

Los pendientes de clasificación **están incluidos** en los activos; no se
suman para obtener otro total. Se excluyen los escalados de etapas posteriores
que ya tienen clasificación o solicitud de responsable. La regla coincide
con la cola de clasificación implementada en HU13, no con una cola general de
todas las incidencias posibles.

La respuesta incluye `consultado_en` con zona horaria. La interfaz presenta
la fecha y hora mediante `America/Argentina/Buenos_Aires`, independientemente
de la zona horaria del servidor o del navegador.

### Actualización, carga y errores

Se consulta al entrar, al volver desde otro módulo y al pulsar **Actualizar**. No hay sondeo periódico.
Mientras se carga, el botón está deshabilitado y los contadores muestran `—`.
Una base vacía correctamente consultada muestra cero y una invitación a
registrar datos. Un fallo, una respuesta incompleta o contadores incoherentes
no se convierten en cero: se retiran los valores anteriores, se informa el
error y se permite reintentar, manteniendo los accesos a los módulos.

Al salir se cancela la solicitud; una respuesta atrasada no reemplaza la
información de una pantalla nueva. El backend no expone detalles SQL ni de
conexión cuando el repositorio falla: responde HTTP 503 con un mensaje seguro.

### Integración con HU13 — completada el 07/10/2026

Al crear esta rama, HU13 aún no estaba fusionada en `main`. La persona
responsable aprobó explícitamente continuar y completar su conexión después.
Por eso la entrega inicial mantuvo **Revisar casos** deshabilitado. Tras el
merge de HU13 se actualizó esta rama mediante rebase desde `main`; no se
cherry-pickeó ni se modificó trabajo de la rama de HU13.

Ahora **Revisar casos** es un enlace real a `/escalados`, con los estilos y
foco del botón primario existente. Permite teclado y navegación nativa sin
duplicar la cola o su formulario. Se mantiene disponible con cero pendientes,
durante carga y ante errores del resumen; esos estados no anulan un acceso válido.

El recorrido es Home → cola → detalle → clasificación manual → Home.
Al volver se consulta nuevamente el resumen: el caso sale de pendientes,
pero sigue activo hasta resolver la reparación. La decisión conserva la
auditoría, el contexto contractual previo y la continuidad de notificaciones
de HU12/HU14. No se añade sondeo periódico, mutación de contadores en el cliente
ni una nueva interpretación automática del contrato.

El historial sí tiene acceso funcional: **Buscar propiedad** abre el listado
de propiedades, desde donde la ficha permite ir al historial de HU11. No se
crea un listado global de reclamos en esta HU. Contratos abre el módulo de HU29.

## Componentes principales

- `backend/app/api/admin_home.py`: endpoint privado y error seguro.
- `backend/app/db/admin_home.py`: agregación SQL del resumen.
- `backend/app/schemas/admin_home.py`: contrato tipado, contadores no negativos
  y validación de subconjuntos.
- `backend/app/main.py`: registro del router, sin alterar los anteriores.
- `frontend/src/features/home/`: API, pantalla operativa, estilos y pruebas.
- `frontend/src/features/auth/routing.js` y `frontend/src/App.jsx`: destino
  inicial y ruta protegida.
- `frontend/src/layouts/AdminLayout.jsx` y `components/layout/AppHeader.*`:
  navegación responsive compartida y acceso Inicio.

## Validaciones de la entrega inicial — 05/10/2026

Todas las validaciones de esta ejecución son locales. No se consultó ni
modificó Supabase, ni se consumió Gemini, Storage o SMTP reales. No se instalaron
dependencias. La base de prueba PostgreSQL fue creada con datos ficticios y
eliminada al terminar por el fixture de prueba.

| Validación | Resultado |
|---|---|
| Backend completo, servicios externos deshabilitados | **392 passed, 40 skipped**. |
| Backend focalizado `tests/test_admin_home.py` | **50 passed**. Incluido también en la suite completa. |
| PostgreSQL local `tests/test_admin_home_postgres.py` | **1 passed** contra PostgreSQL 17 y esquema creado con migraciones reales. |
| Frontend completo | **140 passed** en 29 archivos. |
| Lint y build frontend | Aprobados. |
| Navegador Chrome aislado | Aprobado en 1440, 1024, 768, 390 y 320 px; sin desborde horizontal. |

La prueba de PostgreSQL comprueba base vacía, totales, proveedores con varias
coberturas sin duplicación, exclusión de administradores, estados y orígenes
de reclamos, exclusión por solicitud de responsable y valores actualizados
después de cambios. Reutiliza el fixture local de HU12, que solo permite una
instancia en localhost y crea/elimina una base aleatoria aislada.

La prueba visual usa la aplicación compilada con respuestas HTTP sintéticas,
no una maqueta estática. Verifica navegación móvil y regreso, foco visible,
Escape, áreas táctiles, carga, base vacía, fallos sin datos viejos, reintento
y ausencia de errores JavaScript. Las capturas locales de QA se conservan en
`backend/artifacts/hu31/` (ignorado por Git), sin datos personales reales.

Las pruebas de rutas y endpoint incluyen sesión ausente, otros tres roles,
primer ingreso obligatorio y cuenta inactiva. Las pruebas frontend verifican
formato argentino, credenciales de sesión, accesos, respuestas inválidas y
cancelación de solicitudes.

En la suite backend quedaron 40 pruebas optativas omitidas por no habilitar
sus entornos externos o PostgreSQL dedicado. Se ejecutó por separado la
prueba PostgreSQL de HU31. Los avisos de deprecación de Starlette/httpx y del
adaptador datetime de SQLite ya existentes no impidieron la ejecución. El
build mostró un aviso de temporización de plugins de Vite, sin error de
compilación.

### Comandos reproducibles

Desde `backend/`, con dependencias ya instaladas, deshabilitar la carga del
`.env` local para evitar contactos involuntarios con servicios reales:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:DATABASE_URL='sqlite://'
$env:RUN_SUPABASE_INTEGRATION='0'
$env:RUN_CONTRATOS_POSTGRES_TESTS='0'
$env:RUN_OPERADORES_POSTGRES_TESTS='0'
$env:RUN_SUPABASE_MIGRATION_TESTS='0'
$env:RUN_HU12_SMTP_INTEGRATION='0'
$env:AARI_TEST_POSTGRES_URL=''
$env:NOTIFICATION_WORKER_ENABLED='false'
python -m pytest -q -p no:cacheprovider
python -m pytest -q tests/test_admin_home.py -p no:cacheprovider
```

Para la comprobación PostgreSQL, usar únicamente una instancia **local
dedicada**, con capacidad para crear bases y los roles locales `anon`,
`authenticated` y `service_role` sin login. No apuntar la variable a Supabase.
Configurar la URL local de prueba sin registrar su contraseña en documentación:

```powershell
# AARI_TEST_POSTGRES_URL: URL de la instancia local dedicada, configurada localmente.
python -m pytest -q tests/test_admin_home_postgres.py -p no:cacheprovider
```

Desde `frontend/`:

```bash
npm test -- --run --maxWorkers=2
npm run lint
npm run build
```

En este entorno Windows se ejecutaron las entradas CLI de Vitest, ESLint y
Vite con el runtime Node disponible, equivalentes a los scripts anteriores.
Se revisó `git diff --check` y el contenido de los archivos nuevos; no se
incorporaron claves ni configuraciones reales.

## Documentación y pendientes de cierre

### Ampliación aprobada durante la revisión (05/10/2026)

La persona responsable pidió incorporar filtros de propiedades, propietarios
e inquilinos **en esta misma rama**. Se añadieron búsqueda visible y sincronizada
en los listados de personas, panel responsive y recuperación de páginas fuera
de rango. No cambian estimaciones, dependencias ni migraciones. La validación
de la entrega del 05/10 obtuvo **429 passed / 41 skipped** en backend,
**191 passed** en frontend y **2 passed** en PostgreSQL local; lint, build y
revisión visual de los tres listados aprobados. Los resultados de la tabla
anterior corresponden al Home antes de esta ampliación.

Alcance, decisiones, pruebas, paginación y pendientes en
[`hu31_filtros_listados.md`](hu31_filtros_listados.md).

- README y seguimiento del Sprint 3 actualizados con este alcance.
- Se intentó registrar la decisión en **Decisiones técnicas (ADR)** de Notion;
  la operación falló con HTTP 403: el espacio agotó sus bloques gratuitos.
  **La publicación en Notion no está realizada.** Este documento conserva el
  contexto, alternativas y decisión para sincronizar cuando el espacio permita
  escribir, según el acuerdo de planificación del Sprint 3.
- HU y subtareas permanecen **En curso**. Se registraron **3h 15m** acumuladas,
  confirmadas por la persona responsable, sin modificar la estimación original del Sprint.
- Conexión de HU13 completada y validada el 07/10, con la navegación de
  contratos, escalados y expensas conservada. No se cambian sus migraciones
  ni las protecciones contra reclasificación o la evidencia congelada de HU30.
- Commit/push de la continuación autorizados el 07/10 tras revisar el resultado.
  Quedan revisión y PR; HU31 no se da por finalizada hasta su revisión e integración.
- No se probó la conexión del panel con el Supabase compartido: el SQL sí se
  ejecutó contra PostgreSQL real local. Una prueba externa requiere autorización.

### Registro de tiempo autorizado (05/10/2026)

El total de **2h** fue confirmado por la persona responsable. La distribución
es orientativa según el peso del trabajo realizado, no una medición automática
del tiempo por subtarea. Los worklogs se registran solo en las subtareas, sin
duplicar las dos horas en la HU padre.

| Subtarea | Actividad | Tiempo | Worklog |
|---|---|---|---|
| AARI-333 | Integración con sesión, rutas y destino administrativo. | 10 min | 10263 |
| AARI-334 | Pruebas, PostgreSQL local, revisión responsive y documentación. | 40 min | 10264 |
| AARI-335 | Home, estados, filtros, búsqueda sincronizada y paginación. | 35 min | 10265 |
| AARI-336 | Diseño responsive, navegación y ajustes visuales. | 15 min | 10266 |
| AARI-337 | Resumen privado y consultas filtradas con totales paginados. | 20 min | 10267 |
| **Total** | | **120 min / 2h** | |

## Integración y validación final local — 07/10/2026

Se aprobó retomar el trabajo tras los merges de HU30 y HU13. Se creó la
referencia recuperable `backup/hu31-before-rebase-20261007` en `f6dd220` y
se rebaseó sobre `origin/main` `69d0ec6`. Los cinco conflictos se resolvieron
conservando las dos entregas: README, seguimiento del Sprint, registro de
rutas backend/frontend y navegación administrativa. El router de contratos
mantiene su worker; se conservan los accesos y permisos de HU13/HU14.
La rama remota no se modificó en esta continuación.

Se habilitó **Revisar casos** y se agregaron regresiones del recorrido:

- PostgreSQL y HTTP reales: antes de clasificar, Home y cola tienen el mismo
  total; después la cola queda vacía y Home mantiene un reclamo activo.
  Se probaron ordinario, extraordinario y expensa para los dos roles del personal.
- Un intento repetido responde 409 y no crea otro responsable o notificación.
  Se conserva el contexto contractual y la auditoría del usuario que decidió.
  El envío se captura con un doble, sin SMTP ni cambio ficticio al estado de entrega.
- El contador coincide con el total de una cola paginada, no con el tamaño
  de la página; excluye los escalados ya clasificados o con responsable.
- Frontend: recorrido de las tres clasificaciones desde el Home, regreso
  con resumen actualizado y cola vacía; enlace válido con carga, error y cero pendientes.

| Comprobación | Comando / alcance | Resultado |
|---|---|---|
| Backend completo con PostgreSQL local | `python -m pytest -q` | **808 passed, 37 skipped**. Cero fallos. |
| Backend focalizado Home/cola/filtros | `python -m pytest -q tests/test_admin_home.py tests/test_admin_home_escalados_postgres.py tests/test_admin_home_postgres.py tests/test_admin_list_filters_postgres.py` | **58 passed**, incluidas en la suite completa. |
| Frontend completo | `npm test -- --maxWorkers=4` | **235 passed** en 34 archivos. |
| Estilo y producción | `npm run lint`; `npm run build` | Aprobados. |
| Chrome aislado | Home y tres listados en 1440, 1024, 768, 390 y 320 px; recorrido Home/cola/detalle/regreso en 1440, 390 y 320 px | Sin desborde horizontal ni errores JavaScript; teclado, menú, filtros, paginación y estados aprobados. |
| Integridad | `git diff --check`; comparación con `origin/main` | Sin conflictos/formato incorrecto. Migraciones y componentes sensibles de HU30 intactos. |

El entorno backend se aisló con `PYTHON_DOTENV_DISABLED=1`, workers y flags
externos deshabilitados, claves ficticias y URL PostgreSQL limitada a localhost.
Cada fixture elimina únicamente su base aleatoria de prueba. Las 37 omitidas
corresponden a validaciones optativas/exteriores no habilitadas en esta ejecución.
No se instalaron paquetes ni se usaron Supabase, Gemini, SMTP o Storage reales.
Los avisos preexistentes de Starlette/httpx y SQLite no impidieron las pruebas.

Los scripts y capturas sintéticas de Chrome quedan en `backend/artifacts/hu31/`
(ignorado por Git). Durante QA se ajustaron dos expectativas del script
anterior: el modo desarrollo repite consultas de lectura por StrictMode y la
cabecera completa tiene más paradas de teclado. No hubo que cambiar el producto
para satisfacerlas; todas las comprobaciones finales pasaron.

Se verificó que PostgreSQL tenía cero bases de prueba restantes. Se retiraron
únicamente el contenedor descartable y el frontend temporal de QA, sin tocar
los servicios o datos del usuario.

Se conserva el diseño de la skill visual AARI. No se añadieron nuevas
migraciones, dependencias ni variables de entorno. Jira sigue En curso con
las 2h previas: no se registró tiempo adicional ni se cerraron tareas.
README, este informe, los filtros y el seguimiento del Sprint quedaron actualizados.
Notion continúa pendiente por el límite de bloques ya informado; no se declara
publicada allí esta continuación.

Cuando se autorice publicar, el rebase requiere comprobar de nuevo el head
remoto y usar `--force-with-lease` explícito; no un force sin protección.
En la comprobación final el remoto seguía en `f6dd220` y main en `69d0ec6`.

## Ajustes aprobados durante la revisión visual — 07/10/2026

### Acceso explícito a la clasificación

La persona responsable señaló que el enlace del número no dejaba claro cómo
entrar para resolver la clasificación. Se aprobó agregar **Resolver clasificación**
en esta misma rama. Se eligió ese texto frente a «Resolver» para no confundir
clasificar el gasto con cerrar la reparación. No se cambia el alcance funcional
de HU13 ni se decide automáticamente desde la tabla.

La columna **Acciones** ofrece un enlace nativo con los estilos del botón primario
compartido. Conserva el número como enlace alternativo. Ambos llevan al mismo
detalle, mantienen la búsqueda y página para volver, y respetan las rutas de
administrador y operador. En móvil la acción ocupa el ancho de su tarjeta.
Se mantiene la skill visual AARI: tokens, CSS Modules, foco visible y controles
de al menos 44 px, sin nueva paleta o componente global.

Componentes modificados para este ajuste:

- `frontend/src/features/reclamos/pages/EscalatedClaimsPage.jsx`.
- `frontend/src/features/reclamos/pages/Escalados.module.css`.
- `frontend/src/features/reclamos/pages/Escalados.test.jsx`.
- `frontend/src/features/home/pages/AdminHomeRouting.test.jsx`.

Se agregaron tres regresiones: acceso y regreso con búsqueda/página para cada
rol, y acciones identificables para dos casos sin perder el acceso por número.
La navegación por Enter no envía una decisión; todas sus solicitudes son GET.
El recorrido del Home usa ahora la acción explícita antes de confirmar una
clasificación en el formulario. No se modifican backend, migraciones ni permisos.

| Comprobación posterior al ajuste | Resultado |
|---|---|
| `npm test -- --maxWorkers=4` | **238 passed** en 34 archivos; incluye las 24 pruebas de escalados y rutas del Home. |
| `npm run lint` | Aprobado. |
| `npm run build` | Aprobado. |
| Chrome aislado, administrador y operador | 1440, 1024, 901, 900, 768, 390 y 320 px; navegación por teclado y Enter, foco, búsqueda, regreso, paginación y área táctil aprobados. Sin desborde ni errores JavaScript. |

El primer arranque de Vitest fue impedido por permisos de su directorio temporal
en Windows. Se repitió con `TEMP` y `TMP` en el directorio local de artefactos,
sin cambiar la aplicación. La revisión de Chrome requirió ejecución fuera del
sandbox para acceder a localhost; una sesión nueva interceptó todas las APIs
con respuestas ficticias y bloqueó otros orígenes. No usó la sesión del usuario
ni servicios reales. Script y capturas en `backend/artifacts/hu31/`, ignorados
por Git. Los **808 passed / 37 skipped** del backend corresponden a la validación
anterior: no se repitió esa suite para este cambio exclusivamente de interfaz.

### Foto privada en la vista local

Esta fue una comprobación externa **separada y expresamente autorizada**, no
parte de las pruebas sintéticas anteriores. La vista devolvía 503 porque el
proceso backend cargaba un `.env` sin `SUPABASE_URL` ni
`SUPABASE_SERVICE_ROLE_KEY`; fallaba antes de solicitar la imagen a Storage.

Se comprobó, sin mostrar valores, que otro entorno local ya configurado tenía
esas variables para la misma base y sesión. Se reinició únicamente el backend
de esta vista con la configuración existente en su proceso. La descarga de la
foto ya registrada fue correcta y se validó en memoria como JPEG. No se modificó
ni creó ningún archivo o registro, ni se alteraron permisos o se hizo pública
la foto; tampoco se consumió Gemini ni se enviaron correos.

La pantalla debe recargarse después del reinicio para retirar el estado previo
de imagen no disponible. Las variables usadas en esta comprobación son del
proceso: los próximos arranques también deben cargar un entorno local con
Storage configurado. No se copian claves a este documento o al repositorio.

README y seguimiento actualizados. Notion sigue pendiente por el límite de
bloques ya informado. No se registran horas nuevas, commits, push o cierres
de Jira durante este ajuste sin autorización adicional.

## Revisión final previa a publicar y tiempo adicional — 07/10/2026

Después de aprobar el resultado visual, la persona responsable autorizó revisar
y subir los cambios. Se verificó el remoto: main permanecía en `69d0ec6` y
esta rama en `f6dd220`, sin cambios ajenos posteriores que pudieran sobrescribirse.
El rebase está completado y la actualización usa un lease explícito sobre ese
head previo; no un force sin protección. La copia previa sigue recuperable
mediante `backup/hu31-before-rebase-20261007`.

La revisión de código comprobó consultas parametrizadas y totales filtrados
antes de paginar, permisos privados, conservación de rutas y ausencia de
modificaciones a migraciones o componentes sensibles de HU30. Los cambios de
continuación incluyen el recorrido del Home, la acción visible y sus regresiones.

Se repitieron **todas las pruebas** después del último ajuste de interfaz:

- `python -m pytest -q`: **808 passed, 37 skipped, 19 warnings**, incluyendo
  PostgreSQL local y la integración HTTP de los tres gastos para ambos roles.
- `npm test -- --maxWorkers=4`: **238 passed**, 34 archivos.
- `npm run lint` y `npm run build`: aprobados.
- Chrome aislado: recorrido Home → cola → clasificación → Home → cola vacía
  en 1440, 390 y 320 px; acción, teclado, foco, regreso con búsqueda/página,
  paginación y ausencia de desborde para ambos roles en 1440, 1024, 901, 900,
  768, 390 y 320 px. Sin errores JavaScript.

Esta revisión final no consumió servicios externos. PostgreSQL usó una imagen
local ya disponible, sin descargar dependencias, un contenedor sin volúmenes
del usuario y un puerto aleatorio ligado únicamente a localhost. Los workers,
variables reales y flags de validación externa se deshabilitaron para pytest;
cada fixture eliminó su base aleatoria. Se verificaron cero bases de prueba
restantes y se retiró el contenedor descartable. La aplicación que usa el
usuario se conserva funcionando. Los avisos preexistentes no impidieron las pruebas.

Se registró la **1h 15m adicional** confirmada, solo en subtareas. El reparto
es orientativo por actividad, no un cronometraje automático; las estimaciones
originales y estados En curso se verificaron sin cambios manuales.

| Subtarea | Actividad | Adicional | Acumulado | Worklog adicional |
|---|---|---|---|---|
| AARI-333 | Rebase e integración de rutas, roles y continuidad del flujo. | 20 min | 30 min | 10275 |
| AARI-334 | Pruebas, PostgreSQL local, revisión responsive y documentación. | 30 min | 1h 10 min | 10276 |
| AARI-335 | Accesos Revisar casos y Resolver clasificación. | 15 min | 50 min | 10277 |
| AARI-336 | Adaptación visual de la acción y foco. | 5 min | 20 min | 10278 |
| AARI-337 | Coherencia de contadores con la cola antes/después de clasificar. | 5 min | 25 min | 10279 |
| **Total** | | **75 min / 1h 15m** | **195 min / 3h 15m** | |

El agregado de Jira se verificó en **11700 segundos**. La HU padre no tiene
registro duplicado. README, este documento y seguimiento del Sprint actualizados;
Notion sigue pendiente por el límite de bloques. La entrega requiere revisión
del PR antes del merge y del cierre de HU31.
