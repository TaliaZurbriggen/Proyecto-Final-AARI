# HU24 / AARI-262 — Cancelación y reelección de proveedor

Propuesta aprobada por Tobías el 03/11/2026. Rama
`codex/AARI-262-cancelacion-coordinacion`, creada desde main `e5aa612` y
rebaseada sobre `897b8bd`, después de fusionar el PR #42 aprobado de HU23.
HU y nueve subtareas AARI-263 a AARI-271 En curso; estimación preservada **4 HH**.
Publicación de HU24 autorizada por Tobías después de esa integración.
Sin horas nuevas ni cierre de Jira autorizados en esta etapa.

## Alcance y decisiones

El responsable autenticado puede cancelar esperando presupuestos, revisándolos
o esperando acordar la visita. Las dos primeras situaciones pertenecen a
`Pendiente de asignación`; la tercera a `Proveedor seleccionado`. Se bloquea
`Visita programada`, también si la fecha o una visita confirmada contradicen
el estado del reclamo. No se agregan otros puntos de cancelación ni un cierre
del reclamo. La falta de presupuestos que ya derivó en intervención manual
no amplía por sí sola las etapas habilitadas.

El usuario ve consecuencias y confirma «Sí, cancelar y volver a elegir».
Decir No no escribe nada. El servidor obtiene responsable, etapa y destinatarios;
no acepta esos datos del cliente. UUID, elección y versión del reclamo protegen
frente a doble clic, respuesta incierta, acciones antiguas y carreras con otra
decisión. Un replay autorizado devuelve el resultado histórico sin otro efecto.

La cancelación, auditoría, invalidaciones, nueva solicitud de HU17 y vuelta a
elección se guardan en una sola transacción. Se conserva el ciclo original del
responsable y la autorización extraordinaria sólo si sigue vigente. No se
reclasifica, no se modifica el contrato y no se vacía/reutiliza una decisión
anterior. Se conserva el mismo reclamo y todos sus presupuestos/conversaciones.

Se eligió una fila nueva de HU17 por intento, en lugar de sobrescribir su
decisión histórica o modificar `reclamo_responsables.solicitado_en` (lo que
invalidaría la autorización HU16). El intento original conserva cero y se
incrementa al cancelar. La solicitud nueva tiene su propio recordatorio a las
48 h y vencimiento a las 72 h. La elección vigente se determina con los campos
existentes `solicitado_en,id`, manteniendo lectura compatible antes de migrar.
La fecha de una nueva elección se fuerza posterior a la anterior.

HU17, HU18, HU19 y HU20 consultan sólo esa elección vigente para nuevas
acciones. No se borran rondas ni propuestas: la ronda anterior queda cancelada,
sus respuestas/consultas antiguas no reactivan el caso. La selección persistida
de HU20 se conserva como snapshot; se vacían sólo los punteros actuales del
reclamo para comenzar otra elección. Se puede optar después por fidelizado o
propio: esto último aún requiere la confirmación de contacto HU18.

## Avisos, historial y visitas

`cancelaciones` registra proveedor descartado cuando existe, etapa y fecha.
La auditoría privada vincula las elecciones anterior/nueva, petición, responsable,
nombre y estados. El historial del reclamo identifica la transición del usuario.

En AARI, las solicitudes anteriores quedan canceladas; con HU33 habilitada se
proyecta el evento en sus hilos individuales, conservando mensajes y lectura.
Si había proveedor seleccionado, se encola su aviso por correo; antes de esa
selección, se avisa a los proveedores alcanzados por la ronda cancelada. No se
revelan competidores ni importes ajenos. La entrega revalida cuenta, perfil y
correo del proveedor. Un correo ya aceptado por SMTP no se puede retirar.

Al llegar a tres cancelaciones, el trigger registra una alerta idempotente por
cancelación para el operador asignado activo; si falta, busca una cuenta de
administración/operación habilitada. No inventa contactos si no existe ninguna.
No se bloquea automáticamente una cuarta elección ni se crea una nueva regla
de producto. El conteo y la historia conservan la necesidad de revisión.

Si existe el esquema HU23, se invalidan sus coordinaciones aún no confirmadas,
versiones y avisos pendientes; sus hilos reciben el evento de cancelación con
HU33 habilitada. La operación usa el bloqueo común del reclamo para competir
con la confirmación de visita. La cancelación de una visita ya confirmada queda
fuera del alcance. HU21 detecta la cancelación durable al retomar; completar
todos los adaptadores/checkpoints de módulos sigue en AARI-345.

## Contrato e interfaz

