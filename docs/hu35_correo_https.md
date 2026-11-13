# HU35 / AARI-364 — Correo HTTPS con Gmail API

## Alcance aprobado — 10/11/2026

Adaptar el correo para no depender de puertos SMTP salientes en un futuro
alojamiento gratuito. Tras la prueba de viabilidad, Talía aprobó continuar la
integración manteniendo temporalmente la renovación manual del permiso de
prueba. Los emisores de bienvenida (incluidos operadores), invitación de
proveedor y notificaciones ahora usan un transporte común seleccionable.
`EMAIL_PROVIDER=gmail_api` usa HTTPS; `smtp` conserva la configuración previa
y es el valor predeterminado para no activar envíos nuevos al hacer pull.
Rama: `codex/AARI-364-correo-https`, desde `main` `f851450`.

Restricciones: sin tarjeta, facturación, consultas a la bandeja, datos reales de
reclamos, adjuntos, Supabase ni Gemini. La primera prueba se dirigió a la cuenta
remitente de AARI. Después Talía autorizó un único correo ficticio adicional a
una dirección de prueba indicada por ella, usando el emisor final. Esa dirección
personal y las credenciales no se incorporan al repositorio.
El 12/11 Talía autorizó una única invitación real adicional para validar el flujo
HTTP integrado, utilizando una base local descartable y una dirección de prueba
indicada por ella. No se utilizaron cuentas existentes ni Supabase.

## Decisión y alternativas

Se prueba Gmail API porque utiliza HTTPS y permite reutilizar la cuenta del
proyecto sin comprar un dominio para esta prueba de desarrollo. Esto no acredita
que la configuración de producción admita una dirección gratuita sin otros
requisitos de identidad/verificación. SMTP continúa como implementación existente,
pero sus puertos pueden estar bloqueados por el alojamiento. Otros servicios
transaccionales añaden condiciones de dominio, identidad o límites gratuitos;
no se adoptaron como sustitutos sin comprobarlos.

El transporte HTTPS elimina **la dependencia del puerto SMTP**, no demuestra
por sí mismo que toda AARI pueda desplegarse: memoria, OCR, tareas de fondo,
almacenamiento, cookies y secretos siguen dentro del despliegue AARI-338.

## Configuración y seguridad

- Gmail API habilitada en el proyecto de Google de AARI, sin activar pagos.
- Cliente OAuth propio, tipo web, sin orígenes JavaScript. Redirección local
  exacta `http://localhost:8765/`, sólo para aprovisionar la credencial.
- Único permiso: `https://www.googleapis.com/auth/gmail.send`, clasificado por
  Google como sensible. No se solicitan lectura, borrado, perfil ni acceso total.
- El cliente no se conecta con un servicio MCP ni se entrega al frontend.
- Autorización mediante la biblioteca oficial, con `state` y PKCE; el receptor
  temporal escucha sólo en localhost y se cierra al terminar o tras 10 minutos.
- Archivos privados en `backend/.secrets/`, excluidos de Git. La autorización se
  crea exclusivamente: no se sobrescribe una credencial existente. No se guarda
  el token de acceso; la comprobación solicita uno nuevo mediante HTTPS.
- Los mensajes de error no muestran cuerpos remotos, tokens, códigos ni secretos.
- La prueba no sigue redirecciones HTTP, no reintenta envíos ni cambia a SMTP.
  Si la respuesta de envío se pierde, se informa incertidumbre: no hay garantía
  de entrega exactamente una vez por una llamada HTTP.
- Un resultado `accepted_for_delivery` significa aceptación por Gmail, no prueba
  de recepción en la bandeja. No se usa lectura de correo para comprobarlo.

### Límite temporal aceptado y preparación del entorno definitivo

