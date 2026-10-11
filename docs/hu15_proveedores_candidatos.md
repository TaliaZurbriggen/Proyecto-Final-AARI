# HU15 / AARI-170 — Proveedores candidatos

Estado: HU En curso en Jira. Implementación validada; publicación y creación
del PR autorizadas por Talía el 11/10/2026. Pendiente de revisión y merge.
Propuesta inicial aprobada el 09/10/2026 y alcance automático corregido/aprobado
el 11/10/2026. Rama `codex/AARI-170-proveedores-candidatos`,
desde `main` `fb3a496`. Estimación vigente: 5 HH, sin reestimación. Se registraron
2 HH reales iniciales por indicación de Talía: 20/15/10/20/5/10/25/5/10 minutos en
AARI-171 a AARI-179, respectivamente. El 11/10 se registraron **2 HH adicionales**
autorizadas: AARI-171 25 min, AARI-172 5 min, AARI-173 10 min, AARI-174 10 min,
AARI-176 15 min, AARI-177 30 min, AARI-178 5 min y AARI-179 20 min. No se agregó
tiempo a AARI-175 por esta ampliación. **Total real acumulado: 4 HH**; no se
reestimó la HU ni se duplicaron horas en la historia padre.

## Alcance y decisiones aprobadas

HU15 obtiene proveedores candidatos; no elige un presupuesto, confirma
disponibilidad, reserva visitas ni envía WhatsApp. Mantiene intactos el gasto,
actor responsable, confianza y fundamento de clasificación.

Se usa una búsqueda determinista para filtrar el padrón: proveedor activo,
especialidad por ID y cobertura de la propiedad. Ese filtrado no necesita un LLM.
El clasificador de gasto no completa `tipo_id` y se conserva sin cambios.
Un grafo separado identifica la especialidad faltante a partir de descripción
y catálogo, siempre que la consulta externa esté habilitada/autorizada. Reutiliza
especialidades registradas sin consumir Gemini. Una respuesta ambigua, varias
especialidades, ID inventado, evidencia ausente/inventada o error requieren revisión,
sin un valor por defecto ni reintentos ciegos. El personal puede corregir el dato.

Provincia y localidad deben coincidir completas, ignorando mayúsculas y
espacios de extremos. Se admite cobertura completa de esa localidad o el barrio
exacto de la propiedad dentro de la misma cobertura. No se mezclan barrios
homónimos de localidades distintas. Si falta barrio, sólo se admiten proveedores
que cubran toda la localidad. Los horarios habituales son informativos, no una
agenda de turnos libres. Orden estable por nombre e ID; sin duplicados aunque
varias coberturas coincidan.

## Circuito y dependencias

Talía aclaró y aprobó que obtener candidatos es independiente de contratar:
se permite desde `Recibido`, sin gasto, responsable ni aprobación. Las restricciones
iniciales a `Pendiente de asignación` se reemplazan: mezclaban HU15 con decisiones
posteriores. Reclamos cerrados, rechazados, derivados a proveedor externo o con
sesión expirada son consultables, pero no admiten una nueva búsqueda.

El worker productivo de HU15 descubre trabajos persistidos, ejecuta LangGraph
`identificar_especialidad -> buscar_proveedores_compatibles`, y confirma búsqueda,
especialidad, auditoría y resultado de tarea en una transacción. No depende de
presionar un botón ni de HU16/HU17. El puerto `search_from_coordination()` se
conserva para HU21; HTTP no puede suplantar al agente ni un usuario arbitrario.

La búsqueda conserva cualquier estado actual: encontrar candidatos no
significa haber seleccionado uno. El resultado se registra en una auditoría
propia, sin inventar una transición de estado. HU19 consume los candidatos y
debe revalidar el padrón; la auditoría histórica no acredita disponibilidad
actual. La selección definitiva corresponde al flujo posterior.

## API y consistencia

Rutas privadas de administrador/operador activo con primer ingreso completado:

- `GET /reclamos/pendientes-asignacion`: cola por antigüedad, búsqueda y páginas.
- `GET /reclamos/especialidades-proveedores`: catálogo compartido, sin abrir
  permisos de edición del padrón al operador.
- `GET /reclamos/{id}/proveedores-candidatos`: candidatos paginados y auditoría
  independiente (10 intentos por página). No escribe ni encola avisos.
- `POST /reclamos/{id}/buscar-proveedores`: comando explícito con `request_id`,
  `expected_updated_at` con zona horaria y `especialidad_id` opcional para el
  puerto automático. El formulario exige una especialidad del catálogo.

