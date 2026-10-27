# HU19 / AARI-206 — respuestas, plazos y avisos

## Estado — 25/10/2026

Continuación aprobada: AARI-212/213/214/215/216 y pruebas AARI-218/219, en
`codex/AARI-206-solicitudes-presupuesto`. Fetch confirmó `origin/main` en
`19d06fa7eb9fe543fe960eff58cc852981e02a23`, igual al origen de esta rama.
No hizo falta rebase; se conservaron todos los archivos de las etapas anteriores.
No se hicieron commits ni push. HU/subtareas En curso. La responsable pidió
registrar 1 HH adicional al terminar: 30m AARI-213, 20m AARI-214 y 10m AARI-218,
sin duplicarlo en la historia padre ni modificar estimaciones.

Se completa el negocio local, no la habilitación externa ni el QA real de Meta.
Sin llamadas reales a WhatsApp/Gemini/SMTP, cambios en Supabase o frontend.
No se instaló OpenWA ni se vinculó un teléfono a una integración no oficial.

## Lectura conservadora, sin inferir dinero con IA

El presupuesto automático exige un único importe positivo dentro de numeric(12,2),
moneda explícita y descripción identificable. Usa Decimal, no float. Acepta
ARS/pesos o USD/dólares; no convierte ni compara monedas. Un signo `$` solo no
implica ARS. Los presupuestos históricos mantienen moneda/procedencia NULL:
no se les atribuye información que no estaba registrada.

Ejemplo, respondiendo al mensaje original:

```text
Monto: ARS 12.500,50
Trabajo: Reparación de la cañería debajo de la pileta.
```

Acepta entero, notación argentina de miles/decimales y decimal sin miles
`12500.50`. No acepta automáticamente formato `12,500.50`, varios importes,
porcentajes, cuotas, anticipos, rangos o valores condicionales («desde», «más IVA»,
«no incluye»). Otras cifras ambiguas también requieren revisión. No interpreta
cualquier texto libre: prioriza no registrar un precio inventado.

Alternativas consideradas: LLM (cuota, dependencia externa e interpretación de
precios), imponer una moneda/cálculo implícitos (riesgo económico), lectura
determinista explícita (elegida). No hay entrenamiento ni se afirma precisión
general sobre lenguaje natural. La plantilla ya pide importe, moneda y trabajo;
no se creó/aprobó una plantilla nueva en Meta.

## Correlación, transacción y auditoría

- Vincula por context.id del mensaje original o UUID explícito de solicitud,
  nunca sólo por teléfono. Verifica cuenta/número y contacto congelado.
- Referencias contradictorias, remitentes ajenos y solicitudes desconocidas no
  generan presupuestos. Si el webhook se adelanta al commit del ID de Meta,
  espera el intento activo sin adivinar una asociación.
- Revalida ciclo HU17, autorización HU16, cuenta/actor, asociación del inquilino
  y huella del reclamo. Los ciclos obsoletos no se reactivan.
- Sólo admite solicitudes aceptadas por Meta, fechas coherentes y respuesta
  recibida dentro del plazo. Los envíos inciertos necesitan revisión.
- Presupuesto, resultado de procesamiento y aviso se confirman juntos. Una
  falla revierte todo y permite recuperar el evento pendiente.
- Un mensaje se procesa una vez; una solicitud admite un presupuesto automático.
  Otra cotización se audita para revisión, sin sobrescribir el precio anterior.
- Bloqueos reclamo → solicitud → inbox, unicidades y FK compuesta protegen
  duplicados y correspondencia de solicitud/proveedor/reclamo.

La bandeja privada conserva el original, incluso si la respuesta es ambigua,
tardía o no soportada. No se registran conversaciones/credenciales en logs.
Entrega/lectura son eventos de transporte, no presupuestos ni aceptación del trabajo.

## Plazos y salida hacia HU20

