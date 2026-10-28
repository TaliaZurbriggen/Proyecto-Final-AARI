# HU19 / AARI-206 — base de transporte WhatsApp

> Continuación del 25/10: [recepción de presupuestos y plazos](hu19_respuestas_presupuesto.md).

> Continuación actual: [solicitudes de presupuesto](hu19_solicitudes_presupuesto.md),
> rama `codex/AARI-206-solicitudes-presupuesto` desde main `19d06fa`.
> La sección siguiente conserva la evidencia de la primera etapa del 19/10;
> su actualización pendiente de main ya quedó resuelta en la copia de continuación.

## Estado y alcance aprobado — 19/10/2026

En curso. Rama `codex/AARI-206-whatsapp-base`, creada desde `origin/main`
`02479b9e8cd770e0f87855f88fcbb39572782327`. No se hicieron commits ni push.
Durante el trabajo main avanzó a `19d06fa7eb9fe543fe960eff58cc852981e02a23`;
antes del futuro PR habrá que integrar ese avance y repetir las regresiones.
No se incorporaron silenciosamente ramas de otras historias.

Esta etapa prepara el transporte; **no completa HU19** ni habilita una
coordinación real por WhatsApp. No se enviaron mensajes reales, no se registraron
destinatarios en Meta, no se creó un túnel público y no se activó facturación.
No se aplicó la migración en Supabase. No hubo llamadas a Gemini ni SMTP.

Se inició en Jira la HU y las subtareas AARI-208, AARI-211, AARI-217 y AARI-218,
limitadas a esta etapa. Las otras subtareas no se dieron por implementadas.
No se agregó tiempo nuevo: las 2 HH del trabajo anterior de configuración ya
estaban registradas en AARI-208 y no se duplican.

## Contexto y decisión

La cuenta de prueba de Meta figura con revisión aprobada, pero su diagnóstico
de habilitación sigue bloqueado y no se obtuvo un número utilizable. Una
revisión `APPROVED` no equivale a permiso efectivo de envío. El seguimiento
al soporte fue enviado por la persona responsable; no se duplicó.

Decisión: avanzar con un adaptador oficial y recepción verificable, ambos
apagados, probados con HTTP simulado y PostgreSQL local. Así la restricción
externa no impide comprobar seguridad, persistencia y duplicados. No se
sustituyó WhatsApp por Telegram ni se automatizó WhatsApp Web. Tampoco se
presentó documentación académica como constitución legal de una empresa.

Alternativas consideradas: esperar sin avanzar (mantiene bloqueada toda la
implementación); conectar el worker genérico de notificaciones (reintenta,
por lo que puede repetir un envío de resultado incierto); cambiar de canal
(requiere decisión de producto). Se eligió un transporte separado, sin envío
al arrancar ni reintentos automáticos.

## Qué se implementó

### Configuración y adaptador de envío

- `app/core/whatsapp.py`: configuración desde entorno, secretos ocultos en la
  representación del objeto y validaciones de IDs, versión y destinatarios.
- `app/services/whatsapp_sender.py`: adaptador interno, sin endpoint ni worker
  que lo invoque automáticamente. Envía solamente plantillas ya aprobadas
  por Meta, nunca crea/aprueba plantillas desde la aplicación.
- Host fijo `graph.facebook.com`, HTTPS, Bearer en header, sin tokens en la
  URL, sin redirects/proxies heredados; timeout de 10 s (conexión 5 s).
- Lista explícita de 1 a 5 números de prueba. Esto es una protección local:
  **no inscribe números ni ocupa cupos en Meta**, ni garantiza su habilitación.
- Una sola petición por invocación. Un 2xx con ID significa **aceptado por
  Meta**, no entregado, leído, presupuesto válido ni autorización del reclamo.
- Timeout, fallo de transporte, redirect o 5xx producen resultado desconocido,
  sin reintento automático. Repetir a ciegas podría duplicar mensajes.
  Un 4xx, incluido 429, queda rechazado y requiere revisión.
- No se propagan cuerpos de error de Meta ni excepciones HTTP con credenciales.

### Verificación y recepción

`GET /webhooks/whatsapp` atiende el challenge de Meta. Exige `hub.mode=subscribe`,
el token de verificación propio y un challenge numérico; rechaza parámetros
duplicados y devuelve el challenge exacto como texto, sin envolverlo en JSON.
Puede prepararse sin token OAuth ni número activo. El POST no queda por eso
configurado: necesita su secreto y sus dos IDs.

`POST /webhooks/whatsapp`:

1. Exige habilitación explícita, JSON sin compresión y un único header
   `X-Hub-Signature-256`.
2. Limita el cuerpo a 4 MiB durante la lectura, sin confiar en Content-Length.
3. Verifica HMAC-SHA256 sobre los **bytes originales**, usando el secreto
   de la app y comparación de tiempo constante, antes de interpretar JSON.