- GET/POST privados `/reclamos/{id}/cancelacion-coordinacion`.
- POST: `request_id`, `eleccion_id`, `expected_updated_at` con zona y
  `confirmar` booleano estricto. Identidad y parámetros extra rechazados.
- Sólo propietario responsable del extraordinario autorizado o inquilino
  activo responsable del ordinario; administración/proveedor no cancelan.
- Respuestas exitosas `Cache-Control: no-store`; conflictos 409 y acceso ajeno
  404. Funcionalidad apagada o migración ausente: 503 controlado.
- Pantalla `/{inquilino|propietario}/reclamos/{id}/cancelar-coordinacion`, con
  acceso desde elección HU17 y comparación HU20 cuando está habilitada.
- Componentes compartidos, tokens, CSS Modules, acciones apiladas en móvil,
  confirmación que conserva foco y sigue visible aunque falle el GET posterior.
  Reintentar consulta nunca repite el POST. Un reintento incierto conserva UUID.

## Configuración y migración

Nueva variable en `backend/.env.example`, sin editar el `.env` privado:

```dotenv
AARI_CANCELLATIONS_ENABLED=false
```

Habilitar sólo después de verificar la migración e integración. No activa
workers y no cambia la configuración SMTP. Si el entorno privado del equipo
está en la raíz, agregar allí la variable junto a las demás; no hace falta
crear otro `.env` en backend. No se editó ningún archivo privado ni se agregan
dependencias.

`backend/migrations/20261103120000_hu24_cancelacion_coordinacion.sql` es una
migración incremental transaccional. Conserva datos, agrega auditoría/FK/índices
y restringe permisos mediante RLS y revocaciones. No genera cancelaciones
históricas ni correos al aplicar. **Pendiente de aplicación autorizada en
Supabase**; no se ejecuta al iniciar ni al hacer pull.

## Verificación local y límites

Las pruebas usan datos ficticios, PostgreSQL local descartable y mocks de
canales externos. No se usaron Supabase, SMTP, Gemini ni Meta reales. No sumar
las tandas siguientes como si fueran ejecuciones disjuntas de una sola suite:

- Backend general final: `python -m pytest tests -q -p no:cacheprovider --tb=short`
  → **1217 aprobadas / 552 omitidas**, 18 advertencias SQLite previas. Dotenv
  deshabilitado, SQLite en memoria, sin URL de integración PostgreSQL ni opt-ins
  externos. Esta tanda es anterior al merge de HU23; las omitidas no equivalen
  a aprobadas e incluían entonces esa dependencia ausente de main.
- Contrato HU24 aislado: **18 aprobadas**, incluidas en el total anterior.
- HU24 PostgreSQL: `python -m pytest tests/test_coordination_cancellations_postgres.py -q`
  → **23 aprobadas**. Incluye seis recorridos de etapas/gasto, nueva selección,
  alternativa propia, HTTP con repositorios reales, replay, carreras, rechazo
  de contextos viejos, rollback, alerta, auditoría inmutable y permisos.
- La tanda PostgreSQL ampliada de HU17/HU18/HU19/HU20/HU21/HU33 y HU24 tuvo
  **221 aprobadas y un fallo** de la alerta HU24. Se corrigió el campo obligatorio
  `estado_reclamo` del aviso y se repitieron el caso focalizado y los 23 casos
  HU24, todos aprobados. No se presenta aquella tanda como totalmente verde.
- Frontend completo: `npm test -- --pool=threads --maxWorkers=1 --testTimeout=20000`
  → **484 aprobadas en 45 archivos**, incluidas **12 de la pantalla HU24**.
- `npm run lint`, `npm run build` y revisión de formato correctos. Se conserva
  el aviso conocido del bundle >500 kB (556,70 kB / 155,00 kB gzip).
- QA con componentes reales y API simulada: escritorio 1440 px, móvil 390 px
  sin desborde horizontal, confirmación mediante teclado y foco en el resultado.
  Ante fallo de GET se conserva el éxito, el reintento no repite el POST y
  recupera el foco. Comprobados bloqueo de visita programada y variante de
  propietario. Se retiró la vista auxiliar ignorada y se restauró el viewport.

Las primeras ejecuciones aisladas de TestClient quedaron bloqueadas en el
socketpair/loopback de Windows; se detuvieron y repitieron con permiso local,
sin habilitar servicios externos. Se corrigieron además referencias del fixture
de ronda/consulta escalar y un literal SQL del validador de avisos que SQLAlchemy
interpretaba como parámetro. Son diagnósticos conservados, no pruebas aprobadas.

### Corrección adicional autorizada: historial de visitas canceladas

