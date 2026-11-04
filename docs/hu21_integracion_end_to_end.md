# AARI-345 — Integración final del contexto HU21

Propuesta aprobada por Tobías el 04/11/2026. Rama
`codex/AARI-345-integracion-contexto` desde main `82966cc`, después del merge
autorizado del PR #43 de HU24. AARI-345 y subtareas AARI-236/AARI-237 En curso.
La previsión histórica sigue siendo 65 + 20 minutos; no se registran horas
automáticamente ni se duplican las de HU21 base o las de HU24.

## Problema y objetivo

Los módulos de negocio ya persistían decisiones, presupuestos, visitas y
cancelaciones, pero el contexto HU21 sólo se actualizaba al retomar. Después
de programar una visita, su GET informaba una diferencia y `retomar` rechazaba
el estado terminal: el checkpoint anterior quedaba pendiente de sincronización.
La etapa de selección de presupuesto estaba reservada, sin usar el cierre real
de la ronda. La base HU21 cerrada en AARI-229 no acreditaba estos recorridos.

Esta entrega proyecta los hechos confirmados de HU16/17/18/19/20/23/24 en HU21.
Conserva la identidad vigente de HU32 y la historia separada de Mensajes HU33.
No crea otro chat, no interpreta texto libre con un LLM y no decide por los
módulos. La visita programada sigue siendo el fin de coordinación, no una
reparación resuelta.

## Decisión: reconciliación durable mediante el worker existente

Se consideró escribir checkpoints desde cada transacción de dominio. Acoplaría
todos los módulos al almacenamiento de LangGraph y mezclaría la conexión
SQLAlchemy del dominio con la conexión psycopg de PostgresSaver. Tampoco basta
un callback en memoria después del commit: un reinicio podría perderlo.

Se elige leer el dominio confirmado desde el worker HU21 existente. Los hechos
persistidos son el trabajo recuperable: una caída entre el commit del módulo
y la proyección no pierde la decisión. Cada reconciliación guarda snapshot,
checkpoint PostgresSaver y evento de sistema juntos, en su propia transacción.
Si falla, se revierten los tres; la decisión de negocio ya confirmada permanece
intacta y se vuelve a proyectar en un recorrido posterior.

Se procesan sólo sesiones inicializadas, con versión positiva. No se inicializa
automáticamente toda la historia ni se usa GET como comando. El mecanismo de
inicio sigue siendo el POST deliberado de HU21. GET conserva lectura sin efectos
y puede informar `requiere_sincronizacion=true` hasta que pase el worker.

El worker recorre páginas por UUID, por defecto de 20 elementos, y vuelve al
inicio al acabar. Omite reclamos bloqueados con `SKIP LOCKED`; una página sin
cambios o con un fallo no acapara las siguientes. El cursor en memoria sólo
optimiza el recorrido: tras reiniciar vuelve a comenzar y no duplica versiones
de un contexto que ya coincide. No se promete sincronización inmediata ni un
checkpoint por cada paso intermedio ocurrido entre dos sondeos; la auditoría
completa de decisiones permanece en sus módulos.

El orden del worker es reconciliación y luego expiración. Sigue el intervalo
existente de 30 segundos y el flag `COORDINATION_WORKER_ENABLED=false` por
defecto. No se activó en el entorno compartido durante esta implementación.
Cada candidato a vencimiento reconcilia además su propio contexto bajo el lock
del reclamo y en la transacción de expiración: el orden de los lotes por sí solo
no garantiza que ese reclamo ya haya sido proyectado.

## Proyección e invariantes

- Elección del ciclo vigente del responsable y último intento HU17, sin leer
  decisiones históricas como nuevas acciones.
- Ronda vinculada a esa elección. Recibir un presupuesto durante la recepción
  no adelanta la etapa: `esperando_seleccion_presupuesto` requiere el cierre
  durable con estado `disponibles`. Revisión/sin presupuestos conserva la
  intervención manual.
- Presupuesto/proveedor de HU20 vinculados a su selección auditada y al intento
  vigente. No se eligen ni confirman al proyectar.
- Coordinación HU23 ligada a esa selección: disponibilidad, confirmación,
  negociación y visita programada. Un hilo o una coordinación de otro intento
  no vuelve a habilitar el actual.
- Carga de datos del proveedor propio y derivación externa HU18 sin crear una
  cuenta de proveedor ni confirmar una visita propia automáticamente.
- Cancelación HU24 confirmada: nuevo UUID de intento una sola vez, nueva
  elección y conservación del reclamo, autorización vigente, presupuestos y
  conversaciones. Un evento antiguo no genera otra elección.