El POST bloquea y revalida usuario/reclamo, estado y versión. Especialidad,
auditoría y eventual aviso se confirman juntos o se revierten juntos.
Repetir el mismo intento y datos devuelve el resultado anterior sin duplicarlo;
reutilizar el ID con datos diferentes, una versión vieja o una etapa incompatible
devuelve 409. Una especialidad desaparecida devuelve 422 visible en su selector.

El GET de detalle usa una vista PostgreSQL `REPEATABLE READ`: los IDs, los datos
hidratados y los totales corresponden al mismo snapshot aunque el padrón se
edite simultáneamente. Una nueva consulta sí refleja la edición.

Resultados: `candidatos_encontrados`, `sin_candidatos`,
`especialidad_pendiente` o `ubicacion_incompleta`. Ante faltantes, el aviso usa
la outbox existente, prioriza operador asignado habilitado, otro operador y
administrador. Sin destinatario se informa `sin_destinatario`, nunca un envío
ficticio. Una misma combinación de reclamo/criterios/resultado no vuelve a
encolar el aviso. `encolado` no equivale a entregado; los reintentos de SMTP son
responsabilidad del worker existente y no se ejecutaron en estas pruebas.

## Interfaz

Acceso Candidatos en ambos portales de personal, listado y detalle con acción explícita
Revisar proveedores. Mantiene búsqueda/página al volver y tiene retorno seguro
cuando se abre directamente. El detalle separa especialidad, candidatos y
búsquedas registradas y estado del agente (pendiente/procesando/completada/revisión).
La corrección manual queda como apoyo; no ofrece botones de asignación o reserva.

Se reutilizaron los componentes y tokens de la skill frontend de AARI: tarjetas,
paleta, estados, navegación móvil y foco accesible. Las respuestas tardías se
descartan y una consulta fallida no deja resultados viejos a la vista. El intento
se conserva al reintentar un fallo de red; doble envío se bloquea mientras guarda.

Revisión visual con datos ficticios y API simulada local: escritorio 1280 px,
móvil 390 px, formulario, búsqueda con/sin candidatos, menú, historial y acceso
con teclado. Sin scroll horizontal observado en ambas anchuras. Esta revisión
no sustituye las pruebas SQL reales separadas ni una validación en Supabase.

## Persistencia y seguridad

Nueva migración `20261009120000_hu15_proveedores_candidatos.sql`: auditoría
de criterios, especialidad anterior/nueva, origen/usuario, candidatos y resultado,
con unicidad de intento, FK, índices y RLS/revocación de permisos públicos.
Es aditiva, no convierte datos previos ni agrega políticas públicas.
**Aplicada con autorización el 11/10/2026 en Supabase de desarrollo**, con
historial `20261009120000_hu15_proveedores_candidatos`. La cola requiere esta
tabla para funcionar; no repetir la migración por integrante o pull.
La ampliación agrega `20261011160000_hu15_busqueda_automatica.sql`, **aplicada y
registrada con autorización el 11/10/2026 en Supabase de desarrollo**. No modifica
la migración base ni la evidencia histórica. Nuevas variables sin secretos en `.env.example`:
`PROVIDER_CANDIDATES_WORKER_ENABLED=false`, `PROVIDER_SPECIALTY_EXTERNAL_ENABLED=false`
y `PROVIDER_SPECIALTY_MODEL` opcional. Sin nuevas dependencias.

Componentes principales: `provider_candidates` en API/esquemas/repositorio,
`provider_candidates_service`, consulta de candidatos en `db/proveedores.py`,
rutas y pantallas `PendingAssignmentPage`/`ProviderCandidatesPage`.

## Pruebas y evidencia (09/10/2026)

Entorno Python limpio instalado desde `backend/requirements.txt`; `pip check`
sin incompatibilidades. La instancia PostgreSQL 18 temporal escucha únicamente
en loopback; los tests crean bases aisladas con registros sintéticos y las
eliminan al terminar. No se usó Supabase, Storage, Gemini, SMTP ni WhatsApp.

