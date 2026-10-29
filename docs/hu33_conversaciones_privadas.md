# HU33 / AARI-348 — Mensajes del agente y consultas técnicas

Actualización: 29/10/2026. Propuesta revisada y aprobada por Talía.
Rama `codex/AARI-348-conversacion-solicitudes`, desde main `67b3c90` (HU19,
PR #38). Implementación, regresión local y validación transaccional en Supabase
completas. El 29/10 Talía autorizó migración, publicación y creación de PR para
revisión de Tobías. HU y ocho subtareas En curso; cierre pendiente del merge.
Estimación de 12 HH conservada; 8 HH reales informadas y registradas sólo en
subtareas. Commit/push/PR autorizados; no se autoriza fusión ni cierre.
Commit de implementación y pruebas: `f0118bb`. La documentación de entrega se
versiona en un segundo commit; el enlace del PR se registra en Jira y Notion.

## Decisión vigente: reemplaza el chat compartido inicial

Durante la revisión, Talía pidió evitar la entrada obligatoria desde el detalle
del reclamo, la intervención normal de la inmobiliaria y la conversación libre
entre responsable y proveedor. Aprobó una bandeja flotante y, como excepción,
consultas técnicas abiertas explícitamente por el proveedor antes de cotizar.

Alternativas consideradas: conservar el chat grupal del prototipo; limitar todo
a avisos sin preguntas; o separar avisos del agente y consultas técnicas
(elegida). Así se aclara el problema sin exponer al inquilino el historial
económico ni convertir una conversación informal en una decisión de gasto.

- **Avisos del agente:** hilos privados separados para proveedor y responsable
  original vigente. Se originan en hechos durables de HU19; son sólo lectura,
  no un chatbot general ni mensajes inventados por un modelo.
- **Consultas técnicas:** proveedor ↔ inquilino, incluso si paga el propietario.
  El proveedor pulsa «Necesito hacer unas preguntas»; si no existe un inquilino
  con cuenta activa, se explica el impedimento sin elegir otro destinatario.
- **Cierre explícito:** sólo el proveedor pulsa «Finalizar consultas y continuar
  presupuesto». Conserva historial en sólo lectura, no reabre el hilo y permite
  volver al formulario de presupuesto. No crea ni acepta un presupuesto.
- El formulario y el backend bloquean el envío mientras las consultas están
  abiertas. Sus borradores no se pierden al refrescar el estado del hilo.
- La inmobiliaria consulta con permisos vigentes, pero no escribe ni finaliza
  consultas en el recorrido normal. Intervenciones por escalado son otro flujo.
- Preguntas, respuestas o cierre no amplían las 24 horas ni cambian selección,
  autorización, gasto, estado del reclamo o visita.

## Dependencias y fuera de alcance

HU19 publica solicitudes y recibe presupuestos exactos/mínimos. HU20 recoge la
elección/confirmación del responsable del gasto. Después HU23 solicita
disponibilidad **al inquilino**, aunque pague el propietario, y la ofrece sólo
al proveedor seleccionado. La coordinación estructurada y su integración en
HU21/AARI-345 no se presentan como implementadas por HU33.

La finalidad `coordinacion` está reservada en el modelo, sin activación pública.
Texto libre no aprueba gasto, selecciona proveedor ni programa visitas.
No se agregan correo por mensaje, audio, adjuntos, presencia, edición/borrado de
mensajes, IA conversacional ni WebSockets. No se llama a Gemini por mensaje.

## Permisos por hilo

| Participante | Avisos del agente | Consultas técnicas |
| --- | --- | --- |
| Proveedor propio activo | Su hilo individual, lectura | Lee/escribe mientras estén abiertas; único que abre/finaliza |
| Responsable original y vigente | Su hilo individual, lectura | No obtiene acceso por ser responsable |
| Inquilino actual con cuenta activa | Sólo si también es el responsable | Lee/escribe en su hilo técnico, sin heredar el historial económico |
| Administrador | Consulta, sin escritura | Consulta, sin escritura ni cierre |
| Operador | Sólo el asignado, lectura | Sólo el asignado, lectura |
| Otros candidatos/usuarios | Sin acceso | Sin acceso |

La sesión identifica al usuario; PostgreSQL revalida cuenta, rol, primer
ingreso y vínculos. Se conserva una instantánea del participante: un nuevo
titular/inquilino no hereda el historial. El proveedor desvinculado/inactivo y
el inquilino que deja la propiedad pierden acceso. Adivinar otro ID devuelve
404. No hay destinatario, autor o etapa elegibles en el payload HTTP.

## Persistencia, lectura y concurrencia

La migración aditiva `20261028210000_hu33_conversaciones.sql` se aplicó en Supabase
el **29/10/2026**, con autorización de Talía y verificación previa de destino.
Antes de esa primera aplicación se ajustó su definición local; no se reescribieron
migraciones ya desplegadas. Desde esta aplicación no debe editarse para corregir
instalaciones existentes: cualquier evolución requiere otra migración.

Tres tablas con RLS, revocaciones a PUBLIC/anon/authenticated y sin políticas
públicas:

- `aari_conversaciones`: solicitud, finalidad, audiencia, participante original,
  secuencia, actualización e identificadores/fechas de apertura y cierre.
  Unicidad por solicitud/finalidad/audiencia.
- `aari_conversacion_mensajes`: autor/origen, nombre histórico, texto, secuencia,
  fecha, clave de reintento o evento automático. Trigger impide UPDATE/DELETE.
- `aari_conversacion_lecturas`: posición monotónica por hilo/usuario.

Reintentar la misma operación confirmada recupera el resultado; reutilizar su
clave con texto diferente devuelve conflicto. Apertura/cierre también tienen
UUID idempotente. No se reabre una consulta cerrada con otra clave.
La revalidación impide nuevas escrituras después de vencimiento, presupuesto,
cancelación, selección o cambio de ciclo/contexto.

El bloqueo del reclamo precede a los hilos, igual que HU19, incluidas las
proyecciones históricas desde la bandeja. Serializa cancelaciones, envíos y
presupuestos; la secuencia no deja huecos confirmados fuera de orden.
La proyección de eventos HU19 está en su transacción de origen: fallo revierte
todo, sin presupuesto o aviso a medias. La recuperación idempotente conserva
la fecha original y no repite efectos externos.

La bandeja usa paginación real y consultas por lote, sin una consulta por cada
tarjeta. Obtenerla no marca mensajes leídos. Sólo al abrir/leer el hilo se
confirma el tramo efectivamente recuperado, nunca mensajes futuros o páginas
omitidas. El contador administrativo no suma mensajes ajenos como propios.

## API

Todas las rutas requieren sesión, permisos vigentes y feature flag; respuestas
sin caché y errores de almacenamiento genéricos, sin SQL ni conexiones.

- GET `/conversaciones/bandeja?page=1&page_size=20`: hasta 50 hilos por página.
- GET `/conversaciones/hilos/{id}`: últimos 30 mensajes; límite 1–50,
  `antes` o `despues` excluyentes; orden estable por secuencia.
- POST `/conversaciones/hilos/{id}/mensajes`: UUID y texto de 1–2000 caracteres,
  sólo consultas técnicas abiertas; texto representado sin interpretar HTML.
- POST `/conversaciones/hilos/{id}/lectura`: posición válida y monotónica.
- POST `/conversaciones/solicitudes/{id}/consultas`: UUID de apertura.
- POST `/conversaciones/hilos/{id}/finalizar-consultas`: UUID de cierre.
- Compatibilidad `/conversaciones/solicitudes/{id}` y sus subrutas
  `/mensajes`/`/lectura`: resuelven el hilo propio de avisos, no un chat grupal;
  no permiten escribir en avisos del agente.

## Interfaz

`ConversationDockProvider` se monta una sola vez para la sesión autenticada.
Botón fijo «Mensajes», badge de no leídos, bandeja y panel de escritorio;
vista móvil amplia. No aparece al login/primer ingreso. Cambiar de usuario
descarta el estado anterior. Las pantallas de proveedor/responsable/administración
abren este mismo panel, no duplican un chat inline.

El sondeo cada 8 segundos actualiza la bandeja, se pausa con la pestaña oculta
y cancela solicitudes al desmontar/cambiar sesión. El hilo sólo se consulta
mientras está abierto. Llegar un mensaje no abre panel ni roba foco; cerrarlo
no marca leído. Error de una página nueva no deja visibles datos de otra consulta.
Los contadores de HU19 se actualizan al leer desde el panel.

Reutiliza componentes y tokens de la skill `aari-frontend`, CSS Modules,
etiquetas, foco visible y objetivos táctiles. Escape cierra/restaura foco,
Tab queda dentro del diálogo y el fondo no se desplaza al estar abierto.

## Validación vigente — 29/10/2026

- Backend completo con PostgreSQL 17 local descartable:
  `python -m pytest -q -p no:cacheprovider --tb=short` →
  **1534 passed, 62 skipped**, 376,87 s. Las omitidas no son aprobadas;
  18 advertencias preexistentes del adaptador datetime de SQLite.
- Frontend completo:
  `npm test -- --pool=forks --maxWorkers=1 --testTimeout=20000` →
  **419 passed**, 42 archivos, 170,49 s.
- Focalizadas finales de checkpoints + API de conversaciones:
  **77 passed**, 31,90 s. PostgreSQL HU33 final: **29 passed**, 30,72 s.
  Son subconjuntos/repeticiones; no sumar a la regresión completa.
- Focalizadas de componentes panel/bandeja: **24 passed**, dos archivos, 39,81 s,
  antes de los últimos ajustes cubiertos por la regresión completa.
- `npm run lint` y `npm run build`: correctos. Advertencia no bloqueante
  conservada: bundle 534,72 kB / 149,47 kB gzip, sobre 500 kB.
- `python -m pip check`, `python -m compileall -q backend/app` y comprobación de
  formato de diff/archivos nuevos: correctos. Se respetaron los saltos de línea
  históricos de las líneas ajenas del README; no se modificó evidencia congelada. El escaneo de
  patrones de credenciales sólo encontró la URL ficticia de `.env.example`.
- Pruebas nuevas: aislamiento de avisos/técnicas por actor, apertura sin cuenta
  de inquilino, bloqueo de presupuesto, finalización, reintentos concurrentes,
  recuperación histórica, consultas en lote, paginación, permisos, RLS,
  inmutabilidad, rollback y lectura sin adelantar cursores.

Preparación reproducible: `PYTHON_DOTENV_DISABLED=1`,
`RUN_SUPABASE_INTEGRATION=0`, URLs sólo a PostgreSQL local;
`PGPASSWORD` sólo en memoria para el subproceso del test de checkpoints.
No se almacenan valores privados aquí. Sin Supabase, SMTP real ni Gemini;
no son comprobaciones de CI de GitHub.

Incidencias conservadas: primer intento focalizado con pool threads no inició
workers y no ejecutó pruebas; se repitió con forks. La primera regresión frontend
tuvo 418 aprobadas/1 fallo: el test de operadores asumía un único fetch global.
Se adaptó a la nueva bandeja manteniendo la comprobación de un solo auth/me
y ningún acceso al API de operadores por un inquilino. La repetición pasó 419/419.
La primera regresión backend tuvo 1533 aprobadas/62 omitidas/1 fallo: faltó
PGPASSWORD para el subproceso independiente de checkpoints. Tras corregir el
entorno, el módulo focalizado y la suite completa pasaron, sin alterar ese código.

## QA visual vigente — datos ficticios, autenticación normal

Se regeneró una demo local aislada sin consultas precargadas, con workers externos
apagados. Mediante los formularios reales se verificó:

1. Proveedor abre consultas desde su solicitud; se bloquea Revisar presupuesto.
2. Inquilino ve badge 2 desde su inicio sin abrirse el panel; la bandeja sólo
   contiene la consulta técnica. Lee y responde; baja el contador y vuelve el
   foco al textarea después de enviar.
3. Proveedor recupera la respuesta y finaliza explícitamente. Queda sólo lectura,
   se habilita el presupuesto y conserva el importe de borrador de prueba.
4. Propietario responsable ve avisos individuales del agente sin la consulta
   técnica, sin compositor ni acciones libres de chat.
5. Administración consulta el historial; no hay compositor ni acción de cierre.
6. Móvil solicitado 390 × 844: ancho/scrollWidth 390 px, sin desbordamiento
   horizontal. Escape cierra/restaura foco al botón Mensajes. Escritorio
   1280 × 900 revisado; capturas de consultas, cierre y avisos guardadas localmente.

No acredita dispositivos físicos/teclado virtual ni revisión visual del operador;
sus permisos sí están cubiertos automáticamente. La demo no acredita despliegue,
persistencia entre regeneraciones ni, por sí sola, pruebas compartidas. Runner y
credenciales efímeras viven en una carpeta ignorada; no se publican. Talía autorizó
la entrega a revisión; la prueba compartida independiente se detalla a continuación.

## Aplicación y validación compartidas — 29/10/2026

Ejecutor reproducible: `backend/scripts/check_hu33_shared.py`. Requiere
`--authorized`, destino AARI verificado y configuración local no versionada.
No inicia FastAPI, workers, SMTP ni Gemini. Rechaza `-O` y conexiones a otro
proyecto; oculta conexiones, filas y parámetros privados en sus salidas.

Desde `backend/`, sólo con autorización para ese entorno:

```powershell
python -m scripts.check_hu33_shared --authorized --env-root RUTA_DEL_PROYECTO_CONFIGURADO --apply --validate
```

- Aplicación confirmada: **39 tablas anteriores preservadas**, con igual cantidad
  y huella de todas sus filas. Agregó las tres tablas HU33; total 42. RLS activo,
  sin políticas públicas y sin permisos anon/authenticated. Trigger inmutable y
  columnas de audiencia/participante/apertura/cierre verificados.
- Una segunda invocación del ejecutor con `--apply` reconoció el esquema
  instalado: `applied=false`, 39 tablas previas preservadas; no repitió el DDL.
- **Cinco controles de recorrido aprobados** con datos ficticios y repositorios
  reales: avisos individuales/privacidad; apertura e aislamiento por rol;
  presupuesto bloqueado durante consultas; mensajes/reintento/cursor de lectura;
  finalización explícita y presentación de un presupuesto mínimo posterior.
- La prueba no confirma datos: rollback exterior incluso si falla, con sesiones
  internas mediante savepoints. Las **42 tablas** quedaron iguales a su estado
  anterior y la secuencia de números de reclamo no cambió. Cero envíos externos.
- El primer intento usó nombres ficticios con dígitos en el sufijo HU33 y fue
  rechazado por las restricciones de personas. Se revirtió la prueba, se corrigió
  sólo el dato de QA y la repetición pasó. No se relajó ninguna regla del producto.
- Salvaguardas del ejecutor y API: **50 pruebas aprobadas** (13,84 s), seis nuevas
  de autorización/destino/optimización más 44 de API. Esta tanda es posterior a la
  regresión completa de 1534; no se presenta como una nueva suite completa ni
  se suma a ella como si fueran conjuntos independientes.
  El primer arranque de esa tanda no cargó conftest por faltar la URL ficticia
  al deshabilitar dotenv; se estableció `DATABASE_URL=sqlite://` sólo para esas
  pruebas unitarias y la repetición aprobó las 50, sin usar Supabase.

El feature flag continúa apagado por defecto; la autorización del DDL no activa
workers, despliegue ni el recorrido de horarios. La vista previa de HU23 mostrada
en el chat no es código integrado ni funcionalidad entregada por HU33.

## Registro de esfuerzo autorizado

Total informado por Talía: **8 HH**, distribuido aproximadamente por actividad
el 29/10. Sin duplicar worklogs en AARI-348 ni cambiar estimaciones/estados.

| Subtarea | Actividad | Tiempo |
| --- | --- | --- |
| AARI-355 | Matriz de participantes y permisos | 30 min |
| AARI-356 | API, paginación e idempotencia | 1 h 15 min |
| AARI-357 | Modelo, historial y migración | 45 min |
| AARI-358 | Interfaz responsive y revisión visual | 1 h 30 min |
| AARI-359 | Eventos del agente y contexto por intento | 1 h |
| AARI-360 | No leídos y actualización | 45 min |
| AARI-361 | Seguridad, concurrencia, recuperación y QA | 1 h 30 min |
| AARI-362 | Documentación y preparación de revisión | 45 min |

## Puesta en marcha y próximos pasos

`AARI_CONVERSATIONS_ENABLED=false` por defecto. No activa otros workers,
Gemini/SMTP/Meta ni aplica DDL al iniciar. La migración compartida ya fue aplicada
después de HU19 con preflight de esquema/permisos. No habilitar automáticamente
por hacer pull. La retención/purga futura requiere una decisión aparte.

Pendiente: revisión independiente del PR por Tobías, merge autorizado y cierre
expreso de HU/subtareas. Conservar En curso mientras tanto. HU20/HU23 y acceso
remoto real siguen fuera de esta entrega. Diff/secretos se revisan antes del commit.
README y guía de migraciones describen el alcance vigente. El 29/10 se actualizaron
mediante reemplazos puntuales los resúmenes de [Hub](https://app.notion.com/p/3a0f9f68a0c180cfa9d8ef06ef7da616),
[ejecución](https://app.notion.com/p/3a6f9f68a0c181eabecfc113a214e45c) y
[decisiones](https://app.notion.com/p/3a6f9f68a0c181e793f4dcfe66867b4e) de Notion:
las tres escrituras confirmaron éxito sin advertencias, conservando antecedentes
y páginas hijas, sin crear nuevos bloques ni activar planes de pago.

## Anexo histórico — prototipo inicial SUPERADO

Los resultados siguientes corresponden al alcance inicial del 28 y primera
revisión del 29/10. **No validan el diseño vigente ni autorizan intervención
normal de administración o chat económico compartido.** Se conservan como
evidencia histórica, reemplazada por la decisión y las pruebas anteriores.

### Resultados automáticos del 28/10/2026

- Backend completo, entorno aislado instalado desde `backend/requirements.txt`:
  `python -m pytest -q -p no:cacheprovider --tb=short` → **1518 passed, 62 skipped**,
  400,36 s. PostgreSQL local incluido. Las omitidas no se cuentan como aprobadas;
  persisten 18 advertencias preexistentes del adaptador datetime de SQLite.
- Tanda focalizada HU33 + HU19: **178 passed**, 126,21 s. Es un subconjunto de la
  regresión general, no se suma al total. Incluye permisos entre roles y
  candidatos, cambios de titular/vínculo/ciclo, presupuesto vencido/respondido,
  reintentos, orden y paginación, inmutabilidad, RLS/permisos, rollback del evento
  del agente y cancelación mientras un emisor espera el bloqueo.
- Frontend final tras corregir restauración del foco:
  `npm test -- --pool=threads --maxWorkers=1 --testTimeout=20000` → **407 passed**,
  41 archivos, 199,45 s. Incluye 12 pruebas nuevas de conversación. Otra ejecución
  completa anterior también pasó; no sumar repeticiones.
- `npm run lint`, `npm run build`, `python -m pip check`,
  `python -m compileall -q backend/app` y `git diff --check`: correctos.
- Advertencia de build no bloqueante: bundle principal 526,83 kB, 147,13 kB gzip,
  superior al umbral de 500 kB ya advertido antes de HU33. No se cambió el umbral
  ni se incorporaron dependencias para ocultarlo.

Las pruebas usan dobles HTTP o PostgreSQL nuevo y descartable, accesible sólo
por loopback. No usan Supabase, correo real ni Gemini. Se utilizó psycopg2 para
los fixtures generales y `PGPASSWORD` sólo en el proceso de pruebas del hijo de
checkpoints. `PYTHON_DOTENV_DISABLED=1` evitó cargar configuración real; no se
guardan valores privados en este documento. No son resultados de CI de GitHub.

### Revisión visual y demostración local

Se levantó una instancia aparte con datos ficticios, autenticación/cookie
normales y workers externos apagados, sin reemplazar la identidad por un mock.
En Chrome se verificó login de proveedor, consulta del hilo propio, envío desde
el formulario real, limpieza del borrador y persistencia del mensaje tras
recargar. En la revisión se corrigió el foco para que vuelva al textarea después
del envío; la regresión frontend final ya incluye ese ajuste y su aserción.

Vista móvil en el navegador integrado con viewport solicitado de 390 px: ancho
útil del documento y scrollWidth de 375 px, sin desbordamiento horizontal
general. Se observó el encabezado y las tarjetas adaptadas. En esta primera
pasada el control de navegador se detuvo al no poder verificar con seguridad la
URL de una ventana de Chrome; entonces quedaron pendientes el formulario móvil
y las vistas del responsable/inmobiliaria. La continuación siguiente resuelve
esos pendientes locales, conservando este antecedente.

### Continuación de QA local — 28 y 29/10/2026

- El 28/10 se repitieron `tests/test_conversations.py`: **34 passed**, 0,75 s;
  `ConversationPanel.test.jsx`: **12 passed**, 9,38 s de ejecución total.
  Son repeticiones focalizadas, no pruebas adicionales que deban sumarse a las
  suites completas anteriores. No se repitió la suite completa por esta revisión.
- Proveedor: recorrido por Enviadas y Ver solicitud; envío desde el formulario
  real en escritorio y móvil. Tab llevó de la entrada al botón; Enter envió,
  limpió el borrador y devolvió el foco al textarea. El retorno conservó el
  filtro de solicitudes enviadas.
- Propietario responsable: acceso por su cuenta normal al reclamo, apertura
  del hilo, lectura de mensajes y envío de una aclaración. El contador pasó de
  seis no leídos a cero al abrirlo. Revisión del formulario en ambos anchos.
- El 29/10, administrador: acceso desde candidatos mediante Ver presupuestos y
  conversaciones; selección de la solicitud correcta, consulta e intervención
  identificada como Administración demo. Tras recargar y reabrir el hilo, su
  mensaje persistió y el presupuesto/estado del reclamo no se modificaron.
- Escritorio solicitado 1280 px: documento útil y scrollWidth 1265 px.
  Móvil solicitado 390 px: ambos 375 px. Sin desbordamiento horizontal en los
  recorridos observados; botón de envío de 44 px de alto. Se distinguieron
  autores, avisos automáticos y el estado abierto de la conversación.
- Se guardaron capturas locales de escritorio/móvil y del panel completo para
  revisión de la usuaria. No se copiaron credenciales ni datos reales a ellas.
  Se restauró el tamaño normal del navegador y se dejó la conversación abierta.

La demo del 29/10 se regeneró con datos ficticios al reanudar sus procesos; no
se utiliza para acreditar persistencia entre reinicios del entorno de prueba.
La comprobación de persistencia visual corresponde a la recarga del navegador.
No se probaron dispositivos físicos ni su teclado virtual, ni el recorrido
visual del operador; sus permisos están cubiertos por las pruebas automáticas.
No se cambiaron fuentes funcionales ni se consumieron servicios externos por
esta continuación. La aceptación visual de la usuaria sigue pendiente.

La demo vive sólo en esta computadora y no acredita despliegue remoto ni
validación compartida. Sus credenciales efímeras y runner temporal están en una
carpeta ignorada por Git; no se copian aquí ni se publican. Los datos de demo son
descartables. La migración sigue sin aplicar a Supabase.

### Incidencias de preparación conservadas

El entorno Python inicial reutilizado
carecía de psycopg; se creó un venv aislado desde requirements sin cambiar pins.
Un primer intento frontend quedó bloqueado por permisos sobre temporales de
Vite; se repitió con permiso para esos archivos locales. Un test de hora esperaba
24 h pero Intl usaba 12 h; se explicitó `h23`. El primer test de cambio de elección
intentaba violar una restricción existente: se corrigió para cambiar de ciclo
conservando el registro anterior, no se relajaron controles del dominio.
