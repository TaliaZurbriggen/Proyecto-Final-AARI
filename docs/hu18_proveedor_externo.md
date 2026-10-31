# HU18 / AARI-199 — Registrar un proveedor externo

## Estado y alcance

Implementación local aprobada por Talía, en `codex/AARI-199-proveedor-externo`,
creada desde `main` `2ff6e3e` (HU33 integrada). Revisión de cierre local:
31/10/2026, Argentina. HU y subtareas AARI-200…AARI-205 **En curso**.
Estimación original de 4 HH conservada. Talía autorizó el 31/10/2026 publicar la
entrega y registrar **3 h 30 min**: AARI-200 60m, AARI-201 20m, AARI-202 45m,
AARI-203 20m, AARI-204 20m y AARI-205 45m. Es una distribución del total informado,
no una medición automática; se registra sólo en subtareas, sin duplicar en la HU.
No se cerraron actividades: entrega a revisión, pendiente aprobación/merge.

Permite registrar **nombre completo y teléfono** de una persona elegida fuera
del padrón. Confirmar guarda el contacto asociado al reclamo/propiedad y cambia
el estado a `Derivado a proveedor externo` en una misma transacción.
No equivale a reparación terminada, visita confirmada ni contratación automática.

## Decisiones aprobadas

- Entrada principal: elección de proveedor propio de HU17. No se deriva el
  reclamo hasta confirmar los datos. No se reutiliza el vencimiento de la
  elección ya respondida ni se inventa otro plazo para completar el contacto.
- Alternativa para HU20: con una ronda vigente y presupuestos recibidos, o una
  ronda sin presupuestos, el mismo endpoint permite optar por un externo,
  siempre que aún no haya presupuesto/proveedor seleccionado. El botón de la
  futura comparación se integra con HU20; esta entrega no implementa HU20.
- Sólo registra el responsable original de la elección, con cuenta activa,
  primer ingreso resuelto y vínculo vigente: inquilino para gasto ordinario;
  propietario para extraordinario previamente autorizado por esa misma cuenta.
  Un nuevo titular no hereda el contacto ni la facultad de confirmar otra elección.
- La inmobiliaria consulta el historial, sin compositor ni edición. No hay alta
  en el padrón, nueva cuenta de proveedor, invitación ni mensaje al externo.
- El registro confirmado no se sobrescribe ni borra desde esta función. Cambiar
  de proveedor posteriormente corresponde a HU24, no a este formulario.
- Se conserva la elección original, los presupuestos, mensajes y contactos
  históricos. Las solicitudes/avisos pendientes obsoletos quedan sin efecto con
  auditoría; no se intenta retirar un correo que ya haya sido enviado.

## Recorrido y permisos

1. HU17 muestra «Cargar datos del proveedor» después de elegir proveedor propio.
2. Formulario centrado con dos campos, errores junto al input y foco en el primer
   error; en móvil se apilan los campos y acciones. Reutiliza los tokens y los
   componentes de la skill `aari-frontend`.
3. «Confirmar datos del proveedor» normaliza nombre/teléfono y guarda en un solo
   paso. El servidor revalida identidad, etapa, elección y versión; guarda
   contacto, transición e historial atómicamente.
4. La confirmación muestra «Proveedor externo confirmado: [nombre] atenderá este
   reclamo», destacando el nombre recibido del servidor. El aviso tiene separación
   vertical respecto de los datos y la nota inferior; no confirma una reparación
   terminada ni una fecha de visita. El foco pasa al encabezado de confirmación.
5. Se muestra el contacto en sólo lectura. Administración lo ve en el detalle
   del reclamo dentro del historial de la propiedad. Los registros legados sin
   autor informado se identifican como tales, sin atribuciones inventadas.

El inquilino que consulta el historial general no recibe automáticamente los
contactos económicos del propietario. Operadores/proveedores y cuentas ajenas
no acceden a este recurso. La API no toma usuario, rol o propiedad del navegador.

Ajuste aprobado por Talía después de revisar la demo el 31/10/2026: se eliminó
el paso intermedio «Revisar datos» y el botón «Confirmar y derivar reclamo» de la
primera versión. La intención visible es confirmar al proveedor externo; la
derivación sigue siendo un efecto atómico del guardado, no una acción adicional
del usuario. No se modificaron permisos, API, plazos ni persistencia. Se mantiene
el mismo UUID ante un resultado incierto y se bloquean los campos hasta consultar
el estado o reintentar; un error de validación conocido permite corregirlos.

## API y componentes

- `GET /reclamos/{id}/proveedor-externo`: contexto, permiso, motivo de bloqueo,
  contacto actual e historial permitido. Lectura sin efectos secundarios.
- `POST /reclamos/{id}/proveedor-externo`: cuerpo con `request_id`, `eleccion_id`,
  `expected_updated_at`, `nombre` y `telefono`; rechaza atributos extra.
- Nombre: 3–120 caracteres, letras Unicode, espacios, apóstrofes y guiones;
  normalización NFC y de espacios. No admite un DNI ni números mezclados.