La prueba real HU23→HU24 reprodujo un 404 al abrir el hilo después de cancelar:
el lector HU23 exige la selección vigente. Los mensajes seguían en PostgreSQL,
pero el usuario no podía recuperarlos. Tobías autorizó expresamente resolverlo
desde HU24 en la API compartida de Mensajes, sin modificar el PR de Talía.

`db/cancelled_visit_history.py` reutiliza identidad/contexto, formato de mensajes
y lecturas monotónicas HU33. El origen debe estar unido a la auditoría de una
cancelación real. Revalida participantes y perfiles actuales, mantiene separadas
las audiencias inquilino/proveedor y propietario, y no concede permisos por
conocer el UUID. Permite consultar/paginar y marcar lectura; rechaza escritura
y oculta acciones de coordinación sobre ese hilo histórico. La bandeja conserva
también hilos de intentos anteriores, sin duplicar la última coordinación que
HU23 ya muestra. No modifica la selección, el grafo ni el PR #42.

La copia aislada combinó HU24 con HU23 `43a0a99`. El único conflicto de la primera
combinación estaba en `prepare_notification_delivery`: se conservaron los
validadores HU19, HU20, HU23 y HU24. No se sustituyeron routers ni workers.

`python -m pytest tests/test_coordination_cancellations_visits_postgres.py -q`
→ **12 aprobadas**: invalidación en tres etapas × dos responsables, nueva ronda
y nueva visita, reinicio/sondeo, confirmación concurrente frente a cancelación,
bloqueo posterior, audiencias/perfiles revocados y HTTP de historial con
paginación/lectura sin escritura. Antes del merge de HU23, ese módulo se omitía
en main y la copia utilizaba ambos módulos reales. El worker HU23 pagina por UUID:
el caso de reelección contempla la vuelta del cursor, sin prometer descubrimiento
instantáneo ni cambiar su intervalo.

Después del adaptador histórico se repitieron tres regresiones PostgreSQL
de Mensajes → **3 aprobadas**: proyección histórica, paginación/consultas
constantes y lecturas monotónicas con alcance autorizado. El backend general
de 1217/552 y el frontend de 484 corresponden a las versiones finales; las
35 pruebas PostgreSQL HU24/visitas son tandas separadas de esa suite general.
Revisión de patrones de secretos en los 33 archivos propios: sin coincidencias.
El cambio ajeno de HU11 conserva exactamente su contenido original.

### Integración para publicar el PR (03/11/2026)

Tobías autorizó primero fusionar el PR #42 aprobado y luego rebasear/publicar
HU24. GitHub confirmó el merge `897b8bd`, conservando la cabeza aprobada HU23
`43a0a99`. HU24 quedó rebaseada sobre ese main. Los conflictos de configuración,
Mensajes y avisos se resolvieron conservando ambas funcionalidades: lector HU23
vigente, lector histórico HU24, bandeja combinada y validadores HU19/HU20/HU23/HU24.
Se conservaron todos los routers/workers y el cambio ajeno local de HU11.

Validación repetida sobre la rama rebaseada (tandas separadas de las anteriores):

- Backend completo: `python -m pytest tests -q -x -p no:cacheprovider --tb=short`
  con `--basetemp` nuevo de la tarea → **1248 aprobadas / 604 omitidas**,
  18 advertencias SQLite previas. La primera ejecución con temporales predeterminados
  se interrumpió ante errores de preparación; con el directorio
  nuevo terminó completa, sin fallos. Sin URL PostgreSQL ni opt-ins externos.
- PostgreSQL local descartable: `python -m pytest` con
  `test_coordination_cancellations_postgres.py`,
  `test_coordination_cancellations_visits_postgres.py`, `test_visits_postgres.py`,
  `test_visits_hu20_integration_postgres.py` y `test_conversations_postgres.py`,
  `-q -p no:cacheprovider --tb=short` → **101 aprobadas**. Incluye los módulos
  reales HU20/HU23/HU24, concurrencia y el historial compartido de Mensajes.
- Frontend afectado: `npm test --` con las siete suites de cancelación,
  comparación, elección, visitas y Mensajes, `--pool=threads --maxWorkers=1
  --testTimeout=20000` → **88 aprobadas**. No se presenta como otra ejecución
  completa del frontend.
- `npm run lint` y `npm run build` correctos. Bundle integrado de 571,50 kB
  (158,81 kB gzip); conserva el aviso previo de tamaño >500 kB.

La migración HU24 sigue pendiente de aplicación compartida autorizada; el merge
HU23 no la aplica. No repetir las tres migraciones HU20/HU23 ya registradas.
El cierre final requiere revisión humana y validación compartida autorizada.
AARI-345 se conserva como tarea aparte y no se considera resuelta por este PR.