4. Rechaza JSON ambiguo o inválido, cuentas/números ajenos, campos inválidos
   y lotes con más de 1.000 eventos. Valida todo antes de guardar.
5. Guarda el lote en una transacción y recién después responde 200. Una
   falla SQL devuelve 503; no se reconoce como guardado algo que se perdió.
6. Los reenvíos del mismo mensaje no crean otra fila ni reemplazan su texto.

Se conserva el texto recibido, su ID, remitente, fecha UTC y `context.id`
para una correlación posterior; no se conserva el perfil/nombre de contacto
ni el payload completo. El número y el texto **son datos personales**:
deben permanecer en la base privada, no en logs, capturas ni repositorio.

Los eventos `sent`, `delivered`, `read`, `failed` y `deleted` se registran
por separado del contenido, incluso si llegan desordenados. No hacen avanzar
un presupuesto ni regresan un estado de negocio. Medios/audio/documentos u
otros tipos se registran como `no_soportado`, sin descargar el archivo y sin
interpretarlo. Los códigos de error de estados se conservan, no sus textos
arbitrarios. No se suscriben ni procesan otros campos de webhook en esta etapa;
notificaciones sistémicas sin `messages`/`statuses` no crean entradas de negocio.

### Persistencia

`app/db/whatsapp.py` utiliza un INSERT de lote, unicidad por cuenta/número/clave
de evento y `ON CONFLICT DO NOTHING`. Ordena el lote por clave para evitar
interbloqueos con reenvíos concurrentes en orden inverso. La confirmación ocurre
al salir de la transacción, no al ejecutar el primer INSERT.

La nueva migración `20261019230000_hu19_whatsapp_base.sql` crea solamente
`public.whatsapp_eventos_entrada`, con índices, CHECK, RLS y revocación de todos
los permisos de PUBLIC/anon/authenticated, sin políticas públicas. No cambia
tablas ni estados de reclamos, presupuestos, proveedores o notificaciones.
Es de ejecución única, no automática al levantar FastAPI, pendiente de
autorización y aplicación en Supabase.

La unicidad resuelve **guardado** duplicado, no procesamiento de negocio
exactamente una vez. Todavía no hay consumidor de esta bandeja, outbox durable
de envíos ni correlación con solicitudes/presupuestos: es la siguiente etapa.

## Configuración local y activación futura

Las variables de ejemplo no contienen credenciales reales:

| Variable | Uso |
| --- | --- |
| `WHATSAPP_WEBHOOK_ENABLED=false` | GET/POST responden 404 por defecto. |
| `WHATSAPP_OUTBOUND_ENABLED=false` | Impide enviar aunque haya credenciales. |
| `WHATSAPP_VERIFY_TOKEN` | Secreto propio aleatorio, ASCII de 16–256 caracteres, para el challenge. |
| `WHATSAPP_APP_SECRET` | Secreto de la app Meta para verificar firmas. |
| `WHATSAPP_ACCESS_TOKEN` | OAuth con permiso de mensajería sobre los activos autorizados. |
| `WHATSAPP_WABA_ID` / `WHATSAPP_PHONE_NUMBER_ID` | Cuenta y número de origen esperados; no son el Business Manager ni el teléfono del proveedor. |
| `WHATSAPP_API_VERSION=v26.0` | Versión configurable; falta validarla contra una cuenta habilitada. |
| `WHATSAPP_TEST_RECIPIENTS` | Lista privada separada por comas, hasta cinco destinatarios de prueba. |

No copiar esos secretos al chat ni usar variables `VITE_*`. Son tres secretos
distintos: verify token, app secret y access token no son intercambiables.

Orden de activación, **no ejecutado**:

1. Resolver la restricción con Meta y obtener un número oficial habilitado.
   No inventar datos legales ni agregar tarjetas como atajo.
2. Autorizar los permisos mínimos de mensajería sobre los activos actuales,
   obtener el token y completar `.env` local. Los permisos actuales de gestión
   por sí solos no demuestran capacidad para enviar.
3. Autorizar y aplicar la migración una vez, comprobando RLS y permisos.
4. Autorizar un callback público HTTPS con TLS válido y límites de tráfico.
   Para el proceso receptor y el proxy **deshabilitar o redactar access logs**:
   la verificación lleva su token en el query string. No publicar logs de
   headers/cuerpo, trazas SQL con parámetros ni URLs firmadas. Probar firmas
   inválidas y límites antes de suscribir. No usar un túnel sin aprobación.
5. Activar recepción y verificar challenge/POST; suscribir la app a la cuenta
   y al campo `messages`. Comprobar la configuración real, no sólo el challenge.