- Estado terminal confirmado: sesión `finalizada`, snapshot/checkpoint con el
  estado real. `retomar` sigue rechazándolo; sincronizar no lo reabre.

El contrato agrega campos opcionales de elección, ronda, selección y visita
al dominio del snapshot. Los snapshots de versión 1 anteriores siguen siendo
legibles con esos campos ausentes. No hay DDL ni migración de datos históricos.
Esto acredita lectura de snapshots antiguos por esta versión, no lectura de los
campos/etapas nuevos por un binario anterior. Antes de habilitar, actualizar
todos los lectores/workers HU21; no mezclar versiones antiguas ni hacer un
downgrade que pierda compatibilidad con los nuevos snapshots persistidos.
La lectura de participantes revalida cuenta habilitada, rol, perfil vinculado
y, para el inquilino, estado y unidad vigentes. El endpoint HU21 no concede
acciones de proveedor ni cambia los permisos de los módulos ajenos.

Los eventos internos de proyección usan el `usuario_id` nulo ya permitido por
el esquema HU21: no atribuyen una acción de sistema a una persona. No contienen
contactos, texto de mensajes ni secretos. Los errores de lote se registran sin
identificadores personales o credenciales.

## Plazos

`ultima_actividad` conserva el contrato de la base: sólo una reanudación válida
lo renueva. GET, conversaciones, sondeos, sincronizaciones, reintentos idénticos
y operaciones rechazadas no lo reinician.

Se proyectan los plazos propios de autorización/elección, ronda abierta y
confirmación/negociación de visita. Su expiración corresponde a cada módulo;
HU21 no sustituye las 24 horas de presupuestos o visita ni renueva sus fechas.

La expiración general de 72 horas se conserva para las etapas HU21 previstas
sin un vencimiento específico. Se conecta también la etapa ya reservada de
elección de presupuesto: sólo tras cerrar una ronda vigente con presupuestos
disponibles, cuando el reclamo espera esa decisión. La selección y el vencimiento
compiten bajo el bloqueo del reclamo; se conserva un único aviso por intento.
No se agregan nuevos vencimientos para carga de proveedor propio, gestión manual,
expensas o visitas programadas.

## Archivos principales y operación

- `backend/app/db/coordination_domain.py`: lectura acotada de módulos disponibles.
- `backend/app/db/coordination.py`: permisos, reconciliación, locks, checkpoints
  y convivencia del expirador con las etapas reales.
- Contrato/grafo en `backend/app/agents/coordination/` y servicio/worker HU21.
- Pruebas de recorrido y regresiones HU21/HU20/HU23.

No se instalaron dependencias, no se cambiaron valores privados de `.env` ni
se aplicaron migraciones en Supabase. Para habilitar el worker en un entorno
compartido siguen siendo necesarias autorización y verificación del esquema
HU21 y de los módulos instalados. La migración HU24 permanece pendiente de su
aplicación autorizada; hacer pull o iniciar FastAPI no la ejecuta.

## Validación

Las pruebas usan PostgreSQL local descartable, los repositorios reales de
los módulos y cuentas/perfiles sintéticos. Los canales externos permanecen
simulados o sin invocar. No se consumen Supabase, SMTP, Gemini ni Meta reales.
Los cinco recorridos iniciales de la base con adaptadores simulados se conservan
como pruebas de contrato; no sustituyen esta integración real.

La matriz nueva incluye ordinario con confirmación directa, extraordinario
autorizado con negociación y Mensajes, proveedor propio en ambos tipos de gasto,
y cancelación/reelección durante recepción, comparación y espera de visita.
Se comprueban también rechazo, reinicio de repositorio entre turnos, dos workers,
rollback tras el checkpoint, permisos revocados, cursor y expiración en el
límite exacto de 72 horas. Los primeros fallos de fixture (forma de la propuesta,
clave `request_id` de autorización, literal SQL interpretado como bind y
restricciones de los datos sintéticos de unidad/nombre) se
corrigieron antes de la tanda final; no se cuentan como validación aprobada.

Resultados finales del 04/11/2026, en tandas separadas que no se suman por
solapamiento:

- Backend completo sin integración PostgreSQL ni opt-ins externos:
  `python -m pytest tests -q -x -p no:cacheprovider --tb=short`
  con `--basetemp=artifacts/a345-u2` → **1257 aprobadas / 624 omitidas**,
  18 advertencias SQLite preexistentes. Las omitidas no equivalen a aprobadas.
  Incluye las 35 pruebas aisladas de HU21, nueve nuevas.