La consola está en **Prueba**, con una única cuenta de prueba de AARI. Para
permisos como `gmail.send`, Google documenta vencimiento de refresh tokens a los
siete días en ese estado. No es una configuración estable para un servicio
desatendido. Se puede volver a autorizar manualmente para desarrollo/pruebas;
el equipo eligió continuar con ese mecanismo temporal sin esperar un dominio.
No se exige resolver el dominio para seguir implementando HU35. Para un
funcionamiento definitivo, publicar/cambiar la configuración OAuth y comprobar los requisitos
de verificación requieren una decisión y validación separadas; no se activaron
automáticamente ni se eludió el aviso de app no verificada.

El correo conserva los límites de Gmail y la autorización puede revocarse.
No se garantiza una cuota gratuita perpetua, reputación ni entrega. Los topes
de usuarios que autorizan OAuth no son topes de destinatarios de las alertas:
en este diseño sólo la cuenta remitente autoriza a AARI.

### Intento de paso a producción — 10/11/2026

Talía autorizó intentar el cambio. La consola mantiene deshabilitado
**Publicar app**, indicando que debe completarse la información de marca.
Se revisó la página correspondiente: nombre, asistencia y contacto de AARI están
cargados, pero no hay página principal, enlaces de privacidad/condiciones ni
dominios autorizados. No se alteraron esos campos ni el estado de publicación.

La documentación oficial de Google para producción/verificación exige una
página que identifique la aplicación, política de privacidad y acreditación de
los dominios utilizados. No se añadieron sitios ajenos, datos inventados ni
declaraciones de verificación no realizadas. No se activó facturación ni se
amplió `gmail.send`; la credencial de prueba se conserva sin reemplazarla.

GitHub Pages permite alojar gratuitamente un sitio estático en un repositorio
público; podría usarse para preparar la información pública de AARI. Esto **no
prueba que Google acepte el dominio gratuito para verificar OAuth**. Preparar y
publicar ese sitio/políticas, y comprobar la aceptación de la dirección, son
pasos pendientes de acordar; no se creó un sitio ni se compró un dominio.
La prueba de correo sigue siendo satisfactoria, pero la preparación para
producción continúa pendiente. No se generó otra autorización ni otro envío.

## Integración realizada

- `app/services/email_transport.py`: HTTPS con validación TLS predeterminada,
  destinos fijos de Google, sin redirecciones ni proxies heredados del entorno.
  Un único POST de envío por intento; nunca fallback automático a SMTP.
- Configuración sólo backend, por un archivo privado o tres secretos del
  alojamiento, no ambos a la vez. Remitente configurable y destinatario único;
  se rechaza inyección de cabeceras y mensajes excesivos.
- MIME común con fecha UTC explícita (`Date`) y `Message-ID` con UUID aleatorio
  y dominio del remitente. No incorpora el nombre del equipo, el usuario local,
  el destinatario ni el token de activación en el identificador. Este campo no
  reemplaza la idempotencia de la outbox ni garantiza deduplicación por Gmail.
- Token de acceso sólo en memoria, con margen de renovación. Las rutas/hilos del
  mismo proceso comparten la renovación bajo un bloqueo; una credencial renovada
  cambia la instancia utilizada. No se instala otro SDK en producción: se usa
  `httpx` ya declarado. La biblioteca del consentimiento es opcional y separada.
- Adaptadores `ConfiguredWelcomeEmailSender`, `ConfiguredProviderInvitationSender`
  y `ConfiguredClaimEmailSender`: mantienen las plantillas, enlaces y estados de
  acceso existentes. Los nombres `Smtp*` quedan como alias de compatibilidad para
  imports y dobles anteriores, no como una selección forzada de canal.
- Outbox: mantiene reservas, número real de intentos, clave de idempotencia y
  revalidación de vigencia/permisos justo antes del envío. `retryable=False`
  termina el aviso como `fallido`, sin falsear la cantidad de intentos ni borrar
  el historial. No hay nuevos estados ni migraciones de base de datos.
- `.gitignore` y `backend/.dockerignore`: excluyen `.secrets/`, archivos `.env` y
  entornos locales para no incluir credenciales en Git ni en la imagen Docker.
