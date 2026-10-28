# HU19 / AARI-206 — solicitudes de presupuesto

> Estado actualizado del 25/10: [respuestas, plazos y avisos](hu19_respuestas_presupuesto.md).
> El contenido siguiente conserva alcance y evidencia del bloque del 20/10.

## Alcance aprobado y estado — 20/10/2026

Segunda etapa: AARI-207 (candidatos), AARI-209 (mensaje) y AARI-210 (solicitud y
auditoría). En curso en Jira, junto a la HU. No se presenta la historia completa
como finalizada: interpretar respuestas, guardar presupuestos, vencimientos y
avisos pertenecen al siguiente bloque y aún no están implementados aquí.

Rama actual: `codex/AARI-206-solicitudes-presupuesto`, desde main
`19d06fa7eb9fe543fe960eff58cc852981e02a23`, que incluye HU16, HU17 y HU21.
La base anterior quedó intacta en `codex/AARI-206-whatsapp-base`; se copiaron sus
12 archivos nuevos y se compararon sus hashes. Los cambios de archivos comunes
se reaplicaron sobre main conservando los routers y workers de las otras HU.
No se crearon commits, push ni PR. El nuevo entorno Python es local y aislado,
instalado desde los requirements vigentes, sin cambiar el entorno compartido.

## Decisión y motivo

Solicitar presupuesto tiene un efecto externo distinto de obtener candidatos:
no debe hacerlo un reclamo sólo por haber sido clasificado ni por aparecer en
HU15. Se necesita la elección fidelizada confirmada y, para extraordinarios, la
autorización del propietario. Se revalida antes de enviar y se registra cada paso.

Se usa una outbox específica: el worker genérico de avisos reintenta y podría
duplicar solicitudes después de un timeout. Tampoco se llama a Meta dentro de
una transacción SQL: la marca durable del intento confirma primero, se hace una
sola llamada y se guarda su resultado después. Un corte entre esos pasos deja
un resultado incierto para revisión, no un permiso para volver a enviar.

No se incorpora un LLM, no se cambia el canal a Telegram ni se implementa
coordinación de visitas en este bloque. La tabla `presupuestos` ya existe desde
el Sprint 0; no se recrea ni se llenan montos a partir de confirmaciones de entrega.

## Flujo implementado

1. El worker opcional descubre reclamos habilitados y todavía sin ronda para la
   elección HU17 vigente. También funciona después de reiniciar el servidor.
2. Revalida decisión, actor actual, cuenta activa y primer ingreso completado,
   inquilino aún asignado, ausencia de proveedor/presupuesto seleccionado y estado
   `Pendiente de asignación`. Para extraordinario exige la autorización de ese
   mismo ciclo y propietario. Propio, expensa, rechazo, falta de autorización,
   reclamos cerrados y decisiones históricas no habilitan solicitudes.
3. Reutiliza las reglas deterministas HU15 para candidatos activos con especialidad
   y cobertura exactas. Sin barrio, sólo cobertura de toda la localidad. No usa el
   buscador libre del padrón ni interpreta la cobertura con IA.
4. Guarda una ronda por elección y un pedido por proveedor, atómicamente con su
   primer evento. Congela criterios, descripción, ubicación y contacto para poder
   explicar posteriormente a quién se solicitó y por qué. La primera preparación
   sin candidatos queda auditada, no dispara envíos o avisos nuevos ni se amplía
   silenciosamente al editar el padrón. Un nuevo ciclo requiere decisión explícita.
5. Si el canal está habilitado, configurado y el teléfono está en la lista de
   pruebas, reserva **un único pedido** por vez durante 60 segundos. No reserva
   lotes que puedan vencer mientras está enviando el primer mensaje.
6. Relee los datos, autorización y compatibilidad; si cambió el contacto, el
   problema, la propiedad, el actor o la habilitación, marca `omitida` y conserva
   el motivo. No envía a un teléfono nuevo usando una reserva vieja.
7. Confirma `enviando`, token de intento, plantilla e IDs del canal antes de HTTP.
   El adaptador oficial realiza una sola petición, con timeout de 10 s.
8. Guarda `aceptada` y el ID de Meta, o `rechazada`/`desconocida`. Aceptación no
   acredita entrega, lectura, presupuesto, contratación ni visita.

No se cambia `reclamos`, sus autorizaciones, elecciones, historial de estados
o notificaciones al preparar/despachar. El checkpoint HU21 no se sobrescribe ni
se renueva por una reserva interna. La auditoría tiene tablas propias.