- PostgreSQL real local:
  `python -m pytest tests/test_coordination_workflow_postgres.py
  tests/test_coordination_postgres.py tests/test_coordination_provider_choice_postgres.py
  tests/test_visits_hu20_integration_postgres.py
  tests/test_coordination_cancellations_visits_postgres.py -q -x
  -p no:cacheprovider --tb=short` → **82 aprobadas**, incluidas **20 nuevas**
  de AARI-345. Repositorios recreados entre turnos y recuperación del checkpoint
  en otro proceso en la regresión base; sin reemplazar decisiones por UPDATE de
  fixtures. Los cambios de reloj/datos sintéticos preparan bordes temporales,
  perfiles revocados y competencia de locks, no resultados de negocio.
- Primera pasada general: **414 aprobadas, 21 omitidas y un fallo** en
  `test_contract_recovery_diagnostic`, módulo sin cambios en esta rama.
  Repetición aislada con temporales nuevos → **18 aprobadas**. Repetición
  completa con un directorio temporal nuevo y más corto → los **1257/624**
  indicados arriba, sin modificar código de contratos ni omitir ese módulo.
- Compilación Python, revisión del diff/formato y patrones de secretos de las
  adiciones correctos. El cambio ajeno de HU11 se conserva byte por byte.

No se cambió frontend: no se atribuye una nueva ejecución de su suite a esta
entrega. No se instalaron dependencias ni se habilitaron workers compartidos.
Las bases descartables se eliminaron y PostgreSQL local quedó detenido.

## Estado de entrega

Implementación y publicación de commit/push/PR autorizadas por Tobías el
04/11/2026, para revisión de Talía. AARI-345 y sus subtareas permanecen En curso;
las horas reales requieren confirmación de Tobías. El PR #43 ya
integrado no acredita aplicación de la migración HU24 ni QA compartido de esta
integración. La revisión humana y la habilitación compartida siguen pendientes.

La documentación se mantiene en GitHub. Notion no es un requisito de cierre.

## Corrección P2 de revisión — coherencia del intento al expirar

Talía señaló en la [revisión del PR #44](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/44#issuecomment-6639894534)
que los lotes de sincronización y vencimiento usan órdenes distintos. Si HU24
cancelaba y se completaba una reelección/ronda antes de que pasara el reconciliador,
el expirador podía copiar el nuevo `cancelacion_id` conservando el intento viejo.
El contexto parecía actualizado y la reconciliación posterior ya no detectaba
la necesidad de renovar ese intento.

Se reprodujo el fallo con ambos tipos de gasto y el cursor del reconciliador
fuera de la página: dos pruebas fallaron en la igualdad indebida del intento.
La corrección reutiliza `_synchronize` por candidato dentro de `expire_due`,
con el mismo lock y transacción, tras validar etapa/plazo/receptor. Luego relee
la sesión validada antes de construir el snapshot de expiración y la alerta.
Así sesión, checkpoint, contexto y clave idempotente del aviso comparten el
intento vigente. Si ya estaba sincronizado no se renueva otra vez. Una proyección
pendiente puede incrementar su versión y luego la de expiración, ambas atómicas;
no renueva actividad ni cambia la regla de 72 horas.

Las ocho regresiones nuevas cubren ordinario/extraordinario con y sin
sincronización previa, rollback de la proyección/expiración si falla la alerta
y concurrencia entre seleccionar un presupuesto y expirar. Usan los repositorios
reales y comprueban también el checkpoint PostgresSaver, el intento de la alerta
y que los sondeos posteriores no vuelvan a mutar el resultado.

La tanda focalizada de la corrección aprobó **8 casos**. La regresión general
posterior aprobó **1257 pruebas / 632 omitidas**, con las 18 advertencias SQLite
previas. La primera pasada de esta revisión se detuvo con 359 aprobadas, 21
omitidas y un fallo de `test_contract_direct_diagnostic`, fuera del diff; sus
19 pruebas pasaron aisladas con temporales nuevos y también pasó la repetición
general completa, sin modificar ni omitir el módulo.

La tanda completa de PostgreSQL posterior a la corrección aprobó **90 casos**,
sin omisiones, incluidas las 28 pruebas de integración AARI-345 (20 originales
y las ocho de este P2), más las regresiones HU21/HU17/HU20/HU23/HU24. Se repitió
el mismo comando de cinco suites indicado arriba, con temporales nuevos
`--basetemp=artifacts/r44pg`. El backend general utilizó
`--basetemp=artifacts/r44u2`. Compilación, formato y revisión de secretos de las
adiciones correctos; no se ejecutaron servicios externos ni se activaron
workers compartidos. Estos totales incluyen los casos focalizados: no sumarlos.