- No se activaron workers ni se modificaron datos compartidos. El despliegue
  completo y los enlaces del entorno publicado continúan en AARI-338.

### Política de fallas

| Situación | Resultado |
| --- | --- |
| Permiso vencido/revocado (`invalid_grant`) | `fallido`, mensaje seguro que pide reautorizar, sin reintento automático. |
| Configuración inválida, permiso insuficiente o destinatario rechazado | `fallido`, sin fallback SMTP. |
| Error de renovación recuperable, conexión no establecida, 429 o rechazo 403 de límite temporal conocido | Reintento existente: hasta tres intentos en total, separados por un minuto. |
| Timeout/rotura de comunicación después del POST, respuesta 5xx de envío o éxito sin ID confirmable | `fallido` con advertencia de envío incierto; revisar antes de reenviar. |
| Aceptación con ID de Gmail | Se registra aceptación del canal. No acredita recepción por sí sola. |

En la alternativa SMTP, un retorno exitoso de `send_message` fija la aceptación:
un error posterior de `QUIT` o de cierre no la convierte en fallo. Los rechazos
explícitos SMTP 4xx admiten reintento acotado; los 5xx y configuraciones no
soportadas no. Una pérdida de conexión/respuesta durante el envío es incierta,
no reintentable automáticamente. El cierre se ejecuta aparte y no reemplaza el
resultado original ni guarda respuestas privadas del servidor.

Para `expensa_reporte`, se conserva un resultado no reintentable aunque la
reserva haya vencido si la fila sigue `procesando` con el mismo número de
intento. Las filas ya canceladas/finalizadas y los intentos reemplazados siguen
protegidos. La escritura de éxito y su transición de negocio conservan la
comprobación de reserva vigente anterior; no se amplió esa excepción.

La renovación del permiso permite nuevos envíos, **no reenvía automáticamente
avisos que ya están fallidos**. Los de resultado incierto requieren revisión;
no hay botón nuevo de reenvío masivo. Bienvenidas e invitaciones conservan sus
acciones manuales previas. Las reservas reducen duplicados, pero una caída del
proceso entre la aceptación remota y su registro sigue siendo un límite de la
outbox existente; no se promete entrega exactamente una vez.

## Configuración de AARI (backend)

En `backend/.env` local, usar la cuenta que efectivamente autorizó Google:

```env
EMAIL_PROVIDER=gmail_api
EMAIL_FROM=AARI <cuenta-del-proyecto@example.com>
GMAIL_CREDENTIALS_FILE=.secrets/gmail-authorized-user.json
APP_LOGIN_URL=http://localhost:5173/login
```

La ruta del archivo es relativa al directorio de ejecución: este ejemplo supone
que `uvicorn` se ejecuta desde `backend/`. Los tres campos `GMAIL_CLIENT_ID`,
`GMAIL_CLIENT_SECRET` y `GMAIL_REFRESH_TOKEN` deben quedar vacíos si se usa archivo.
Reiniciar el backend al cambiar `.env`. No copiar secretos en variables `VITE_*`.

Para un alojamiento con secretos por variable, dejar vacío `GMAIL_CREDENTIALS_FILE`
y completar esos tres valores en su gestor de secretos, además de `EMAIL_PROVIDER`
y `EMAIL_FROM`. Nunca incluirlos en Git/Dockerfile. Usar `APP_LOGIN_URL` del frontend
real con HTTPS: los enlaces se generan con esa configuración. No usar localhost
en correos destinados a otra computadora. Habilitar el worker existente sólo
después de la aceptación del entorno; esta entrega no cambia esa habilitación.

### Renovar manualmente sin borrar la autorización anterior

Repetir el consentimiento con un **archivo de salida nuevo**, por ejemplo:

```powershell
.venv-gmail/Scripts/python.exe -u backend/scripts/authorize_gmail_api.py `
  --client backend/.secrets/gmail-client.json `
  --output backend/.secrets/gmail-authorized-user-AAAAMMDD.json
```