Cada solicitud inicia sus 24 h desde la aceptación de Meta. La ronda espera el
último vencimiento de los pedidos aceptados: cada proveedor conserva su plazo
completo. Fechas UTC persistidas, independientes de la reserva técnica de envío
y de la ventana comercial de WhatsApp.

Sin un envío aceptado no se inventa un vencimiento. Con canal apagado sigue
sin_envios. Si todos los intentos terminaron rechazados/inciertos, se cierra en
revision con alerta al operador, sin acusar al proveedor de no contestar.

Al vencer, consume antes las entradas guardadas a tiempo; si queda una pendiente,
no cierra prematuramente. Con al menos un presupuesto válido cierra disponibles,
aunque sean parciales, sin elegir/contratar. Sin ninguno y sin fallo de canal,
cambia a Sin presupuestos recibidos, con historial origen agente y alerta atómicos.
Con envíos incompletos/inciertos/fallidos cierra revision, sin ese cambio de estado.
Si cambió el contexto, cancela la ronda sin pisar el reclamo.

No despacha pedidos nuevos en rondas vencidas/cerradas. Una respuesta tardía queda
auditada y no reabre la ronda. Una confirmación tardía del mismo intento puede
registrar aceptación, pero no reabre ni extiende una ronda ya cerrada.

El checkpoint HU21 no se sobrescribe ni rejuvenece. Vista comparativa, selección
y proyección de esa etapa pertenecen a HU20/integración AARI-345, no se anticipan.

## Avisos y revisión

El primer presupuesto encola un aviso único al responsable actual, con su canal.
Los casos sin presupuesto/con fallos alertan al operador asignado; se reutiliza
la selección HU12 si no está disponible (operador activo, luego administrador).
No se inventan contactos. Las claves idempotentes separan disponibilidad,
revisión inicial y cierre: una alerta anterior no oculta el vencimiento.

Se reutiliza notificaciones; el consumidor no ejecuta SMTP/WhatsApp. La entrega
depende del worker/canal. El adaptador genérico de avisos WhatsApp sigue apagado;
no se promete su entrega sin acordar y probar plantilla/ventana reales.

Los mensajes no correlacionables se auditan sin adjudicar un reclamo ajeno.
Los correlacionables ambiguos encolan revisión. No se creó un visor ni una acción
administrativa para corregir cotizaciones: evidencia en tablas privadas y avisos
sin contenido del mensaje. Una interfaz de resolución requiere acordar su alcance.

## Archivos y despliegue

- app/services/quote_response_parser.py: importes y rechazo seguro.
- app/db/quote_responses.py: correlación, consumo, persistencia, plazos y avisos.
- app/services/quote_responses.py: worker opcional sin APIs externas.
- app/db/quote_requests.py: plazos durables y guardas de despacho.
- app/main.py y .env.example: QUOTE_RESPONSES_WORKER_ENABLED=false.
- Migración adicional 20261025160000_hu19_respuestas_presupuesto.sql.

DDL aditivo: fechas/ronda, moneda y procedencia nullable para filas históricas,
y presupuesto_respuestas como auditoría. RLS, revocación PUBLIC/anon/authenticated,
sin políticas públicas, seeds, envío ni modificación de importes anteriores.
Si otra instalación ya aceptó solicitudes con el bloque previo, deriva sus
nuevos vencimientos de aceptado_en; nunca los reinicia desde la fecha de migración.
Orden: 20261019230000 → 20261020120000 → 20261025160000. **Ninguna aplicada en
Supabase**. No hay DDL al arrancar. Aplicación compartida, activación de workers
y callback público requieren autorización separada.

## Validación

PostgreSQL 18.1 local, clúster nuevo en loopback y bases descartables; todos los
datos son ficticios. Mocks exclusivos de tests, sin endpoint público sin firma.
Resultados por ejecución, sin sumar repeticiones:

- Parsing, worker y transporte HTTP simulado: **138 aprobadas**, 1,47 s.
- Regresión backend integrada con PostgreSQL local: **1279 aprobadas / 51 omitidas**,
  1539,15 s. Excluido únicamente el benchmark preexistente HU15
  test_provider_candidates_volume_postgres.py; no se presenta como ejecutado.
  Las omisiones corresponden a integraciones opcionales/externas; no las acredita.
  Hubo 18 avisos SQLite preexistentes (operadores/property_claims).
- Última pasada específica de respuestas: **36 aprobadas**, 942,18 s. Incluye
  cinco casos adicionales a los 31 ya recogidos por la regresión general:
  propietario autorizado, dos respuestas distintas concurrentes, reserva vencida,
  FK de proveedor y migración con presupuestos/aceptaciones anteriores. No sumar
  las 36 al total general porque se solapan. Incluye ingreso real al endpoint
  local con firma sintética y escritura PostgreSQL, no un envío real por Meta.
- pip check y git diff --check correctos. No se modificó ni volvió a probar frontend.

Las primeras pasadas detectaron errores en los tests: un patrón LIKE con dos
puntos se interpretaba como parámetro SQL y el viaje temporal de una reserva
simulada infringía sus propias restricciones. Se corrigieron los fixtures y se
repitieron los casos; las corridas fallidas/interrumpidas no se cuentan como
aprobadas. No se relajaron controles de importes, firma, datos o base para pasarlos.

Comandos desde backend, usando el Python de tmp/hu19-venv y un clúster QA local
nuevo (nunca reemplazar estas URL por Supabase):

```powershell
$env:DATABASE_URL='sqlite:///:memory:'
$env:AARI_TEST_POSTGRES_URL='postgresql+psycopg2://aari_qa@127.0.0.1:55425/postgres'
$env:AARI_WHATSAPP_TEST_POSTGRES_URL='postgresql+psycopg2://aari_qa@127.0.0.1:55425/test_aari_hu19'
$env:NOTIFICATION_WORKER_ENABLED='false'
$env:CONTRACT_ANALYSIS_WORKER_ENABLED='false'
$env:PROVIDER_CANDIDATES_WORKER_ENABLED='false'
$env:COORDINATION_WORKER_ENABLED='false'
$env:CONTRACT_ANALYSIS_EXTERNAL_ENABLED='false'
$env:PROVIDER_SPECIALTY_EXTERNAL_ENABLED='false'
$env:WHATSAPP_WEBHOOK_ENABLED='false'
$env:WHATSAPP_OUTBOUND_ENABLED='false'
$env:QUOTE_REQUESTS_WORKER_ENABLED='false'
$env:QUOTE_RESPONSES_WORKER_ENABLED='false'
$env:LANGCHAIN_TRACING_V2='false'
$env:LANGSMITH_TRACING='false'
$env:RUN_SUPABASE_INTEGRATION='0'
python -m pytest -q --tb=short -p no:cacheprovider --ignore=tests/test_provider_candidates_volume_postgres.py --basetemp=RUTA_ABSOLUTA_NUEVA_QA
python -m pytest -q --tb=short -p no:cacheprovider tests/test_quote_responses_postgres.py --basetemp=OTRA_RUTA_ABSOLUTA_NUEVA_QA
python -m pip check
git diff --check
```

Las bases por caso se crean con UUID y se eliminan al terminar. La base de
transporte test_aari_hu19 también debe ser nueva y descartable. basetemp debe
ser una carpeta nueva y exclusiva: pytest puede borrar su contenido. El clúster
local sólo escucha en loopback y se detiene al finalizar; no usar en producción.

## Pendientes externos y límites

Revisión del navegador AARI del 25/10: cuenta de test sigue restringida, sin
respuesta nueva de soporte. Los dos casos anteriores cerrados; el trámite del
24/10 quedó sin enviar y no generó un caso nuevo. No se presupone que pagar,
cargar un acta académica o recrear cuentas resolverá el bloqueo.

Pendientes: configuración privada, plantilla/callback, migraciones compartidas
autorizadas y prueba real completa. No acredita entrega ni respuesta real de un
proveedor. La HU no se da por cerrada con mocks ni por tener un token.