## Mensaje y configuración

Contenido propuesto, versionado como `hu19_presupuesto_v1`:

> AARI · Solicitud [UUID del pedido]. Problema: [descripción]. Ubicación:
> [dirección, localidad, provincia, piso/unidad si corresponde]. Plazo de
> respuesta: 24 horas. Respondé a este mensaje indicando importe, moneda y
> descripción del trabajo. Esta solicitud no confirma una contratación ni una visita.

El adaptador entrega cuatro parámetros al cuerpo de una plantilla de Meta:
referencia, problema, ubicación y `24 horas`. `QUOTE_REQUEST_TEMPLATE_NAME`
debe corresponder **exactamente** a una plantilla ya aprobada con ese contenido,
orden e idioma; crear/aprobar plantillas en Meta no forma parte de esta entrega.
No se inventan prefijos para teléfonos históricos inválidos. No se envían nombres,
documentos, contratos, fotos ni teléfonos personales del responsable como parámetros.
La dirección y descripción siguen siendo información privada, no apta para logs.

Tres interruptores independientes, todos apagados en `.env.example`:

| Variable | Efecto |
| --- | --- |
| `QUOTE_REQUESTS_WORKER_ENABLED=false` | No descubre/prepara ni procesa pedidos al iniciar. |
| `WHATSAPP_OUTBOUND_ENABLED=false` | Permite probar preparación sin hacer HTTP. |
| `WHATSAPP_WEBHOOK_ENABLED=false` | El receptor GET/POST no queda expuesto por defecto. |

El envío también exige configuración válida y destinatario explícito en
`WHATSAPP_TEST_RECIPIENTS` (máximo cinco distintos). Los demás pedidos permanecen
pendientes: la aplicación no los inscribe ni consume sus cupos en Meta. Nombre
de plantilla vacío, idioma inválido o credenciales incompletas no reservan pedidos.
No hay endpoint público, botón nuevo o modo HTTP falso habilitable en producción.
Las simulaciones son dobles exclusivos de las pruebas.

**Los tres tiempos son distintos:** la reserva interna de 60 segundos evita
procesos duplicados; el mensaje comunica 24 horas para cotizar; la ventana de
atención de WhatsApp es una regla del canal. Este bloque no implementa todavía
el job AARI-214 ni abre una ventana de atención por enviar una plantilla.
Se conserva `aceptado_en`, pero no se hace avanzar el reclamo por un timeout.

## Concurrencia, cortes y límites

- Unicidad de ronda por elección y de pedido por ronda/proveedor.
- Bloqueo reclamo → outbox y reserva con `SKIP LOCKED`; token distinto en cada reserva.
- La reserva vieja no puede iniciar ni finalizar un intento de otro proceso.
- Si venció `reservada` sin haber marcado envío, vuelve a pendiente; no salió HTTP.
- Si venció `enviando`, pasa a desconocida y nunca se reenvía automáticamente.
- Una confirmación tardía del mismo token puede resolver desconocida a aceptada,
  sin otra llamada y sin reemplazar el resultado de otro intento.
- Intentos acotados a uno en este bloque. Un reenvío manual exige diseño y
  autorización posteriores; no existe un botón para eludir esa protección.
- Si falló el commit previo a HTTP, no se llama a Meta. Si falló después de que
  Meta aceptó, el pedido queda en enviando y luego desconocido para revisión.
- No se mantiene una transacción abierta durante la red. Un cambio posterior al
  último control no puede retirar un mensaje ya salido: se conserva el resultado,
  sin contratar ni seleccionar automáticamente. No se promete envío exactamente
  una vez bajo cualquier fallo distribuido; se evita el reintento incierto.

## Persistencia y despliegue

Se conserva la migración de recepción `20261019230000_hu19_whatsapp_base.sql` y
se agrega `20261020120000_hu19_solicitudes_presupuesto.sql`:

- `reclamo_rondas_presupuesto`: elección, criterios/huella y resultado de preparación.
- `proveedor_solicitudes_presupuesto`: contacto, parámetros/mensaje, reserva,
  estado e intento, plantilla/activos utilizados e ID de Meta.
- `solicitud_presupuesto_eventos`: eventos/motivos seguros, sin secretos ni errores
  arbitrarios de terceros. Sin API pública de lectura ni cambios a eventos previos.