Desde `backend/`, con `DATABASE_URL=sqlite://` y workers deshabilitados:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_provider_candidates.py tests/test_provider_candidates_postgres.py
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pip check
```

Las pruebas SQL requieren `AARI_TEST_POSTGRES_URL` dirigido exclusivamente a un
PostgreSQL local dedicado; sin esa variable se omiten. No usar una URL de
Supabase ni otra base compartida en estos tests.

Desde `frontend/`:

```text
npm test -- --pool=threads --maxWorkers=4
npm run lint
npm run build
```

El pool de threads evita el fallo de arranque de forks en este Windows; no se
omitieron pruebas para resolverlo. La suite frontend completa pasó 328 pruebas.
Lint y build correctos. El archivo de dependencias no cambió; la instalación
informó avisos de vulnerabilidad preexistentes y no se ejecutó `audit fix`.

Backend focalizado inicial: 60 aprobadas (49 unitarias, 11 PostgreSQL), sin
servicios externos. Una primera pasada SQL detectó una referencia a columna
incorrecta; se corrigió a `proveedor_seleccionado_id` y se repitió con éxito.
Se agregó después la regresión de lectura consistente ante baja concurrente.
Backend completo con PostgreSQL local: **871 aprobadas, 37 omitidas**, 18 avisos
preexistentes del adaptador de fechas SQLite. Las omitidas corresponden a
validaciones opcionales/externas no habilitadas; no se consumió cuota.

Cobertura: permisos/primer ingreso, rutas, validaciones de comando, cobertura
exacta, sin duplicados, faltantes, lectura sin efectos, clasificación intacta,
rechazo de versiones viejas, idempotencia, dos solicitudes simultáneas,
rollback completo ante fallo de auditoría y RLS/permisos de la migración.

## Validación autorizada en Supabase (11/10/2026)

Se aplicó y registró la migración, sin conversión de datos. Los conteos de las
trece tablas previas se conservaron durante la operación. Se verificaron los
cinco índices, cuatro FK, unicidad y siete CHECK válidos, RLS activo, ausencia
de políticas públicas y ausencia de permisos de anon/authenticated.

Desde `backend/`, indicando el archivo local de configuración existente (no
copiar credenciales a comandos, documentación ni Git):

```text
.venv/Scripts/python.exe scripts/check_provider_candidates_postgres.py --env-file <ruta-al-env-local> --mode check
.venv/Scripts/python.exe scripts/check_provider_candidates_postgres.py --env-file <ruta-al-env-local> --mode apply
.venv/Scripts/python.exe scripts/check_provider_candidates_postgres.py --env-file <ruta-al-env-local> --mode test
```

`apply` y `test` sólo se ejecutan con autorización específica. No volver a
aplicar al hacer pull: el historial evita repeticiones y una instalación parcial
detiene el script, no se repara silenciosamente.

Resultado final de `test`: **10 aprobadas**, sin omitidas, en 228,02 segundos.
Se probaron consultas sin efectos, cobertura exacta/proveedor activo,
paginación, preservación de clasificación/responsable/historial, auditoría,
idempotencia, deduplicación del aviso, origen agente del servicio, etapas
incompatibles, versión vieja, especialidad inexistente, usuario inactivo,
rollback ante fallo de auditoría y HTTP con roles administrador/operador.
El origen agente se prueba mediante el servicio: no acredita integración del
grafo de coordinación ni presentación de opciones al responsable.

Cada caso creó sólo sus personas, dos reclamos, especialidad y proveedores
sintéticos en una transacción externa. Los números se pasaron explícitamente
para no consumir la secuencia real. Los commits de aplicación liberaron
savepoints; el rollback externo y las consultas posteriores verificaron que
no persistieran las filas propias ni sus relaciones/avisos. No se modificaron
personas/reclamos existentes. Gemini, SMTP y Storage estaban bloqueados.

Las primeras ejecuciones detectaron errores de montaje del nuevo fixture, no
se informaron como aprobadas: nombres de campos de horario, clave de orden del
snapshot y aislamiento ya establecido en la transacción externa. Se corrigió
el fixture sin cambiar código de producción. Asimismo, `now()` del trigger es
estable dentro de esa transacción: la prueba HTTP usa una versión explícitamente
anterior, mientras la concurrencia entre transacciones independientes queda
cubierta por PostgreSQL local. Tras corregirlo se repitieron las diez con éxito.

Comprobación sin autorización externa: **49 unitarias aprobadas / 10 Supabase
omitidas**; compilación de scripts/tests y `git diff --check` correctos. Los
totales completos de backend/frontend arriba corresponden a la pasada del
09/10; no se presentan como repetidos en esta validación.

Se levantó la aplicación normal con backend en `localhost:8000` y frontend en
`localhost:5173`. Talía inició sesión; la cola real cargó correctamente y se
probó Actualizar, menú móvil y anchos sin desbordamiento (escritorio 905 px y
viewport móvil 390 px). Supabase tiene **0 reclamos en Pendiente de asignación**:
se observó el estado vacío real, no se simularon candidatos en esa sesión.
Los detalles con/sin candidatos se validaron por HTTP real contra el fixture;
su revisión visual poblada previa usaba API simulada. No se confunden ambas
evidencias. No se validó todavía el recorrido automático completo del Sprint.

Ambos workers se deshabilitaron explícitamente para esta sesión mediante
`NOTIFICATION_WORKER_ENABLED=false` y `CONTRACT_ANALYSIS_WORKER_ENABLED=false`.
No subir archivos de configuración ni habilitar procesos externos sólo para
demostrar la pantalla. No hubo llamadas a Gemini, correos, WhatsApp, commit,
push ni cierre de tareas.

## Automatización aprobada el 11/10/2026

El worker está conectado al ciclo de vida de FastAPI con activación explícita.
Cada 15 segundos descubre altas/cambios relevantes, incluidos los ocurridos con
el servidor detenido. La huella usa descripción, propiedad, especialidad y
ubicación, no `updated_at`, estado ni autorizaciones: escribir el rubro resuelto
no genera un bucle. Un cambio de ubicación/descripción habilita otra entrada;
una modificación administrativa irrelevante no repite una llamada.

Reserva sólo un trabajo cuando va a procesarlo, por 180 segundos, renovado cada
30. Comprueba token y vigencia antes de la llamada y al finalizar. Ante cambio de
entrada, cierre, pérdida de reserva o corrección manual se descarta el resultado.
Si la reserva vence, queda en revisión y se avisa al personal sin reintento
automático ni afirmar que se completó. No se sostiene una transacción SQL durante
la consulta al modelo. Finalizar bloquea reclamo/ubicación y tarea, preservando
consistencia, y la persistencia de candidatos mantiene idempotencia y rollback.

Prompt separado `prompt_especialidad_proveedores_v1.md`. Sólo envía descripción
y catálogo (sin agregar contratos, fotos, dirección, identidad ni contactos).
La descripción libre puede contener datos personales: no habilitar el permiso
externo con reclamos reales sin acordar su tratamiento. Una respuesta aceptada
debe indicar un ID del catálogo y evidencia literal de la descripción; estos
controles no garantizan precisión semántica. SDK con timeout 30 s y reintentos 0.
El diagnóstico real de Gemini y su cuota requieren una prueba externa autorizada.

Componentes nuevos: `agents/provider_candidates.py`, `provider_candidates_worker`,
`db/provider_candidates_jobs.py`, migración incremental y pruebas del grafo,
worker y concurrencia local. La consulta sigue mostrando el padrón actual; la
auditoría conserva los candidatos encontrados en cada búsqueda para HU19/HU21.
No hay un segundo paso de selección antes de los presupuestos: HU19 solicita
cotizaciones y HU20 presenta/elige. No se amplió el acceso a contactos del padrón
en portales de inquilinos/propietarios; su presentación comercial se integra en
esas HU, con validación del responsable. HU15 deja la lista disponible al flujo.

## Validación final de la automatización (11/10/2026)

Con la autorización de Talía se aplicó únicamente la migración incremental.
Los conteos de las trece tablas previas y la auditoría base se preservaron;
historial, RLS, ausencia de políticas públicas y permisos anon/authenticated,
FK, unicidad, cinco CHECK e índice válido fueron verificados. No se activó el
worker sobre los reclamos existentes ni se cambiaron archivos `.env`.

Pruebas y comandos, desde `backend/` (con configuración local, nunca claves en
el comando):

```text
.venv/Scripts/python.exe -m pytest -q --tb=short
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe scripts/check_provider_candidates_automatic.py --env-file <ruta-al-env-local> --mode test
.venv/Scripts/python.exe scripts/check_provider_specialty_gemini.py --env-file <ruta-al-env-local> --execute-authorized
```

- Backend final completo: **911 aprobadas / 51 omitidas**, 47,20 s, sin fallos.
  Incluye PostgreSQL 17 local dedicado, 18 regresiones SQL del worker automático
  y las regresiones anteriores del proyecto. Las omitidas son pruebas opcionales
  o externas no activadas en la suite general. Permanecen 18 avisos preexistentes
  del adaptador datetime de SQLite. `pip check`: sin incompatibilidades.
- Supabase autorizado: **14 aprobadas**, 341,15 s. Repite las diez regresiones
  base y agrega cuatro del worker: búsqueda desde Recibido sin gasto/responsable,
  catálogo/ubicación exactos, origen agente, una sola ejecución, aislamiento,
  falta de permiso externo, ambigüedad y fallo simulado 503 con revisión/aviso.
  Cada prueba hizo rollback externo y verificó ausencia de sus personas,
  reclamos, relaciones, auditoría, avisos y tareas. Sin secuencias reales ni
  procesamiento de reclamos ajenos. Gemini, SMTP y Storage reales bloqueados.
- Gemini: **una invocación real**, sin reintentos, con el adaptador y grafo
  productivos. Texto ficticio aprobado: «Pierde agua la cañería debajo de la
  pileta»; catálogo ficticio de Plomería/Electricidad/Cerrajería. Modelo local
  configurado `gemini-3.5-flash`, prompt `especialidad_proveedores_v1`. Seleccionó
  el ID de **Plomería**, con evidencia literal válida. No se enviaron contratos,
  contactos, fotos ni reclamos existentes. Esto comprueba conexión/esquema y
  ese ejemplo, no acredita precisión general del identificador de especialidad.
- Frontend focalizado: **16 aprobadas**. Suite completa final:
  `npm test -- --pool=threads --maxWorkers=2` → **332 aprobadas**, 36 archivos,
  122,64 s. `npm run lint` y `npm run build`: correctos.
- Compilación Python de aplicación/scripts/tests y `git diff --check`: correctos.

Una pasada previa de la suite frontend tuvo dos timeouts en pruebas preexistentes
(contratos y filtros de propiedades). Se repitió la suite completa con menor
concurrencia sin modificar esas pruebas ni ocultar fallos. Asimismo, la nueva
prueba de alcance QA inicialmente creaba dos reclamos activos para el mismo
inquilino/propiedad, violando una restricción válida: se corrigió el fixture con
otra unidad/inquilino ficticios y se repitió todo el backend con éxito.

Revisión visual adicional: frontend y API HU15 reales en puertos temporales,
PostgreSQL local ficticio y modelo simulado. La pantalla mostró un reclamo
Recibido, sin gasto ni responsable, con dos proveedores compatibles y una
búsqueda de origen agente, sin acción manual previa. Se comprobó escritorio
1280 px, móvil 390 px, menú desplegable, corrección accesible por teclado y
ausencia de scroll horizontal. No se presenta esta vista como una llamada real
a Gemini: la consulta real autorizada es la prueba sintética separada anterior.

La skill frontend de AARI guió la reutilización de tarjetas, tokens, estados,
menú móvil y foco; no se alteró la estética general ni se agregó otro sistema
visual. Los servicios temporales de QA no reemplazan la app habitual. Al terminar
se cerraron los dos servicios temporales y su pestaña, se retiró exclusivamente
la base ficticia restante y se detuvo el contenedor PostgreSQL dedicado. No se
eliminó información del equipo ni se modificó la aplicación habitual.

Notion: Hub existente actualizado. No se pudo agregar el ADR como bloque nuevo
por el límite gratuito; la decisión completa y las pruebas quedan preservadas
en este documento versionable, sin contratar planes ni borrar documentación.

## Ampliación: muchos proveedores (11/10/2026)

Talía pidió verificar el comportamiento con un padrón grande. Se añadió
únicamente `tests/test_provider_candidates_volume_postgres.py` y documentación;
no se modificó el filtrado, el prompt ni el código productivo. La autorización
de estas pruebas no se interpretó como autorización para contactar proveedores.
El padrón no se transmite al LLM: el modelo identifica la especialidad y SQL
resuelve activo/especialidad/cobertura. El contacto y la solicitud de presupuestos
siguen fuera de HU15, en las historias siguientes.

El fixture genera doce grupos del mismo tamaño: cobertura de toda la localidad,
barrio exacto, varias especialidades/coberturas, inactivos, otra especialidad,
otra localidad, otra provincia, barrio parecido, sin cobertura (dato heredado),
provincia/localidad repartidas en coberturas diferentes, caracteres literales
`%`/`_` y diferencias de mayúsculas/espacios de extremos. Las listas esperadas se
definen por grupos explícitos, independientemente del predicado SQL productivo.

Resultado focalizado final: **23 aprobadas**, sin fallos ni omitidas, en 587,05 s.
Compara todos los IDs auditados, no sólo la primera página. Cubre:

- Once combinaciones geográficas, incluidos barrios homónimos, ausencia de
  barrio, localidad sin cobertura y texto que no puede alterar el SQL.
- Cambio de especialidad y proveedor con varios rubros, sin mezclar los IDs.
- Todas las páginas con tamaños 20, 37 y 100: orden estable (nombre e ID),
  sin duplicados ni pérdidas; repetición y página fuera de rango sin escrituras.
- API real con página de 100, totales completos y rechazo de tamaños mayores
  a 100 o página cero. No se levantó un servidor público ni se omitió seguridad.
- Worker/grafo real, con modelo simulado: **400 candidatos de 1.200 proveedores**
  y **4.000 de 12.000**, exactamente los esperados. Una invocación por reclamo,
  sin enviar al modelo el padrón ni sus teléfonos/IDs. Auditoría de origen agente,
  sin selección, presupuesto, visita ni cambios de gasto/responsable/estado.
- Baja de 100 proveedores y cambio de cobertura de otros 100: el listado actual
  pasa de 400 a 200, pero la auditoría conserva los 400 encontrados anteriormente.
- Ocho workers concurrentes para un reclamo: una única invocación simulada y
  una búsqueda registrada; los otros siete no duplican el trabajo.

Lecturas de primera página de 20, diez repeticiones por tamaño; medición
orientativa en PostgreSQL 17 local, después de crear el padrón:

| Proveedores | Candidatos correctos | Consultas SQL/lectura | Mediana (ms) | Percentil 95 (ms) |
| --- | --- | --- | --- | --- |
| 120 | 40 | 10 | 18,60 | 28,98 |
| 1.200 | 400 | 10 | 17,03 | 20,51 |
| 12.000 | 4.000 | 10 | 59,98 | 79,22 |

El número de consultas no crece por proveedor (sin N+1). Los tiempos incluyen
repositorio/hidratación/validación de respuesta, no la llamada al LLM, la creación
del padrón, Internet ni el render del navegador. Diez muestras y una máquina
local no acreditan un SLA en la nube ni una prueba de carga de usuarios. El tiempo
total de pytest tampoco se presenta como latencia de búsqueda.

Comando focalizado, con `DATABASE_URL=sqlite://`, workers apagados y
`AARI_TEST_POSTGRES_URL` dirigido **sólo** a la instancia local dedicada:

```text
.venv/Scripts/python.exe -m pytest -q -s --tb=short tests/test_provider_candidates_volume_postgres.py --junitxml=artifacts/hu15_volumen_20261011.xml -o junit_family=legacy
.venv/Scripts/python.exe -m pytest -q --tb=short --ignore=tests/test_provider_candidates_volume_postgres.py
```

La segunda orden repitió todas las regresiones previas: **911 aprobadas / 51
omitidas**, 48,12 s, con los mismos 18 avisos preexistentes de SQLite. Se separó
el volumen para no mezclar sus mediciones con otra carga ni duplicar el padrón
grande. Entre ambas ejecuciones se aprobaron **934 pruebas**; no se presenta
como el resultado de una única invocación de pytest. La primera pasada focalizada
había aprobado 22; se amplió con comparación de todos los IDs en cada escenario
y grafo con 12.000 proveedores, y se repitieron las 23 finales con éxito.

El XML detallado queda en `backend/artifacts/` (ignorado por Git); este resumen
conserva las mediciones en el proyecto. Se bloquearon expresamente los adaptadores
Gemini, SMTP y Storage reales. No hubo llamadas nuevas a Gemini, datos escritos
en Supabase, mensajes, worklogs, commit, push ni cierre de Jira. La conexión real
y las catorce pruebas en Supabase son la evidencia separada anterior. Estas
pruebas acreditan elegibilidad técnica; no disponibilidad actual de una persona
ni precisión general del modelo ante descripciones nuevas.

## Pendientes antes de cerrar la HU

1. Publicar el commit/PR autorizados y obtener revisión de Tobías antes del
   merge. La autorización de publicar no autoriza fusionar ni cerrar Jira.
2. Para el uso automático habitual, habilitar el worker y, si se autoriza el
   tratamiento de descripciones reales, su permiso externo en el servidor. La
   migración y pruebas están completas; ambos permisos siguen apagados por defecto.
3. Selección, presupuestos, disponibilidad y visitas pertenecen a las HU
   siguientes; no se consideran implementados ni probados por esta entrega.

Jira AARI-170 está En curso y las decisiones se registraron en el Hub de Notion.
No se cerraron subtareas ni se registró tiempo estimado como si fuera real.