- Teléfono: 8–15 dígitos ASCII. Acepta espacios, guiones, paréntesis y `+` inicial
  para pegarlo; almacena dígitos. Rechaza letras, extensiones y `+` intermedios.
  No comprueba existencia, titularidad ni disponibilidad en WhatsApp.
- Respuestas del recurso sin caché. Errores de almacenamiento sin detalles de
  conexión; conflictos no sobrescriben datos y obligan a refrescar el contexto.
- Backend: esquema/reglas/repositorio/rutas `external_providers`; frontend:
  `ExternalProviderPage`, cliente `externalProvidersApi`, rutas protegidas y
  enlaces en elección/detalle, más `ExternalProviderHistory` de administración.

## Consistencia y recuperación

La transacción respeta el orden cuenta → perfil → propiedad → reclamo → elección.
Revalida identidad, autorización, elección actual y `updated_at`; también la
huella del contexto de la ronda en la salida alternativa. Una confirmación UUID
con el mismo contenido devuelve el resultado anterior; un UUID reutilizado con
otros datos se rechaza. Hay unicidad por elección y protección de auditoría.

El formulario bloquea doble envío. Ante un resultado incierto conserva el UUID
y los datos, permite consultar estado/reintentar sin crear otro contacto y no
permite editar silenciosamente el contenido del reintento. Un conflicto real
recarga el estado y deja de ofrecer la acción si dejó de corresponder.

La cancelación de rondas y avisos ocurre en la misma transacción. Los mensajes
ya existentes siguen consultables pero no admiten nueva escritura/cotización
cuando la derivación deja obsoleto ese circuito. No reactiva rondas antiguas ni
recorta el historial de elecciones anteriores.

## Migración

`backend/migrations/20261029235000_hu18_proveedor_externo.sql` amplía la tabla
existente `proveedores_externos` con elección, usuario, nombre del actor,
idempotencia, versión e historial de transición. Conserva las filas anteriores
sin inventar esos valores. Incluye FK/índices, RLS, revocación de permisos de
tabla/columnas y un trigger que exige auditoría para nuevos registros e impide
modificar/borrar contactos nuevos confirmados.

Requiere HU16/HU17 y HU19 AARI. El evento de conversación se integra cuando
HU33 está habilitada, sin activar ese flag desde HU18. La migración se aplicó
primero a bases locales descartables y, con autorización posterior de Talía,
**en Supabase AARI el 31/10/2026** (detalle abajo). No se ejecuta al iniciar
FastAPI ni se repite por pull/merge; no editar el SQL ya aplicado.

## Validación

Regresiones locales sin Supabase, Gemini ni SMTP real. PostgreSQL 17 en un contenedor dedicado,
con base ficticia nueva por caso y eliminación posterior por el fixture.