FK, CHECK, unicidades e índices; RLS en todas y revocaciones a
PUBLIC/anon/authenticated, sin políticas públicas. Migraciones de ejecución única,
sin seeds, envíos ni cambios a filas anteriores. **No aplicadas en Supabase**.
No hacer setup/DDL al iniciar el worker. Aplicar y habilitar requieren autorización.

Archivos principales: `app/db/quote_requests.py`, `app/services/quote_requests.py`,
`app/schemas/quote_requests.py`, `app/main.py`, `.env.example`, migración y pruebas.
No se modificó el frontend ni se cambió el resto de las historias integradas.

## Validaciones

Primer bloque focalizado: **52 aprobadas** (34,68 s). Después de agregar los casos
de cortes al commit, 100 candidatos y conservación de HU21: **58 aprobadas**
(54,85 s), incluidos PostgreSQL 18.1 local y Meta simulado. No sumar ambas pasadas.
Regresión inicial sobre main actualizado, sin PostgreSQL opcional:
**987 aprobadas / 272 omitidas / 18 avisos SQLite preexistentes**, 20,49 s;
se excluyó el archivo PostgreSQL de solicitudes porque ya se ejecutó aparte.
Regresión integrada final con PostgreSQL local: **1216 aprobadas / 51 omitidas /
18 avisos SQLite preexistentes**, 496,09 s. Se excluyó únicamente el benchmark
preexistente `test_provider_candidates_volume_postgres.py`; sí se ejecutaron los
100 candidatos de esta entrega. Las pruebas externas permanecieron deshabilitadas.
`pip check` correcto en el entorno nuevo instalado desde requirements vigentes.

Comandos desde `backend/`, con workers, APIs externas y tracing apagados:

```powershell
# Usar exclusivamente el clúster QA local, no la URL de Supabase.
$env:DATABASE_URL='sqlite:///:memory:'
$env:AARI_TEST_POSTGRES_URL='postgresql+psycopg2://aari_qa@127.0.0.1:55419/postgres'
$env:AARI_WHATSAPP_TEST_POSTGRES_URL='postgresql+psycopg2://aari_qa@127.0.0.1:55419/test_aari_hu19'
python -m pytest -q -p no:cacheprovider tests/test_quote_requests.py tests/test_quote_requests_postgres.py
python -m pytest -q -p no:cacheprovider --ignore=tests/test_provider_candidates_volume_postgres.py --basetemp=RUTA_ABSOLUTA_NUEVA_DE_QA
python -m pip check
```

El runner PostgreSQL valida loopback y crea/elimina una base nueva por caso. El
basetemp debe ser nuevo y descartable: pytest puede eliminarlo. La recepción usa
otra base nueva llamada `test_aari_hu19`; nunca reutilizarla con datos de negocio.
Las suites automatizadas no ejecutaron pruebas contra Supabase ni llamadas a
WhatsApp, Gemini o SMTP. Los intentos manuales posteriores en el panel de Meta
se distinguen a continuación y no forman parte de esos resultados automatizados.

## Meta y próximos pasos

Revisión del navegador AARI del 20/10: inicialmente Paso 1 no tenía un número
disponible. Tras autorización específica se pulsó **una única vez** «Solicitar
número de prueba». Meta terminó mostrando **Completado** y un número de test
asignado a la aplicación actual. No hubo reintentos ni se crearon otras apps.
Los identificadores quedan en la configuración privada, no en este documento.

El token **no** se generó automáticamente. Después de la autorización específica
para «Generar identificador», la responsable completó el acceso de Facebook y la
selección de la nueva cuenta de prueba, sin acceso a todas las cuentas futuras.
Se verificó en la interfaz el token generado y la opción «Generar nuevo
identificador». No se guardó la clave en archivos ni se incluyó en mensajes,
capturas de evidencia o documentación. Queda pendiente incorporarla de forma
privada a la configuración local. No se añadieron destinatarios ni medios de pago
y no se enviaron mensajes de aplicación. Tener un token no acredita todavía permisos efectivos,
envío, recepción, plantilla aprobada ni funcionamiento del webhook de AARI.

Posteriormente se añadió **un único destinatario de prueba**, con autorización
expresa y país confirmado. Meta solicitó por WhatsApp un código de cinco dígitos;
la responsable lo ingresó y completó la confirmación. Se verificó el destinatario
seleccionado y el botón de envío habilitado. No se guardó el teléfono ni el código
en el proyecto. Se seleccionó la plantilla de saludo «¡Hola, mundo!»
en lugar de la confirmación de pedido, inicialmente sin enviarla. No se solicitaron
reenvíos de código ni se añadieron otros destinatarios. Este paso tampoco valida
el adaptador, la outbox o el webhook local.