Reemplazar `AAAAMMDD` por la fecha de renovación. El script se niega a sobrescribir
un archivo existente. Tras autorizar únicamente envío, apuntar
`GMAIL_CREDENTIALS_FILE` al nuevo archivo y reiniciar el backend; en la nube,
actualizar el secreto correspondiente y reiniciar/republicar el servicio según
su plataforma. No es necesario autorizar cada destinatario ni dejar abierto
el servidor local del consentimiento. Mientras siga en modo Prueba, prever la
intervención semanal; no se cobra por el mero vencimiento del permiso.

### Reversión controlada

Para volver a un entorno que **sí permita SMTP**, configurar
`EMAIL_PROVIDER=smtp`, dejar `EMAIL_FROM` vacío si se usa `SMTP_FROM` y conservar
los parámetros SMTP previos; reiniciar el backend. Cambiar de canal no borra
avisos ni los reenvía por sí solo. No es una solución para un hosting que bloquee
SMTP y no debe usarse como fallback automático ante un envío incierto de Gmail.

## Reproducir sin tocar producción

Desde la raíz del repositorio, crear un entorno separado e instalar
`backend/requirements-gmail-probe.txt` (no reemplaza `backend/requirements.txt`).
No copiar `.env` con secretos de otros servicios. Los scripts no importan la app,
no cargan dotenv ni ponen en marcha sus procesos automáticos.

```powershell
python -m venv .venv-gmail
.venv-gmail/Scripts/python.exe -m pip install -r backend/requirements-gmail-probe.txt
.venv-gmail/Scripts/python.exe -m pytest --noconftest -q backend/tests/test_gmail_api_probe.py
.venv-gmail/Scripts/python.exe -m pip check
```

Descargar el JSON del cliente desde Google y guardarlo privadamente como
`backend/.secrets/gmail-client.json`. No pegar claves en el chat ni añadirlas al
repositorio. El archivo original descargado también contiene un secreto.

```powershell
.venv-gmail/Scripts/python.exe -u backend/scripts/authorize_gmail_api.py `
  --client backend/.secrets/gmail-client.json `
  --output backend/.secrets/gmail-authorized-user.json
```

Abrir el enlace que muestra el script en el perfil de AARI. La persona responsable
debe revisar el aviso de app de prueba y comprobar que sólo se pide enviar correo.
No es necesario dejar ese servidor local funcionando después de autorizar.

Para comprobar únicamente renovación, configurar `AARI_GMAIL_PROBE_SENDER` en el
entorno local con la cuenta que se autorizó (ejemplo ficticio abajo):

```powershell
$env:AARI_GMAIL_PROBE_SENDER = 'cuenta-del-proyecto@example.com'
.venv-gmail/Scripts/python.exe backend/scripts/check_gmail_api.py `
  --credentials backend/.secrets/gmail-authorized-user.json