6. Acordar destinatarios de prueba y consentimiento, plantilla aprobada,
   precio/cuota y autorización de una prueba real. No asumir que todo envío
   es gratuito ni que la ventana de atención elimina cualquier costo.
7. Sólo entonces habilitar temporalmente envío, hacer una única prueba y
   verificar recepción/entrega/respuesta persistida. Desactivar al terminar.

La plantilla sirve para iniciar el contacto fuera de la ventana permitida;
no abre por sí sola una ventana de 24 h. Esta etapa no gestiona conversaciones
libres ni interpreta que un mensaje leído sea aceptación de un trabajo.

## Pruebas locales

Prueba focalizada final: **90 aprobadas**, 1 aviso de deprecación preexistente de
Starlette/TestClient, 2,11 s. Incluye 79 pruebas HTTP/configuración/envío con
mocks y 11 pruebas de persistencia en PostgreSQL **18.1 local**. Docker no
completó su inicio; se usó la instalación local existente en un clúster nuevo,
aislado en `127.0.0.1:55419`, sin tocar el clúster de la aplicación.

El fixture sólo permite PostgreSQL en localhost y nombre `test_aari_hu19`, y
exige que la tabla de entrada no exista. La base debe ser nueva/descartable:
no repetir contra una base previa ni apuntar al entorno compartido.
Al finalizar el QA se detiene el servidor temporal. Sus datos ficticios quedan
en `tmp/` ignorado por Git, sin credenciales ni mensajes reales.

Desde `backend/`, con el entorno virtual del proyecto:

```powershell
$env:DATABASE_URL='sqlite:///:memory:'
$env:NOTIFICATION_WORKER_ENABLED='false'
$env:CONTRACT_ANALYSIS_WORKER_ENABLED='false'
$env:PROVIDER_CANDIDATES_WORKER_ENABLED='false'
$env:WHATSAPP_WEBHOOK_ENABLED='false'
$env:WHATSAPP_OUTBOUND_ENABLED='false'
$env:AARI_WHATSAPP_TEST_POSTGRES_URL='postgresql+psycopg2://aari_qa@127.0.0.1:55419/test_aari_hu19'
python -m pytest -q -p no:cacheprovider tests/test_whatsapp_webhook.py tests/test_whatsapp_sender.py tests/test_whatsapp_postgres.py
```

Cobertura: challenge exacto; firma alterada; JSON malformado/ambiguo; IDs ajenos;
feature flags; controles de destinatario; rechazo y timeout sin reintento;
transacciones; persistencia leída por un repositorio nuevo; duplicados en el
mismo lote; 2/8 hilos concurrentes; lotes inversos de 40 eventos; rollback
completo ante una fila inválida; 1.000 eventos con un solo INSERT; RLS y ausencia
de privilegios públicos; retorno 503 ante falla SQL y posterior reenvío durable;
separación de entrega/lectura, mensajes de texto y medios no soportados.

Regresión backend general con `python -m pytest -q -p no:cacheprovider`:
**881 aprobadas, 194 omitidas, 19 avisos preexistentes, 34,69 s**. Las omitidas
incluyen integración externa, OCR opcional y PostgreSQL opcional de otros
módulos; no se presenta esa ejecución como una validación de la base compartida.
Las once PostgreSQL de esta etapa se ejecutaron separadamente, incluidas
en las 90 focalizadas anteriores, no se suman dos veces. `pip check` correcto.

No se modificó frontend. Las pruebas de mocks no habilitan una cuenta Meta,
no verifican entrega real y no son una medición de capacidad de producción.

## Qué falta para completar HU19

- Conectar las solicitudes a proveedores candidatos y a la autorización
  correspondiente, preservando las reglas de HU15/HU16/HU17 y la trazabilidad.
- Persistir la intención y el resultado del envío en una outbox; manejo
  explícito del resultado incierto antes de permitir repetirlo.
- Correlacionar respuesta/proveedor/solicitud, validar e interpretar montos,
  moneda y alcance del presupuesto sin mezclar eventos de entrega.
- Procesamiento recuperable con reserva/idempotencia, plazos, avisos y
  caminos sin presupuesto de las subtareas restantes.
- Acordar retención y acceso administrativo a mensajes; esta etapa no publica
  un visor ni un endpoint de lectura anónima de la bandeja.
- Configuración real, migración autorizada y prueba E2E oficial cuando Meta
  habilite el entorno. No cerrar la HU únicamente por mocks aprobados.

## Referencias oficiales

- [Meta: Webhooks, verificación y firma](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/).
- [WhatsApp: referencia de eventos messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/).
- [WhatsApp: envío de mensajes](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages/).

La configuración de cuenta, versión, permisos, plantillas y precios requiere
una comprobación vigente al habilitar la conexión real.