Comandos desde `backend/`, con `PYTHON_DOTENV_DISABLED=1`, `DATABASE_URL=sqlite://`,
`RUN_SUPABASE_INTEGRATION=0` y `AARI_TEST_POSTGRES_URL` apuntando sólo a loopback:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_external_providers.py tests/test_external_providers_postgres.py
python -m pytest -q -p no:cacheprovider --tb=short --junitxml=tmp/hu18-backend-tests.xml
python -m pip check
python -m compileall -q app
```

Desde `frontend/`:

```powershell
npm test -- --pool=forks --maxWorkers=1 --testTimeout=20000
npm run lint
npm run build
```

Pruebas focalizadas previas: **63 backend aprobadas**; **40 frontend aprobadas**
incluyendo formulario, elección e historial. No se suman repeticiones o
subconjuntos al total. Las regresiones completas se repitieron el 31/10 tras
detenerse el contenedor entre sesiones y no conservarse el resultado final de
las sesiones anteriores:

- Backend completo: **1603 aprobadas / 62 omitidas**, 942,04 s, PostgreSQL local
  incluido. Sin fallos. Se conservan 18 advertencias previas de adaptación
  datetime de SQLite; otras tres corresponden a `record_property` y el formato
  del informe JUnit de las pruebas de volumen, no a fallos de negocio.
- Frontend completo: **450 aprobadas / 0 fallidas**. Lint y build correctos.
  JavaScript 544,62 kB / 152,20 kB gzip: permanece la advertencia conocida de
  chunk superior a 500 kB. No se ocultó ni cambió el umbral; no acredita una
  medición de rendimiento en dispositivos reales.
- `pip check`: sin dependencias rotas. `compileall`: correcto.
- `git diff --check`: correcto; revisión del diff y búsqueda de patrones de
  credenciales sin hallazgos. La demo y sus ejecutores están ignorados por Git.

Corrección posterior de interfaz (31/10): 34 pruebas focalizadas aprobadas
(formulario real y elección), incluidas cuatro regresiones nuevas sobre nombre
numérico en el formulario, corrección tras 422, reintento tras 503 y consulta de
un guardado cuya respuesta se perdió. Las pruebas existentes se adaptaron al
guardado en un paso y verifican el nombre en la confirmación, foco y doble envío.
Lint/build correctos; bundle 544,05 kB / 152,07 kB gzip, advertencia conocida
conservada. Regresión completa posterior de frontend: **454 aprobadas / 0
fallidas**. Los botones admiten reorganizar el texto en móvil sin imponer un
ancho mínimo mayor que la tarjeta. No se repitió backend porque no cambió;
se conserva su evidencia anterior por separado.

Último ajuste visual autorizado: separación de 24 px (token `--aari-space-5`)
entre el bloque «Ver presupuestos y conversaciones» y «Estado actual», sin
cambiar comportamiento ni estilos globales. Verificación posterior: **44
focalizadas aprobadas** en formulario/elección/historial, lint/build correctos;
bundle 544,14 kB / 152,10 kB gzip, advertencia conocida conservada. Las últimas
regresiones completas siguen siendo 454 frontend y 1603/62 backend; no se
repitieron completas por este margen y no se suman las 44 al total.

Cubren permisos ordinario/extraordinario, campos vacíos/inválidos, normalización,
identidad/propiedad/versión obsoletas, doble clic, UUID repetido, dos confirmaciones
simultáneas, contacto contra cotización concurrente, rollback temprano/tardío,
historial privado, conservación de presupuestos/mensajes, cancelación de avisos,
RLS, preservación de legados e inmutabilidad de registros nuevos.

Incidencia corregida durante la validación: una expresión de caracteres del
nombre en JavaScript admitía un rango involuntario. Dos pruebas la detectaron;
se corrigió y la repetición focalizada pasó completa. Sin cambiar dependencias.

## Aplicación compartida autorizada — 31/10/2026

El primer commit `748633e` ya había terminado de subirse cuando llegó la
indicación de Talía de aplicar la migración antes de publicar. Se informó esa
secuencia y se detuvo la creación del PR hasta completar la validación compartida.

Ejecutor versionado `backend/scripts/check_hu18_shared.py`: exige `--authorized`,
valida destino AARI antes de conectar, rechaza `-O`, aplica DDL e historial en una
transacción con límites 5s/30s y comprueba preservación de los campos existentes.
Verifica RLS/revocaciones de tabla/columnas/función, FK/CHECK/índices/trigger y
función SECURITY INVOKER con search_path aislado. No repara estados parciales ni
lee/imprime filas privadas, conexiones o huellas. No activa la aplicación/workers.
La comparación de huellas no constituye un respaldo independiente de la base.

```powershell
python -m scripts.check_hu18_shared --authorized --env-root RUTA_CONFIGURADA
python -m scripts.check_hu18_shared --authorized --env-root RUTA_CONFIGURADA --apply --validate
```

- Preflight compartido de sólo lectura: proyecto correcto, HU18 no instalada,
  42 tablas comprobadas y sin cambios.
- Aplicación confirmada: versión `20261029235000`, nombre
  `hu18_proveedor_externo`, DDL e historial confirmados juntos. Las 42 tablas
  mantuvieron conteos/huellas de columnas preexistentes; contactos legados sin
  metadatos atribuidos ni creación de registros de negocio por el DDL.
- Dos recorridos con repositorios reales en Supabase: responsable inquilino
  ordinario y propietario extraordinario autorizado. Guardado normalizado,
  transición, repetición idempotente, un contacto/un historial y administración
  sólo lectura aprobados.
- Los datos ficticios se revirtieron por completo; numeración de reclamos
  preservada mediante números explícitos en la prueba. Cero envíos de correo,
  Gemini o Meta. La demo visual sigue siendo local, no un login compartido validado.
- Ejecutores/guardas y dominio HU18: **75 pruebas locales aprobadas**. Repetición
  final del ejecutor: **12 aprobadas**, subconjunto de esas 75, sin sumarlas.
  La suite completa de 1603/62 antecede a estas 12 pruebas nuevas y no se repitió
  por el ejecutor operativo; no se informa un total completo nuevo calculado.
- Antes de tocar Supabase, las pruebas del ejecutor detectaron la interpretación
  de `%I` por el driver al pasar parámetros vacíos y un nombre ficticio con dígitos.
  Se corrigieron ambos en el ejecutor/datos de prueba y se repitió con éxito. No
  se cambió la migración ni la lógica de producto para hacer pasar estos controles.

## Demo y pendientes de aceptación

Demo temporal ignorada por Git en `http://127.0.0.1:13609/tmp/hu18-review.html`:
componentes reales y PostgreSQL local real, con identidad simulada explícita.
Permite revisar como inquilino y luego como administración; no valida el login
normal, no usa datos compartidos y no envía notificaciones. Los ejecutores y
datos temporales no forman parte de la entrega.

La revisión visual automática se detuvo porque Computer Use no pudo identificar
con seguridad la URL de Chrome. No se acredita QA visual escritorio/móvil ni
aceptación del usuario por el solo hecho de levantar la demo. Pendiente esa
revisión y el enlace de HU20 cuando esté integrada. La aplicación compartida ya
fue autorizada y validada, sin acreditar QA visual ni login normal por ello.
Publicación/PR autorizados el 31/10, con estas limitaciones explícitas
para Tobías; el cierre de Jira no está autorizado hasta aprobar/fusionar.
