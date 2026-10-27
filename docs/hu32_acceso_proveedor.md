# HU32 / AARI-347 — Acceso y espacio de trabajo del proveedor

**26/10/2026. Estado: entrega parcial para revisión; HU y seis subtareas
En curso.** Talía autorizó commit, publicación y creación del PR. No se autoriza
fusionar ni cerrar la HU con esta entrega.
Rama `codex/AARI-347-acceso-proveedor`, creada desde origin/main `19d06fa7`
tras consultar el remoto. La planificación de cambio permanece aparte en
`codex/cambio-canal-proveedores`; el trabajo local HU19 no se copió ni descartó.

Origen: [HU32](https://taliazurbriggen.atlassian.net/browse/AARI-347) y
[SC-2026-10-26](https://taliazurbriggen.atlassian.net/browse/AARI-346).
Propuesta aprobada antes de implementar. Estimación preservada: 6 HH. Talía
autorizó registrar 4 h 30 min de esfuerzo real en las subtareas de Jira tras
publicar el PR, sin alterar la estimación ni duplicar la carga en la HU padre.

## Alcance implementado

- Identidad 1:1 entre proveedor y usuario, rol `proveedor`, correo normalizado
  y único. Sin registro público, multirrol ni traslado de identidades existentes.
- Proveedores legados sin correo/cuenta se conservan. Administración puede
  habilitar acceso sólo si el proveedor está activo.
- Invitación de 24 h por defecto, configurable entre 1 y 168 h. No es el plazo
  de 24 h de HU19. Se persiste SHA-256 de un secreto aleatorio de 256 bits,
  nunca el token original; consumo atómico y bloqueo frente a reenvío/concurrencia.
- El token sólo viaja en el correo, como fragmento del enlace; no se devuelve
  por API al administrador, no se guarda en logs ni almacenamiento del navegador.
  La pantalla quita el fragmento de la URL y lo conserva sólo en memoria.
  Recargarla requiere abrir nuevamente el enlace original.
- Abrir la página no activa ni consume la invitación. El proveedor elige y
  confirma su contraseña; no se mandan contraseñas por correo. Contraseña con
  al menos ocho caracteres/un número y hasta 72 bytes (límite bcrypt existente).
- Login/logout comunes, mismo mecanismo de cookie HttpOnly y control de
  intentos. Se consulta el estado actual del padrón por petición; desactivar
  al proveedor impide también usar una sesión que ya estaba abierta.
- Reenvío confirmado por administración: revoca enlace anterior y reutiliza
  usuario. `request_id` permite repetir una misma petición sin reenviar ni rotar.
- Correo corregible antes de activar; después no se modifica desde esta acción.
  Recuperación general de contraseña olvidada/cambio verificado de correo
  activo no están incluidos en esta HU.
- Fallo SMTP se guarda con mensaje seguro, sin borrar la cuenta. El estado
  `enviado` significa que SMTP aceptó el mensaje, no prueba entrega ni lectura.
  Corte antes de registrar resultado puede dejar `pendiente`: consultar estado
  y generar una nueva invitación. No se prometen correos exactamente una vez.
- Portal responsive y consulta privada del perfil, sin accesos a administración
  ni a otro proveedor. El diseño reutiliza cabecera, tokens y componentes AARI,
  sin navegación lateral ni paleta nueva.

## Separación de responsabilidades y pendiente de integración

| Entrega | Estado |
| --- | --- |
| Modelo, invitación, activación, login y permisos | Implementados y probados localmente |
| Gestión administrativa del acceso | Implementada; consultas reales de Supabase verificadas en navegador |
| Portal propio e indicador de integración pendiente | Implementado; no muestra una bandeja ficticia como vacía |
| Listado/detalle de solicitudes propias | **Pendiente de adaptar e integrar HU19**; AARI-354 no queda terminada |
| Presentación estructurada del presupuesto | HU19, no implementada por HU32 |
| Conversación privada y eventos | HU33, no implementados por HU32 |
| Entrega real SMTP y activación por destinatario | Confirmadas por Talía el 26/10; automatizadas siguen usando doble SMTP |
| Acceso remoto de proveedor externo | Depende del despliegue AARI-338, fuera del Sprint actual |

`GET /proveedor/perfil` informa `solicitudes_disponibles=false`. La interfaz
explica que la recepción de solicitudes aún está en preparación. Esto no
acredita el criterio completo de bandeja de HU32: requiere integración real y
revisión antes de cerrar HU/subtareas.

### Secuencia de integración acordada

1. Revisar este PR de acceso, invitación, activación, permisos y portal inicial.
2. Si Tobías lo aprueba, fusionar esta base en `main` sin cerrar HU32 ni AARI-354.
3. Actualizar la rama existente de HU19 desde ese `main`, conservando su trabajo;
   adaptar el canal a AARI con aviso por correo y conectar las solicitudes reales.
   Este PR no copia, descarta ni publica el trabajo local de HU19.
4. Probar listado/detalle propios, rechazo del acceso a solicitudes ajenas,
   estados y navegación con la integración real. Recién después evaluar el
   cierre de HU32 y su subtarea de bandeja mediante la revisión correspondiente.

Se integra primero una base reutilizable para resolver la dependencia técnica;
un merge parcial no equivale al cumplimiento de todos los criterios de la HU.
La conversación privada se implementa aparte en HU33.

## API y componentes

| Ruta | Permiso / efecto |
| --- | --- |
| `GET /proveedores/{id}/acceso` | Sólo administración; estado sin token |
| `POST /proveedores/{id}/acceso` | Sólo administración; email y request_id; crea/renueva invitación |
| `POST /auth/proveedores/activar` | Token público de un uso + contraseña confirmada; no abre sesión automáticamente |
| `GET /proveedor/perfil` | Proveedor activo; vínculo se verifica en backend |

Respuestas privadas con `Cache-Control: no-store`. Errores 422 de activación
no reflejan contraseña/token de entrada. Conflictos de email se muestran junto
al campo. No hay permisos nuevos por Supabase Data API.

Backend: `api/provider_access.py`, `db/provider_access.py`,
`schemas/provider_access.py`, `services/provider_access_service.py`; ajustes
acotados en autenticación/usuarios y registro de rutas.
Frontend: `ProviderAccessPanel`, `ProviderActivationPage`, `ProviderHomePage`,
API del módulo, rutas por rol y reutilización de `RoleLayout` y componentes UI.

## Migraciones y entorno compartido

1. `20261026180000_hu32_rol_proveedor.sql`: adición del enum; confirmar primero.
2. `20261026180100_hu32_acceso_proveedor.sql`: correo/vínculo opcionales,
   invitaciones privadas, índices, restricciones y validación diferida de identidad.

Aplicadas con autorización expresa al Supabase AARI de desarrollo el 26/10/2026,
con versiones de historial iguales a los prefijos. Verificados RLS, ausencia de
políticas y permisos públicos en invitaciones, triggers y conteos de las 35
tablas anteriores. No se compararon valores fila por fila ni se generó un backup.
No se crearon cuentas/invitaciones de negocio ni se transmitieron mensajes.

La adición del enum requiere transacción separada: si fallara la etapa 2,
puede quedar confirmada la etapa 1. `scripts/apply_provider_access.py` permite
preflight sin escritura y aplicación autorizada de etapas faltantes. No repetir
SQL manualmente por cada integrante/pull. Los workers no se activan por DDL.

## Validaciones y límites de la evidencia

- Regresión backend con PostgreSQL local y reloj/contraseña de prueba:
  `pytest -q -p no:cacheprovider --ignore=tests/test_provider_candidates_volume_postgres.py`
  → **1110 aprobadas, 51 omitidas**, 18 avisos de SQLite preexistentes.
  Benchmark aparte: `pytest -q -p no:cacheprovider
  tests/test_provider_candidates_volume_postgres.py` → **23 aprobadas**.
  Son conjuntos disjuntos: 1133 aprobadas en total, no una única invocación.
- Backend focalizado: 85 aprobadas antes de agregar la regresión de proveedor
  legado inactivo; incluye PostgreSQL local real, API y regresiones de auth/CRUD.
- Repetición final antes del commit: `pytest -q -p no:cacheprovider
  tests/test_provider_access.py tests/test_provider_access_postgres.py`
  → **42 aprobadas** en PostgreSQL local; frontend completo, lint y build
  repetidos con los mismos resultados indicados a continuación.
- PostgreSQL: simultaneidad de activación/reenvío y de email entre proveedores,
  rollback del perdedor, token usado/vencido/revocado, duplicados, identidad,
  aislamiento, RLS, cookie que deja de autorizar tras desactivación y legado intacto.
- Frontend completo: `npm test -- --maxWorkers=4` → **362 aprobadas, 39 archivos**.
  Incluye componentes reales de habilitación/activación/portal y navegación por rol.
- `npm run lint` aprobado. `npm run build` aprobado, con advertencia por chunk
  principal de 506,47 kB; no se desactivó la advertencia ni se hizo un refactor
  de carga de toda la aplicación fuera del alcance de HU32.
- `pip check`: sin dependencias rotas. `python -m compileall -q app
  scripts/apply_provider_access.py`: aprobado. `git diff --check`: aprobado.
- Navegador real, sesión administrativa iniciada por Talía: consulta de lista
  y acceso del proveedor existente; ese proveedor no se reactivó ni modificó.
  Revisado a 1440 px y 390 px; móvil sin desbordamiento horizontal y con menú.
- La suite PostgreSQL local usa bases `aari_hu32_<uuid>` descartables y roles de
  prueba sin login. Ningún caso automatizado usa Supabase, Gemini o correo real.
- `npm ci --ignore-scripts` instaló las versiones del lockfile sin modificarlo.
  `npm audit` reporta **9 avisos (6 altos, 3 moderados)** en dependencias de ese
  lockfile, incluidos Vite/Vitest. No se ejecutó `audit fix` ni se actualizaron
  versiones fuera de alcance; revisar en una tarea de dependencias antes de
  exponer un entorno público. No afirmar seguridad integral sólo por pasar tests.

La primera preparación de PostgreSQL local necesitó roles anon/authenticated
de prueba y confirmar explícitamente transacciones DBAPI; se corrigió el fixture.
La regresión de operadores detectó acoplamiento al nuevo padrón en auth: se
acotó esa consulta al rol proveedor, conservando el acceso de los otros roles.
El primer recorrido multiproceso HU21 no heredó PGPASSWORD de la base local;
se repitió con esa configuración corregida, sin cambiar HU21.

## Revisión manual y siguientes pasos

La app se levanta en `http://localhost:5173` contra el backend local 8000 y el
Supabase autorizado, con workers apagados para evitar envíos/consumo automáticos.
No se modifica el `.env` real: la sesión de desarrollo carga sus valores en
memoria. Requiere entorno Python con `backend/requirements.txt` y frontend
instalado desde su lockfile; no se agregó una dependencia nueva al proyecto.

Para probar: iniciar sesión como administrador, abrir un proveedor **activo**,
sección Acceso a AARI, indicar su correo y habilitar la invitación. Esa acción
sí intentará enviar correo y crea una cuenta pendiente. El destinatario abre
el email en esta misma computadora mientras la URL siga siendo localhost.
Activar es una acción del destinatario: el agente no elige su contraseña.

### Prueba manual solicitada posteriormente

Talía autorizó crear un proveedor nuevo de prueba y usar su correo para validar
la invitación. Se creó un registro claramente identificado como prueba, con
teléfono ficticio, especialidad Otros y cobertura en Localidad de prueba,
sin coincidir con la ubicación de la propiedad existente. Se conservan el
proveedor y la cuenta de prueba porque son parte de la validación solicitada.
No se publica el correo ni el identificador personal en este documento.

El primer intento falló **antes de contactar SMTP**, porque el `.env` utilizado
todavía no contenía host, remitente ni credenciales SMTP. El error quedó visible
y la cuenta no se perdió. Talía completó la configuración en su archivo local;
se reinició exclusivamente el backend de esta revisión, con workers apagados,
y se generó otra invitación, revocando la anterior y sin duplicar usuario.
SMTP aceptó el mensaje. Luego Talía confirmó por capturas en el chat tanto
la recepción en Gmail como la activación y el ingreso al portal con rol proveedor
y estado Cuenta activa. La contraseña fue elegida por la destinataria, no por
el agente. No se copian capturas con datos personales al repositorio.

La contraseña de aplicación tenía espacios de agrupación: en esta sesión se
quitaron únicamente en memoria antes de iniciar el backend. Para reinicios
normales debe quedar sin esos espacios en el `.env` local. El agente no
modificó ese archivo ni persistió una clave en código/chat/documentación.

Integrar HU19 para la bandeja real, revisar con Talía y Tobías y recién entonces
evaluar cierre. Correo, activación y acceso reales ya quedaron confirmados. No cerrar
por haber aplicado una migración o tener una demo con dobles. La autorización
de publicación es para una entrega parcial y revisable, no para su merge o
cierre. El registro de esfuerzo autorizado corresponde sólo a HU32; no se
incluyen cambios ni horas de HU33 con esta publicación.