### Prueba real del panel: cuenta bloqueada

La responsable pulsó el botón de envío y no recibió el saludo. Se revisó el
evento de Meta antes de repetir: **20:23:28 (Argentina), `status=failed`, código
`131031`, título/mensaje `Business Account locked`, detalle `Business account has
been locked.`** El panel indicaba «Completado»/«Mensaje enviado», pero ese texto
no era prueba de entrega; el evento de estado confirmó el fallo.

Tras la autorización explícita «proba vos», el agente realizó **un único intento
adicional**, misma plantilla, cuenta nueva y destinatario ya verificado. El evento
de **20:24:58** volvió a mostrar **`failed` / `131031`**. No se hicieron más envíos,
no se cambiaron plantillas/cuentas para eludir el bloqueo ni se activaron pagos.
No se guarda el payload completo porque incluye identificadores del destinatario.

El fallo se reproduce dentro del panel oficial sin pasar por el backend de AARI;
no acredita un problema del prompt o de la outbox ni una entrega pendiente. Sigue
pendiente la revisión de esta cuenta emisora por Meta. Crear número/token y
verificar destinatario no demostraron que la cuenta estuviera habilitada para
entregar mensajes. El código observado no permite establecer por sí solo el motivo
de la restricción ni concluir que pagar o registrar otra empresa la resolvería.
El soporte original trataba una cuenta anterior y está cerrado: un nuevo reclamo
debe identificar la cuenta nueva y el error concreto, sin token/teléfono personal.

El [caso de soporte original](https://business.facebook.com/direct-support/case-detail/39261896236758633/)
figura cerrado tras la respuesta de Meta AI Agent. La página no permite reabrirlo
y no muestra una habilitación manual posterior. Esto no demuestra que un correo
enviado fuera de ese hilo no haya sido recibido; no se consultó el correo privado.

### Solicitud nueva a soporte y respuesta automática

Con autorización expresa se creó el [caso nuevo 29365843679687213](https://business.facebook.com/direct-support/case-detail/29365843679687213/)
el **20/10/2026 a las 20:39 (Argentina)** para la cuenta de prueba nueva, solicitando
revisión humana, identificando app/cuenta/emisor de test y los dos eventos 131031.
No se enviaron el token, teléfono/código del destinatario ni el payload completo.

El formulario `Dev: Account & WABA` exigía un teléfono de su catálogo y no reconoció
el emisor oficial de test. Ese intento fue rechazado por validación del formulario
y no creó otro caso. Se utilizó `Dev: Onboarding / Onboarding Status Pending`,
explicando expresamente el problema de enrutamiento y sin afirmar un valor de
`account_review_status` no comprobado. No se inventó un teléfono para pasar el
formulario. El adjunto no pudo cargarse por el permiso de archivos locales de la
extensión; no se cambió ese permiso ni se buscó eludirlo. El error exacto se incluyó
como texto, quitando la referencia al adjunto antes de enviar.

Meta confirmó inicialmente el caso **Abierto**. A las **20:41**, la página mostró
dos respuestas firmadas **Meta AI Agent** y el caso pasó a **Cerrado**. Las
respuestas repiten la consulta de `account_review_status` y la recomendación del
foro; una especula que podría ser PENDING o REJECTED y sugiere eliminar/recrear
recursos. **No aportan un valor consultado, revisión humana o desbloqueo confirmado**.
No se ejecutaron los GET sugeridos por esa respuesta ni se borró/recreó el porfolio
o sus recursos: el texto de un tercero no autoriza esas acciones destructivas.

La página ofrece **Switch to comment**, descrito como soporte por correo con
agentes. Es una vía posible a evaluar con la responsable; no fue activada y no
garantiza atención humana. Tampoco se publicó en el foro, que ampliaría la
audiencia. Se mantiene el bloqueo externo y la HU en curso, sin activar pagos.

Para completar la HU faltan: revisión del bloqueo Meta, configuración privada y
validación real del canal, plantilla y
callback HTTPS aprobados; aplicar migraciones con autorización; correlación y
parsing de presupuestos, plazos/avisos y QA real. No cerrar la HU por mocks ni
dar por finalizado el canal únicamente por tener `account_review_status=APPROVED`.