```

**Sólo con autorización explícita para un envío real**, agregar `--send-to-self`
al último comando. El destinatario siempre es el mismo remitente configurado;
no hay argumento para enviar la prueba a una tercera persona. No ejecutar
repetidamente ante una respuesta incierta.

## Evidencia de la prueba inicial (antes de integrar)

- Entorno aislado, sin cambiar el entorno Python habitual ni el pin histórico
  de `google-genai`.
- **32 pruebas automatizadas aprobadas**: configuración, permisos, PKCE,
  configuración del receptor local, rechazo
  de credenciales ampliadas, renovación, MIME a sí mismo, errores HTTP,
  respuestas malformadas, redirecciones y timeout sin reenvío.
- `pip check`: sin dependencias incompatibles.
- Autorización real completada por la persona responsable en el navegador.
  Credencial renovable guardada localmente con permiso exclusivo `gmail.send`;
  sin token de acceso persistido y sin valores reales en el repositorio.
- Prueba real del 10/11/2026: renovación por HTTPS aprobada y **un único correo
  ficticio dirigido a la propia cuenta remitente**, con resultado
  `accepted_for_delivery`. La persona responsable aportó una captura del correo
  recibido, confirmando recepción. El agente no consultó la bandeja. Sin
  reintentos, destinatarios externos ni fallback SMTP.
- Compilación de los dos scripts y su prueba, exclusión de archivos privados
  de Git y `git diff --check`: correctos.
- En esa fase no se ejecutó la suite integral de AARI ni se cambió su código de
  producción. No se aplicaron migraciones ni se consumió cuota de Gemini.

## Validación de la integración — 10/11/2026

- Pruebas focalizadas del transporte, adaptadores y herramienta de autorización:
  **95 aprobadas**, sin red ni correo real.
- Suite backend completa, desde un entorno Windows nuevo instalado con
  `backend/requirements.txt`: **1352 aprobadas y 648 omitidas**, sin fallos.
  Las omitidas incluyen recorridos PostgreSQL y servicios externos optativos;
  no se presentan como validados en esa tanda. Permanecen 18 avisos deprecados
  del adaptador datetime de SQLite, ajenos al cambio de transporte.
- PostgreSQL local descartable, con datos ficticios: notificaciones HU35,
  expensas, portal de presupuestos e invitaciones. Se verifican cancelación de
  avisos obsoletos, reintentos persistidos y resultados tardíos: **117 aprobadas
  con psycopg2**, repetidas tras corregir el fixture.
- Con psycopg 3 se detectó un defecto del fixture compartido: el seed se ejecutaba
  con cursor DBAPI y la confirmación de SQLAlchemy no siempre confirmaba esa
  transacción. Se corrigió el commit del fixture, sin cambiar SQL de producción.
  Regresión de HU35 y expensas con psycopg 3: **18 aprobadas**.
- Prueba real adicional expresamente autorizada: el emisor final
  `ConfiguredClaimEmailSender` renovó el permiso y Gmail aceptó un solo mensaje
  ficticio a la dirección de prueba indicada por Talía. Sin base de datos,
  contraseñas, adjuntos ni datos de reclamos. Talía confirmó mediante captura que
  **se recibió en Spam**, no en Recibidos. La aceptación del canal está validada,
  pero la llegada a Recibidos no queda aprobada.
- `pip check`, compilación, exclusión de los secretos y revisión de formato:
  correctos. No se alteró `backend/requirements.txt` ni la evidencia congelada
  de Gemini. No se consumió Gemini ni se modificó Supabase.
- No sumar las tandas focalizadas como si fueran casos independientes del total.
- La prueba inicial autoriza la conexión; no acredita el entorno remoto todavía.

Comandos de validación, desde `backend/`, con dotenv deshabilitado y servicios
externos apagados. La suite general usa una base SQLite ficticia; las dos tandas
PostgreSQL fijan `AARI_TEST_POSTGRES_URL` exclusivamente a una instancia local
descartable con el controlador correspondiente, nunca a Supabase:

```text
../.venv/Scripts/python.exe -m pytest -q --durations=5 -o faulthandler_timeout=60
../.venv/Scripts/python.exe -m pytest -q tests/test_email_transport.py tests/test_email_adapters.py tests/test_gmail_api_probe.py
../.venv/Scripts/python.exe -m pytest -q tests/test_email_delivery_postgres.py tests/test_expensas_postgres.py tests/test_quote_portal_postgres.py tests/test_provider_access_postgres.py
../.venv/Scripts/python.exe -m pytest -q tests/test_email_delivery_postgres.py tests/test_expensas_postgres.py
../.venv/Scripts/python.exe -m pip check
```

En Windows, las pruebas HTTP locales de `TestClient` requirieron ejecución fuera
del entorno restringido: sin ello, la suite se detenía al abrir el cliente
simulado. Las dos ejecuciones interrumpidas por esa condición no se cuentan como
aprobadas. La tanda completa informada arriba es la repetición final exitosa.

## Estado de entrega

Entrega inicial publicada en el [PR #47](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/47),
commit `0720ff9`, para revisión cruzada. Las correcciones del 13/11 descritas al
final de esta guía están validadas; Talía autorizó su commit y publicación en
el mismo PR el 13/11. Queda pendiente la nueva revisión cruzada. No se fusiona
ni se cierra la HU en esta entrega. Sin cambios
visuales ni migraciones nuevas. Se conserva la renovación manual como limitación
temporal aceptada; producción OAuth y despliegue remoto siguen pendientes. No se
cierra HU35 en Jira antes de la revisión/merge ni se presenta AARI-338 como hecha.

### Observación de entregabilidad — 10/11/2026

La captura del segundo correo muestra la carpeta Spam y un aviso de Gmail de
similitud con mensajes identificados como spam. No permite atribuir la causa
al contenido, reputación del remitente, autenticación o modo OAuth. No se
presenta la prueba como recepción satisfactoria en la bandeja principal.

Se debe revisar el resumen de autenticación SPF/DKIM/DMARC en «Mostrar original»
del mensaje recibido, sin pedir acceso de lectura a Gmail API ni copiar los
encabezados completos al repositorio. La construcción local del MIME no agrega
explícitamente `Date` ni `Message-ID`; hay una mejora de formato a evaluar, pero
Google puede agregarlos al procesar el correo y no se afirma que eso haya
causado Spam. No se cambió código ni se envió otro correo por este hallazgo.

Marcar el mensaje conocido como «No es spam» o añadir el remitente a contactos
es una acción de la persona destinataria para su buzón; no demuestra que el
problema esté resuelto para otros proveedores. La carpeta elegida por el filtro
no se conoce con el permiso `gmail.send`, por lo que el estado de aceptación
del canal no se convierte artificialmente en una confirmación de Recibidos.

## Diagnóstico y validación adicional — 12/11/2026

Talía aportó el original del correo que llegó a Spam. Su resumen muestra
**SPF PASS, DKIM PASS y DMARC PASS**, además de transporte seguro entre los
servidores de Google. Por lo tanto, esa muestra no evidencia un fallo de
autenticación del remitente. Google ya había incorporado `Date` y `Message-ID`;
su ausencia en la construcción local no se presenta como causa del Spam.
No se copiaron encabezados completos, firmas, direcciones ni otros datos
personales al repositorio y no se amplió el permiso de Gmail para leer correo.

Se incorporaron fecha e identificador explícitos como mejora del formato
RFC 5322, válida tanto para Gmail API como para la compatibilidad SMTP.
No se cambió el asunto ni el contenido de las plantillas para intentar engañar
al filtro. La evidencia disponible no distingue entre reputación del remitente,
contenido y otras señales internas de Gmail. Las acciones «No es spam» o agregar
el contacto quedan en manos de la persona destinataria y no son una validación
general de entrega a proveedores.

- Transporte, adaptadores y autorización: **97 aprobadas**, sin red.
- Backend completo: **1354 aprobadas y 652 omitidas**, sin fallos; los mismos
  18 avisos deprecados de SQLite. Las omitidas incluyen las cuatro regresiones
  nuevas de invitación PostgreSQL, que se ejecutan aparte con una base local.
- Se agregaron regresiones HTTP con los servicios y la persistencia reales de
  invitaciones: permiso administrador, MIME por Gmail simulado, replay sin
  reenvío, hash del token, activación de un solo uso, login/perfil y registro
  seguro de rechazo o envío incierto. No usan correos reales ni Supabase.
- PostgreSQL local 17, creado sólo para esta validación: **121 aprobadas con
  psycopg2**, incluyendo invitaciones, outbox, expensas y portal de presupuestos.
  Regresiones HU35/invitaciones/expensas con psycopg 3: **22 aprobadas**. No sumar
  estas repeticiones ni las pruebas focalizadas como casos distintos del total.
- Ensayo real separado, autorizado expresamente: una sola invitación de
  proveedor por el endpoint administrativo real, con autenticación, servicio y
  repositorio reales contra PostgreSQL local. El transporte final renovó el
  permiso de Google y Gmail aceptó **un único envío**. No se sustituyó el
  transporte por un doble en ese ensayo ni se recurrió a SMTP.
- Activación por HTTP usando el token emitido, rechazo de su reutilización,
  login del proveedor y lectura de su perfil: aprobados. No fue una prueba
  visual del navegador; no se afirma haber validado una interfaz nueva.
  El enlace apuntaba al acceso local y quedó consumido durante la prueba.
- Talía confirmó que la invitación **llegó a Recibidos**. Es evidencia de esa
  muestra, no garantía general ni demostración causal de que los nuevos
  encabezados solucionaron el Spam del correo genérico anterior.
- Se retiraron la base, el contenedor y su volumen descartables al terminar;
  no queda una cuenta de prueba persistente en el entorno compartido.
  `pip check`, compilación y exclusión de secretos: correctos.

Comandos adicionales, desde `backend/`, con las mismas guardas de entorno y
una URL PostgreSQL exclusivamente local. Todos los transportes HTTP/SMTP de
estas pruebas automatizadas son dobles; el ensayo real anterior fue independiente
y no queda habilitado por ejecutar pytest:

```text
../.venv/Scripts/python.exe -m pytest -q tests/test_email_delivery_postgres.py tests/test_email_invitations_postgres.py tests/test_expensas_postgres.py tests/test_quote_portal_postgres.py tests/test_provider_access_postgres.py
../.venv/Scripts/python.exe -m pytest -q tests/test_email_delivery_postgres.py tests/test_email_invitations_postgres.py tests/test_expensas_postgres.py
```

La validación funcional de HU35 queda preparada para revisión. Commit, push y
PR autorizados por Talía el 12/11; quedan pendientes revisión cruzada y merge.
No se marca la HU como finalizada antes de ello. La renovación manual de OAuth continúa
como limitación temporal aceptada y el despliegue en la nube sigue en AARI-338.

## Correcciones de la revisión del PR #47 — 13/11/2026

Talía aprobó corregir los dos hallazgos de Tobías sobre `0720ff9`:
[cierre SMTP](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/47#discussion_r4563334695)
y [resultado terminal tardío de expensas](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/47#discussion_r4563334713).

### Cambios y alcance

- `email_transport.py`: la conexión SMTP se prepara/envía y se cierra en fases
  separadas. `QUIT`/`close` no transforman una aceptación en un error ni tapan
  el rechazo o la incertidumbre original. Se conserva el mensaje seguro y se
  distingue rechazo temporal, permanente, fallo previo al envío y respuesta
  perdida durante el envío. No se reenvía dentro del transporte.
- `db/reclamos.py`: el UPDATE admite el fallo no reintentable del intento aún
  actual después del vencimiento. Conserva las condiciones de estado y número
  de intento, el orden de locks y la protección de los éxitos de expensas.
  No se quita globalmente la comprobación de reserva ni se avanza el reclamo
  al guardar un error.
- Se agregaron regresiones de transporte y persistencia; el doble SMTP de la
  prueba HU32 se adaptó al cierre explícito. Sin dependencias nuevas, frontend,
  migraciones, cambios de permisos ni configuración real.

### Evidencia de reproducción y validación

- Antes de corregir, los dobles reprodujeron aceptación seguida de `QUIT 421`
  y pérdida de respuesta durante SMTP como errores recuperables incorrectos.
- Antes de cambiar la condición SQL, las dos nuevas regresiones PostgreSQL
  (autorización rechazada y envío Gmail incierto después de vencer la reserva)
  fallaron porque el aviso quedaba `procesando`, en vez de `fallido`. Esas
  ejecuciones intencionalmente rojas no se cuentan como validación aprobada.
- Tanda final de correo/adaptadores/autorización/compatibilidad HU32:
  **138 aprobadas**, sin red. Incluye cierre fallido tras aceptación, cierre
  que no tapa el error de envío, rechazos explícitos y fallos previos al envío.
- Backend completo: **1373 aprobadas / 660 omitidas**, sin fallos; los mismos
  18 avisos preexistentes del adaptador datetime de SQLite. Los casos locales y
  externos optativos omitidos aquí no se presentan como aprobados en esa tanda.
- PostgreSQL 17 local descartable: **129 aprobadas con psycopg2** en outbox,
  invitaciones, expensas y portal; **30 aprobadas con psycopg 3** en
  outbox/invitaciones/expensas. Tandas solapadas: no sumar al total general.
- La prueba de concurrencia vence la reserva mientras el resultado espera
  el lock del reclamo. El fallo terminal se conserva si el intento sigue
  siendo el mismo; se rechaza si otro worker ya adquirió un intento nuevo.
  También se comprueba que no sobrescriba filas canceladas/finalizadas, que no
  haya otro envío en el siguiente ciclo y que el éxito tardío de expensas siga
  protegido por las regresiones anteriores.
- Gmail se simuló con `httpx.MockTransport` y reloj controlado; SMTP con dobles.
  No se enviaron correos reales, no se consultó Gmail ni se consumió Gemini,
  no se modificó Supabase/OAuth y no se usaron sus credenciales. La base,
  contenedor y volumen de pruebas fueron retirados.
- `pip check`, compilación y `git diff --check`: correctos. Tras la validación,
  Talía autorizó commit/push y comentario de contexto el 13/11. Los hilos de
  revisión quedan pendientes de confirmación por Tobías; no se resuelven ni se
  fusiona el PR en nombre del revisor.

Comandos, desde `backend/`, con dotenv y servicios externos deshabilitados:

```text
../.venv/Scripts/python.exe -m pytest -q tests/test_email_transport.py tests/test_email_adapters.py tests/test_gmail_api_probe.py tests/test_provider_access.py
../.venv/Scripts/python.exe -m pytest -q --durations=5 -o faulthandler_timeout=60
../.venv/Scripts/python.exe -m pytest -q tests/test_email_delivery_postgres.py tests/test_email_invitations_postgres.py tests/test_expensas_postgres.py tests/test_quote_portal_postgres.py tests/test_provider_access_postgres.py
../.venv/Scripts/python.exe -m pytest -q tests/test_email_delivery_postgres.py tests/test_email_invitations_postgres.py tests/test_expensas_postgres.py
```

Las dos últimas tandas requieren `AARI_TEST_POSTGRES_URL` exclusivamente local;
se ejecutan con psycopg2 y psycopg respectivamente. No hay envíos reales al
ejecutar pytest. Se mantiene el límite general de la outbox: no se garantiza
entrega exactamente una vez ante cualquier caída o reserva ya reclamada por
otro proceso; estas correcciones cierran los dos caminos reproducidos sin
eliminar las protecciones de concurrencia.

## Fuentes oficiales consultadas

- [Envío mediante Gmail API](https://developers.google.com/workspace/gmail/api/guides/sending).
- [Permisos y clasificación de Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes).
- [Duración/revocación de autorizaciones OAuth](https://developers.google.com/identity/protocols/oauth2#expiration).
- [Cuotas de Gmail API](https://developers.google.com/workspace/gmail/api/reference/quota).
- [Preparación/verificación de una app OAuth](https://support.google.com/cloud/answer/13464323).
- [Información de marca y dominios en OAuth](https://support.google.com/cloud/answer/15549049?hl=en).
- [Políticas de OAuth para producción](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance).
- [Alojamiento de sitios con GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).
- [Biblioteca oficial de autorización](https://pypi.org/project/google-auth-oauthlib/).
- [Correos válidos en Spam y acciones de la persona destinataria](https://support.google.com/mail/answer/1366858?hl=es).
- [Autenticación de mensajes recibidos](https://support.google.com/mail/answer/180707).
- [Directrices de Gmail para remitentes](https://support.google.com/mail/answer/81126?hl=es).
- [Formato de mensajes RFC 5322](https://www.rfc-editor.org/rfc/rfc5322).
- [Utilidades de correo de Python](https://docs.python.org/3/library/email.utils.html).
