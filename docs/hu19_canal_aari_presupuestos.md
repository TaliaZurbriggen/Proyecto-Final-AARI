# HU19 / AARI-206 — Solicitudes y presupuestos dentro de AARI

Estado al 27/10/2026: implementación y validación compartida listas para revisión.
Migración aplicada con autorización; recorridos HTTP/Supabase exacto y mínimo
aprobados con rollback. Correo recibido según confirmación de Talía y recorrido
visual del proveedor completado con un mínimo ficticio persistido. Entrega
autorizada en `codex/AARI-206-solicitudes-presupuesto`, pendiente de revisión y
merge del PR por Tobías. Sin cierre de la HU en Jira.

## Decisiones aprobadas

WhatsApp no es un requisito operativo de este recorrido. Se conserva la
evidencia del intento anterior, sin declarar solucionada la restricción de Meta.
HU32 (PR #37, integrado en `c3adc8f`) aporta cuentas, invitaciones, activación y
sesiones del proveedor; HU19 completa la recepción y respuesta de solicitudes.
HU33 sigue siendo una historia distinta: conversación privada, no confirmación
de importes mediante texto libre.

El agente publica una solicitud privada para cada candidato compatible de HU15
con cuenta activa, luego de la elección fidelizada de HU17 y la autorización de
HU16 cuando corresponde. No crea ni activa cuentas de forma automática. Los
proveedores sin acceso se registran como exclusiones para revisión de la
inmobiliaria, no como personas que ignoraron una solicitud.

Se eligió publicar en AARI y encolar el correo en una única transacción. La
entrega SMTP es posterior y utiliza la bandeja de salida existente con reintentos
persistidos. No se llama a SMTP dentro de la transacción. El aviso contiene un
enlace protegido, no datos del contrato, fotos ni información de competidores.
«Enviado» significa aceptación por SMTP, no recepción, apertura ni lectura.

### Precio exacto o importe mínimo

Talía aprobó expresamente el 27/10 permitir que el proveedor informe un mínimo
cuando no puede dar un precio final. `tipo_importe` es obligatorio para nuevos
presupuestos AARI y admite:

- `exacto`: precio exacto informado para el alcance descripto.
- `minimo`: piso del costo, presentado como «Desde $10.000,00 ARS».

Un mínimo **no es un máximo autorizado ni un precio final**. Recibir el presupuesto
no contrata al proveedor ni aprueba un aumento posterior. HU20 deberá conservar
esa distinción al comparar y confirmar una elección. No se deduce el tipo desde
un mensaje ni se usa Gemini para interpretar dinero. Se descartó esa alternativa
porque podría transformar un monto tentativo en un compromiso inexistente.

Moneda explícita ARS/USD; monto positivo, máximo 10 dígitos enteros y dos
decimales, enviado como texto decimal y almacenado con `numeric(12,2)`. El
formulario acepta coma decimal y la convierte a punto, sin aceptar separadores
de miles. La API rechaza símbolos, booleanos, flotantes, notación exponencial,
monedas no admitidas y campos de identidad enviados por el cliente.

El proveedor revisa una vista previa antes de confirmar. Hay un presupuesto
inmutable por solicitud; un reintento con el mismo UUID y contenido devuelve el
resultado previo. Otra respuesta no lo sobrescribe. La confirmación queda
vinculada a la cuenta autenticada, al proveedor y al reclamo con restricciones
SQL compuestas y evento de auditoría.

## Bandeja del proveedor y filtros (ajuste aprobado el 27/10/2026)

La vista inicial es **Pendientes**. El proveedor puede alternar entre:

- **Pendientes:** solicitudes abiertas, dentro del plazo, sin presupuesto y con
  contexto, autorización/elección y compatibilidad todavía válidos para responder.
- **Enviadas:** solicitudes con un presupuesto ya confirmado por esa cuenta.
  No significa que el correo haya sido entregado ni leído.
- **Todas:** historial propio completo, incluidas vencidas y canceladas.

Cambiar el filtro reinicia la página en uno. La URL conserva `estado` y `page`
durante la paginación y al volver desde el detalle real. El acceso directo al
detalle vuelve de forma segura a pendientes; valores desconocidos del filtro se
normalizan en la interfaz y la API rechaza valores no admitidos con 422.

El backend filtra antes de contar y paginar, no solamente las diez filas visibles.
Para pendientes, SQL excluye cerradas, respondidas y vencidas; se revalida el
contexto en lote y se comparte la búsqueda de compatibilidad por criterios, sin
consultar una vez por solicitud ni duplicar las reglas de autorización. La
consulta es sólo lectura. No requiere una migración adicional.

## Plazos, vigencia y aislamiento

Las 24 horas empiezan al publicar para una cuenta activa, no al abrir el correo.
Se guardan como `timestamptz`; la interfaz presenta horario argentino. Reiniciar
el servidor, reintentar correo o recargar una página no reinicia el plazo.

Cada lectura y respuesta valida identidad/vínculo del proveedor. Antes de
confirmar se bloquea el reclamo y la solicitud, y se revalida autorización,
elección, participantes, ubicación, descripción, especialidad, cobertura y plazo.
Un proveedor no consulta solicitudes ajenas ni presupuestos competidores. El
responsable sólo consulta su ciclo vigente; administración puede consultar el
historial y el operador sólo los reclamos asignados. Ninguna ruta pública recibe
un `usuario_id` para decidir permisos.

Al vencer, se conservan los presupuestos parciales. Si no hay ninguno y los
avisos fueron aceptados por SMTP, se registra «Sin presupuestos recibidos» y se
avisa a la inmobiliaria. Si falló o sigue pendiente un aviso, se deja la ronda
en revisión sin atribuir silencio al proveedor. Un contexto que ya no coincide
cancela el intento; no vuelve a usar una autorización anterior. La primera
respuesta genera un único aviso lógico al responsable. No se selecciona ni
contrata a nadie y no se sobrescribe el checkpoint de HU21.

## Modelo y despliegue

Migración nueva: `backend/migrations/20261027130000_hu19_canal_aari.sql`.
Requiere las tablas de HU16, HU17, HU32 y el esquema de coberturas HU15. **No
requiere aplicar las tres migraciones locales del intento WhatsApp**. Crea
rondas, solicitudes y eventos AARI, y agrega procedencia, moneda y tipo de
importe a presupuestos. No inventa moneda ni tipo para registros históricos.
Activa RLS y revoca permisos públicos, `anon` y `authenticated`; el acceso es por
FastAPI autenticado. No crea cuentas, solicita presupuestos ni envía correo al
aplicar el SQL.

Orden de despliegue (migración compartida autorizada y aplicada el 27/10/2026;
activación general de workers todavía pendiente):

1. Respaldo y revisión del esquema compartido; aplicar la migración aditiva.
2. Configurar `APP_LOGIN_URL` con el origen correcto (HTTPS fuera de localhost).
3. Habilitar `AARI_QUOTE_PORTAL_ENABLED=true` para API y bandeja.
4. Habilitar `AARI_QUOTE_WORKER_ENABLED=true` para publicación y vencimientos.
5. Habilitar el worker de notificaciones existente sólo al autorizar correo real.

Ambos flags nuevos permanecen en `false` en `.env.example`. Con el portal activo,
los workers legados de solicitudes/respuestas Meta no se inician, aunque sus
flags se hayan dejado activos accidentalmente. No hay nuevas dependencias.

## Contrato para integración con HU20/HU33

- `GET /proveedor/solicitudes?page=1&page_size=10&estado=pendientes`: bandeja propia
  paginada; `estado` admite `pendientes` (predeterminado), `enviadas` y `todas`.
- `GET /proveedor/solicitudes/{id}`: solicitud privada y presupuesto ya enviado.
- `POST /proveedor/solicitudes/{id}/presupuesto`: `request_id`, `monto` textual,
  `moneda`, `tipo_importe`, `descripcion`. No acepta identidad del proveedor.
- `GET /reclamos/{id}/presupuestos`: lectura autorizada del responsable o agencia.
- La ficha de elección fidelizada muestra las respuestas en sólo lectura. La
  selección, comparación económica y contratación pertenecen a HU20.
- HU33 debe conservar la relación solicitud/intento y no sustituir el formulario
  de confirmación de precios por extracción automática del chat.

## Validación

La suite nueva usa PostgreSQL local descartable, usuarios sintéticos y mocks.
Se comprueban migración independiente de Meta, RLS, precios exactos/mínimos,
autorización previa, exclusiones, idempotencia, concurrencia, vencimiento,
resultados parciales, fallas de correo, cambios de contexto y rollback de auditoría.
Las pruebas frontend recorren componentes reales, validaciones, vista previa,
doble clic, respuesta perdida, enlaces de retorno y paginación con error sin
mostrar resultados viejos.

Resultados previos al ajuste de filtros, conservados como evidencia:

- `pytest -q` con SQLite en memoria y workers externos deshabilitados: **1077
  passed, 384 skipped**. Las omitidas dependen de PostgreSQL/servicios externos u
  otras condiciones de entorno; no se informan como aprobadas. Dieciocho avisos
  de deprecación del adaptador datetime SQLite, sin fallos.
- `pytest -q tests/test_quote_portal.py tests/test_quote_portal_postgres.py`
  con `AARI_TEST_POSTGRES_URL` apuntando a loopback: **64 passed** (36 de contrato
  HTTP/validación y 28 de PostgreSQL). Incluye outbox real con emisor SMTP simulado.
- La regresión PostgreSQL ampliada de HU19/HU32/HU17/legado dio inicialmente
  **139 passed, 1 failed** por un operador ficticio sin nombre obligatorio. Al
  completar el fixture también se corrigió un correo sintético duplicado con
  el fixture base; el caso pasó y la suite nueva completa terminó en 64/64.
  No se presenta aquella corrida ampliada como una corrida completa verde.
- `npm test -- --maxWorkers=1 --testTimeout=20000`: **383 passed**, 40 archivos.
  La primera corrida concurrente tuvo 16 esperas agotadas en el archivo
  preexistente de filtros; sus 75 pruebas pasaron aisladas y luego pasó toda
  la suite con un único proceso, sin cambiar esas comprobaciones.
- `npm run lint`, `npm run build`, `pip check` y `git diff --check`: correctos.
  Build advierte un bundle principal de aproximadamente 517 kB, no bloqueante.
- Chrome con una demo en puertos separados y PostgreSQL descartable: bandeja,
  detalle, vista previa y confirmación de un mínimo de 10000 ARS. Se verificaron
  los tres controles alineados en escritorio (misma coordenada superior), foco
  de teclado visible y apilado en móvil. Ancho de contenido igual al ancho útil
  tanto en escritorio (1521 px) como en móvil (375 px útiles de viewport 390 px):
  sin desbordamiento horizontal. La demo usa sesión ficticia sólo en su proceso
  temporal; no modifica autenticación de producción ni envía correo.

No considerar cerrada la HU por pruebas locales: la migración, el aviso recibido
y el recorrido manual ya se validaron de forma controlada; resta la entrega
autorizada y revisión del PR antes de marcarla finalizada.

### Validación del ajuste de filtros

`pytest -q tests/test_quote_portal.py tests/test_quote_portal_postgres.py` con
PostgreSQL local: **71 passed**. Incluye 31 solicitudes propias y otras 31 para
otro proveedor, distribuidas en varias páginas: 15 pendientes vigentes, 12
presupuestos enviados y cuatro solicitudes no accionables. Se verifica el
conteo antes de paginar, estabilidad del orden, filtro predeterminado, rechazo
de parámetros inválidos, aislamiento y ausencia de cambios de negocio al listar.
El primer fixture intentó reutilizar un inquilino/propiedad para varios reclamos
activos y fue rechazado por la restricción vigente; se corrigieron los datos
ficticios creando unidades e identidades independientes, sin alterar el esquema.

Frontend completo actualizado: **389 passed**, 40 archivos, con
`npm test -- --maxWorkers=1 --testTimeout=20000`.
Frontend focalizado: **27 passed**; incluye cambio de filtro a página uno,
retorno mediante los componentes reales, respuesta tardía del filtro anterior y
vacíos diferentes por filtro. `npm run lint` y `npm run build`: correctos.

Revisión visual con Chrome y datos ficticios: Pendientes seleccionado al abrir
`/proveedor`, Enviadas muestra sólo el presupuesto confirmado, Todas reúne ambas
solicitudes y el enlace real de retorno conserva el filtro. En móvil de 390 px
no hay desbordamiento horizontal. Por debajo de 24 rem, los botones se apilan
para no recortar etiquetas. La simulación a 320 px con scrollbar de escritorio
también permitió separar el badge de cuenta activa del nombre/correo, para que
la cabecera del proveedor no los comprima en una columna demasiado estrecha.
Esa misma simulación
evidenció el `min-width: 320px` global preexistente en `body`; no se cambió ese
estilo transversal en este ajuste de la bandeja. No se aplicó SQL en Supabase,
no se enviaron correos y no se realizaron llamadas a Gemini.

### Ajuste visual de la bandeja y pie de navegación — 27/10/2026

Revisión aprobada por Talía: filtros centrados en una franja con más aire y un
divisor antes de los reclamos; estado junto al número del reclamo; «Ver
solicitud» conserva su semántica de enlace, pero compone los estilos del botón
secundario compartido de AARI, sin flecha ni subrayado. No se duplicó el diseño
de botones ni se convirtió el estado en una acción.

Se retira el contador visible «Página X de Y». El pie se oculta cuando hay cero
resultados o una sola página. Para varias páginas muestra «Ver anteriores» y
«Ver siguientes», centrados, con límites deshabilitados; no es un mecanismo de
acumulación/ocultación de filas («Ver más/menos»). Si una URL quedó fuera de rango,
se mantiene una salida segura a la primera página y el botón anterior salta a
una página válida en lugar de recorrer índices vacíos. Se conservan filtro y
página al abrir y volver del detalle.

La API y las consultas de negocio no cambian. Se repitió la suite HTTP/PostgreSQL
local: **71 passed**. La prueba de mezcla de 31 solicitudes por proveedor sigue
comprobando filtros antes del conteo, orden estable, límites, aislamiento y la
búsqueda compartida de compatibilidad. La demo se amplió únicamente con datos
ficticios locales para revisar el pie real: 12 pendientes (10 en página uno y
2 en página dos), una enviada y 13 en Todas; página tres vacía y sin duplicados
entre las páginas de pendientes. No se tocó Supabase ni SMTP.

Frontend focalizado: **32 passed**, incluyendo ausencia del pie con un solo
resultado/vacío, primera/segunda/última página, recuperación fuera de rango,
una sola consulta por cambio de página, retorno real y foco del enlace con
teclado. Frontend completo: **394 passed**, 40 archivos, ejecutado con
`npm test -- --maxWorkers=1 --testTimeout=20000`.
`npm run lint` y `npm run build`: correctos; continúa la advertencia conocida
del bundle principal mayor a 500 kB.

Revisión visual final en Chrome: filtros centrados, etiqueta y número en la
misma cabecera y acceso secundario sin flecha. En móvil de 390 px, el ancho
útil y el ancho del contenido coinciden (375 px, sin scroll horizontal); los
accesos y el pie se apilan sin recortes. Se abrió un detalle desde la segunda
página y el enlace real de regreso conservó `page=2&estado=pendientes`.

Refinamiento posterior solicitado por Talía: título, filtros y «Actualizar» se
agrupan en una única fila en escritorio, con los filtros centrados. En tablet
se permite una segunda fila y en móvil se apilan sin scroll horizontal. Se
reutilizan los botones y tokens compartidos; no cambia la API ni la paginación.
Validación: **33 pruebas focalizadas aprobadas**, lint y build correctos
(persiste únicamente la advertencia de tamaño del bundle). Chrome confirmó la
misma alineación vertical de los tres grupos en escritorio y ningún
desbordamiento a 390 px. No se repitió la suite backend al no haber cambios en
ese componente.

### Validación compartida autorizada — 27/10/2026

Talía autorizó aplicar la migración aditiva y enviar un aviso de prueba al mismo
correo vinculado al proveedor de HU32. El preflight confirmó las dependencias y
la cuenta activada, sin divulgar contactos ni credenciales en la evidencia.

- Ensayo de DDL con rollback: correcto. Aplicación posterior con respaldo local
  privado del esquema público (archivo custom de 198856 bytes, catálogo legible
  por `pg_restore`; no se ensayó una restauración completa). Respaldo excluido de
  Git. El primer intento de respaldo no avanzó porque el contenedor local estaba
  detenido; se inició antes de repetir. Ninguna migración se ejecutó sin respaldo.
- DDL e historial `20261027130000_hu19_canal_aari` confirmados atómicamente.
  Se preservaron los conteos de las 36 tablas existentes. Es una comprobación de
  cantidades, no de igualdad fila por fila. RLS verificado en las tres tablas
  nuevas y `presupuestos`; sin políticas públicas ni permisos de clientes
  `anon`/`authenticated`. No se aplicaron las migraciones del intento Meta.
- Dos recorridos sobre Supabase con transacción externa y rollback: `exacto` y
  `minimo`, importe decimal `10000.50` ARS. Se usaron rutas HTTP reales, login y
  cookie normal, con repositorios reales enlazados a la transacción de QA; no se
  reemplazó la identidad autenticada. Se verificaron 401 sin sesión, publicación
  única, lectura privada, confirmación, replay idempotente, 409 ante otro intento,
  filtros Pendientes/Enviadas, 404 para lectura y respuesta de otro proveedor y
  lectura del responsable. Conteos iniciales/finales iguales tras rollback.
  La numeración secuencial puede consumir números aun con rollback; no se
  reinició ninguna secuencia compartida. Cero correos y cero llamadas a LLM en
  esos recorridos.
- Preparación persistida: una solicitud sintética exclusiva para el proveedor
  de prueba de HU32. Se agregaron únicamente entidades ficticias y una
  especialidad de QA para aislar la compatibilidad; no se alteraron reclamos ni
  contratos existentes. Los demás avisos generados para ese reclamo ficticio
  quedaron explícitamente excluidos de envíos reales. Dos intentos previos del
  runner abortaron por formato de email ficticio y tipado de un parámetro de QA;
  se corrigieron en el runner temporal y revirtieron antes de preparar la fila.
- Envío SMTP puntual: un destinatario, un intento; estado `enviado` y fecha
  persistidos. Se reservó sólo el ID autorizado y se usaron el emisor SMTP y la
  confirmación de entrega de la outbox, sin consumir la cola general ni ejecutar
  su limpieza global. Aceptación por Gmail no prueba recepción, apertura o
  lectura: Talía confirmó posteriormente que el correo llegó a su bandeja.

La revisión manual usa `http://localhost:5190` con API local en 8020 conectada a
Supabase y autenticación normal, sin overrides de identidad. Todos los workers
generales, Meta y Gemini están apagados en ese proceso temporal; no cambia el
`.env` compartido ni los defaults del proyecto. Los enlaces del aviso apuntan a
esa versión local y sólo sirven mientras esté levantada en la misma computadora.
La demo ficticia anterior en 5189/8019 no constituye evidencia de este recorrido.
La recepción en bandeja y el recorrido visual se completaron después, como se
detalla a continuación; no se marca la HU terminada antes de revisión/merge.

Regresión final del frontend tras el ajuste de cabecera:
`npm test -- --maxWorkers=1 --testTimeout=20000` → **395 passed**, 40 archivos.
Una primera ejecución restringida se interrumpió antes de obtener resultado y
no se cuenta como aprobada; la repetición completa terminó correctamente.
`git diff --check` correcto, conservando los finales de línea históricos.

### Cierre de la comprobación visual compartida — 27/10/2026

Talía confirmó la llegada del correo e inició sesión con la cuenta de proveedor
de prueba de HU32. Chrome mostró una única solicitud sintética en Pendientes.
Se abrió el detalle, se cargó un mínimo ficticio de `10000,50` ARS y el alcance
de prueba; la vista previa mostró «Desde $10.000,50 ARS», aclarando que no
confirma contratación. Se confirmó mediante el formulario real, sin invocar
directamente la API ni reemplazar la identidad del navegador.

La pantalla mostró «Tu presupuesto enviado» y conservó el resultado tras
recargar. El retorno mantuvo página y filtro; Pendientes quedó vacío y Enviadas
mostró exactamente una solicitud. Se contrastó la persistencia en Supabase:
un presupuesto `10000.50` ARS / `minimo`, un evento de registro y lectura
autorizada del responsable sintético. No se seleccionó proveedor, no se aprobó
un gasto real y no se programó ninguna visita.

El aviso al proveedor conserva un único intento SMTP; los avisos del responsable
sintético quedaron excluidos de envíos reales. No se enviaron nuevos correos ni
se consumió Gemini. Se conserva el reclamo, el presupuesto y su evidencia como
datos identificados de QA; no se eliminaron registros auditados. La captura de
confirmación excluye cabecera/correo personal. No se necesitó cambiar código
funcional durante este recorrido. README y guía de migraciones actualizados.

Resultado: **HU19 lista para revisión de Tobías**; Talía autorizó commit, push
y PR. Los workers generales siguen apagados en el
proceso temporal de QA; la activación general es una puesta en marcha posterior,
no se hizo como efecto lateral de esta validación.
