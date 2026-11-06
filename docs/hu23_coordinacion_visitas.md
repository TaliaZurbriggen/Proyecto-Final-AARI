# HU23 / AARI-250 — Coordinación de visitas

## Estado conciliado al 06/11/2026

HU23 y sus once subtareas están Listo; PR #42 integrado el 03/11 en `897b8bd`.
La integración terminal que los registros históricos inferiores dejaban en
AARI-345 ya fue implementada y fusionada por PR #44 en `9d38ca0` el 06/11;
AARI-345 y sus dos subtareas también figuran Listo. Los apartados fechados
anteriores conservan sus resultados y límites, no el estado administrativo actual.
La verificación compartida, migración HU24 y habilitación segura de workers
siguen como pendientes operativos; no se acredita SMTP ni despliegue por esos
merges. Ver [integración HU21](hu21_integracion_end_to_end.md) y
[seguimiento del cambio de canal](gestion/sprint_4/cambio_canal_aari_2026-10-26.md).

Inicio autorizado: 01/11/2026. Rama `codex/AARI-250-coordinacion-visitas`, desde
main `879fa07`. Estimación vigente 6 HH, sin reestimación. Talía informó y
autorizó registrar 2 HH de implementación el 01/11/2026, distribuidas abajo.
Rama rebaseada el 02/11/2026 sobre main `e5aa612` (PR #41, HU20). La base
rebaseada es `6007c59`; esta entrega incluye la integración posterior con HU20.
El recorrido funcional HU20→HU23 se validó localmente con módulos reales y,
después de autorización específica, en Supabase el 02/11/2026 con login real y
rollback. Las tres migraciones requeridas quedaron instaladas. No acredita
cierre del checkpoint de AARI-345 ni autorización de publicación/cierre de Jira.

## Decisión aprobada y recorrido

HU20 confirma presupuesto y proveedor. HU23 pide al inquilino (también cuando
paga el propietario) tres fechas diferentes con intervalos de hora argentina.
El proveedor seleccionado confirma una fecha/hora comprendida en esas opciones.
Si ninguna sirve, pulsa «No puedo en estos horarios»: habilita chat privado
proveedor↔inquilino. Cualquiera propone fecha/hora y el otro confirma explícitamente
la versión mostrada. No se exigen nuevamente tres opciones para negociar.
Conversar no confirma visita, cambia el presupuesto ni reinicia las 24 horas.
Agencia sólo consulta; el propietario no hereda el chat del inquilino.

Alternativas: sólo formulario, chat libre desde el inicio, o formulario con
negociación excepcional (elegida). La excepción evita bloquear horarios sin
convertir texto libre en autorizaciones o confirmaciones implícitas.

24 horas desde la publicación durable de opciones, no desde el correo. Al
vencer se conserva historial y se avisa al responsable; cancelar/reseleccionar
corresponde a HU24. Confirmación de visita, historial, estado y avisos atómicos.
Recordatorios 24h y 2h, sin retroactivos ni avisos de intentos obsoletos.

## Entrada real de HU20 y compatibilidad con HU21

El contrato provisional del 01/11 queda reemplazado por la decisión auditada
de `reclamo_selecciones_presupuesto`. Cada coordinación nueva guarda su
`seleccion_id`; una FK compuesta vincula decisión/reclamo/presupuesto/proveedor.
La fuente comprueba elección, ronda, actor, importe, moneda y tipo exacto/mínimo.
No basta con cargar «Proveedor seleccionado» o sus IDs directamente en reclamos.
Se conserva además `updated_at` como guarda del contexto, no como única prueba
de que hubo selección. Cambiar importe, moneda o tipo invalida nuevas acciones
y detiene avisos obsoletos, sin reescribir la decisión histórica.

El worker descubre decisiones confirmadas después de su commit; inicia el
pedido al inquilino y encola un único aviso durable. Dos workers o un reinicio
no duplican coordinaciones ni pedidos. No se agrega un envío de red dentro de
la elección HU20, ni se necesita Gemini para manejar horarios estructurados.
El intervalo normal es 30 s; requiere ambos flags de visitas habilitados y
el esquema completo. No se activaron en el entorno compartido.

El GET de comparación sólo ofrece `coordinacion_url` con la función y el
esquema disponibles, selección coincidente y estado vigente. «Ver coordinación»
respeta el rol: inquilino propone; propietario sólo consulta. La interfaz usa
los componentes/tokens AARI, no ofrece el enlace sobre un reclamo resuelto,
tras error/recarga pendiente o para una URL ajena al reclamo.

HU21 fue instalado y probado localmente con el mismo reclamo: retoma la
selección real y conserva presupuesto/proveedor; su expirador de 72h no pisa
la espera específica de HU23. Al confirmar la visita, el GET de HU21 informa
`requiere_sincronizacion=true` y el estado actual «Visita programada».
**Límite comprobado:** `resume` no admite estados terminales; no se escribió
el checkpoint a mano ni se lo presenta como sincronizado. El adaptador de
eventos/sincronización terminal quedó registrado en AARI-345 de Tobías.
La implementación local posterior de AARI-345 incorpora esa reconciliación
mediante el worker HU21, sin reabrir terminales ni convertir GET en escritura.
Resultados y límites actuales en [integración HU21](hu21_integracion_end_to_end.md);
esta evidencia original de HU23 por sí sola no acredita su despliegue compartido.

Migraciones HU23 `20261101110000_hu23_coordinacion_visitas.sql` y
`20261102103000_hu23_seleccion_auditada.sql`, aplicadas con autorización en
Supabase el 02/11/2026 junto con su requisito HU20. La segunda agrega el vínculo sin
editar los SQL anteriores. Conserva filas/acciones legadas sin atribuirles una
decisión retrospectiva: el worker las deja inactivas al preparar un intento
vinculado real. Sólo sustituye el índice de unicidad de selección para no
bloquear ese reemplazo; no borra filas, mensajes ni visitas.
Workers y funcionalidad opt-in; no se activa SMTP ni Gemini para implementar.

## Implementación local

- API privada `GET /reclamos/{id}/visita` y POST de disponibilidad,
  sin-coincidencia, propuesta y confirmación. El listado de visitas pagina en
  servidor. El usuario no elige autores, destinatarios o etapas en el payload.
- `aari_visita_coordinaciones` conserva selección/participantes/versiones;
  `aari_visita_opciones`, los intervalos; `aari_visita_acciones`, las acciones y
  sus datos inmutables; `aari_visita_avisos`, el vínculo con el outbox existente.
  Se conserva cada propuesta reemplazada para auditoría. Una visita confirmada
  se inserta en `visitas` y se actualiza el reclamo en la misma transacción.
- Subgrafo determinista en `agents/coordination/visits.py`, invocado por las
  acciones permitidas. El estado durable vive en PostgreSQL; no depende de que
  sobreviva un proceso ni requiere un LLM para interpretar horarios.
- Los hilos de finalidad `coordinacion` reutilizan secuencia, mensajes inmutables,
  lectura monotónica, paginación y bandeja global de HU33. Separados de las
  consultas técnicas del presupuesto. Se puede leer los avisos desde el inicio;
  sólo el botón de incompatibilidad habilita texto entre inquilino y proveedor.
  El responsable propietario tiene avisos separados, sin chat compartido.
- Formularios con acciones estructuradas, bloqueo de doble envío, UUID
  conservado ante respuesta incierta, errores/cargas y estilos/tokens de AARI.
  Opciones apiladas en móvil y accesos desde Mensajes y el portal del proveedor.
- Worker opt-in: descubre selecciones sin alterar la elección, materializa
  vencimientos y recordatorios; no hace SMTP. Revalidación de avisos de visita
  conectada al repositorio de notificaciones justo antes de su entrega. La
  confirmación enviada al canal no se puede retirar; se detienen avisos obsoletos.
  Resolver un reclamo no convierte automáticamente su visita histórica en
  cancelada: HU24 conserva la responsabilidad sobre la cancelación real.

## Evidencia de pruebas por tandas (no sumar por solapamiento)

- Focalizada con código y migración sincronizados:
  `python -m pytest -q -p no:cacheprovider --tb=line tests/test_visits.py tests/test_visits_postgres.py`
  → **40 aprobadas**, 332,04 s. Son 23 de reglas/API/subgrafo y 17 PostgreSQL.
- Regresión conjunta previa de visitas/mensajes → **44 aprobadas**, 893,76 s:
  15 primeras de HU23 y 29 regresiones HU33. No equivale a otra suite completa.
- Regresión backend sin PostgreSQL general:
  `python -m pytest -q -p no:cacheprovider --tb=line`
  → **1208 aprobadas / 509 omitidas**, 467,39 s; 18 advertencias SQLite previas.
  Se omitieron explícitamente las integraciones no habilitadas. Este total se
  obtuvo antes de agregar la última regresión de conservación del historial.
- Pantalla HU23:
  `npm test -- --pool=threads --maxWorkers=1 --testTimeout=20000 src/features/visitas/VisitCoordinationPage.test.jsx`
  → **8 aprobadas**, 52,87 s. Incluye formularios, zona argentina, apertura
  explícita del hilo, aceptación ajena, reintento con el mismo payload y error
  de lectura sin conservar acciones viejas.
- Repetición final PostgreSQL, después de preservar el estado histórico de
  la visita al resolver el reclamo: **18 aprobadas**, 369,51 s. Prueba adicional
  del repositorio real de notificaciones: **1 aprobada**, 22,11 s; prepara un
  aviso vigente y rechaza el mismo aviso tras resolver el reclamo, sin SMTP.
  Son tandas distintas, no otra ejecución de la suite general.
- El enlace desde Mensajes solicita cerrar el panel antes de navegar a las
  acciones de coordinación. Su regresión pasó dentro de la tanda forks de
  cuatro archivos (88 aprobadas/2 fallidas ajenas a ese enlace).
- Regresión final completa del frontend:
  `npm test -- --pool=forks --maxWorkers=1 --testTimeout=20000 --reporter=json --outputFile=tmp/hu23-final-frontend.json`
  → **463 aprobadas, 0 fallidas**, `success: true` en el reporte. Incluye las
  ocho de la pantalla HU23 y el cierre del panel antes de navegar. No se
  modificaron los módulos de filtros/Home/alta de reclamo ni sus pruebas.
- Lint/build finales correctos; advertencia conocida del bundle
  >500 kB conservada: 558,34 kB / 155,77 kB gzip, CSS 143,47/18,33 kB. Formato y
  compilación Python correctos; búsqueda de patrones de credenciales en los
  archivos del alcance sin hallazgos. Los archivos de demo están ignorados.
- Ajuste visual posterior aprobado: el botón «Abrir conversación de
  coordinación» tiene 24 px de separación superior mediante el token
  `--aari-space-5`, sin modificar su acción. Repetición focalizada con
  `npm test -- --pool=forks --maxWorkers=1 --testTimeout=20000 src/features/visitas/VisitCoordinationPage.test.jsx`
  → **8 aprobadas**; `npm run lint`, `npm run build` y `git diff --check`
  correctos. Build posterior: JS 558,42/155,80 kB gzip y CSS 143,54/18,35 kB.
  La suite completa de 463 corresponde a la tanda anterior al ajuste de espacio.

Regresión frontend: primera completa con threads/2 workers, **444 aprobadas y
18 fallidas** en filtros/Home/alta de reclamo. Repetición aislada de esos tres
archivos con threads/1 worker, **75 aprobadas y 14 fallidas**; con forks/1 worker
mismos archivos más el enlace de Mensajes, **88 aprobadas y 2 fallidas** (ambas
en filtros de propiedades). No se afirma que sea sólo el entorno ni se cambian
los casos para ocultarlos. Se preparó una copia temporal de main `879fa07` para
comparar; no se modificó su código. La última regresión completa forks/1 worker
aprobó las 463 pruebas. Se conservan las tandas fallidas como diagnóstico;
el resultado final no prueba por sí solo una causa concreta de esos fallos.

Las primeras pruebas detectaron un campo obligatorio faltante en los avisos y
una diferencia entre Session/Connection en el helper de disponibilidad; ambos
corregidos. Se ajustó una prueba que construía una versión inválida antes de
alcanzar la comprobación de obsolescencia. Una tanda con archivos editados
mientras se ejecutaba mezcló un esquema nuevo con código ya importado: se
repitió con archivos sincronizados, sin presentar ese fallo como aprobado.
Frontend detectó export de hook junto a componentes y un efecto inicial: se
separó el contexto y se corrigió sin desactivar reglas de lint. Una primera
tanda forks sólo aprobó 16 pruebas y reportó dos fallos de arranque de workers;
no se considera aprobada. Las ocho HU23 se repitieron con threads sin errores.

## Demostración y pendientes de integración

Demo temporal ignorada por Git en
`http://127.0.0.1:13610/tmp/hu23-review.html`: componentes y API reales,
PostgreSQL local, identidades simuladas explícitas y selección preparada por
fixture. Selector para inquilino/proveedor/propietario; no se usan cuentas,
contratos o correos reales. HTTP de interfaz 200 y detalle con disponibilidad
comprobados. No acredita login normal ni selección HU20 real.

La herramienta de navegador agotó dos intentos de conexión; no se acredita
revisión visual automatizada de escritorio/móvil. Talía puede revisar la demo.
En esa demostración inicial no se aplicó la migración en Supabase ni se
enviaron mensajes externos; la validación compartida posterior consta abajo.

Antes de declarar HU23 terminada: completar el adaptador de checkpoint
terminal HU21/AARI-345 y su validación multi-HU, y obtener revisión del PR.
El esquema compartido y login real se verificaron posteriormente, como se
detalla abajo; no se acredita un recorrido manual completo con todas las
cuentas reales. No se implementa la
cancelación/reselección de HU24 ni se expira por cuenta propia la espera del
inquilino mediante un plazo nuevo no acordado. La actividad en el chat no
renueva las 24 horas específicas del acuerdo.

## Registro de esfuerzo y autorización de publicación

Talía autorizó commit y push de esta rama, sin solicitar PR ni cierre de Jira.
Se registraron **120 minutos** sólo en las subtareas, sin duplicarlos en la HU.
La distribución es orientativa del total informado, no una medición automática:

| Subtarea | Minutos | Trabajo registrado |
| --- | ---: | --- |
| AARI-251 | 20 | Disponibilidad, fechas e intervalos |
| AARI-252 | 10 | Publicación en AARI y aviso durable |
| AARI-253 | 20 | Confirmación y negociación excepcional |
| AARI-254 | 5 | Avisos de confirmación y revalidación |
| AARI-255 | 10 | Estado, visita e historial atómicos |
| AARI-256 | 5 | Recordatorio 24h |
| AARI-257 | 5 | Recordatorio 2h |
| AARI-258 | 10 | Vencimiento y conservación del historial |
| AARI-259 | 10 | Base de subgrafo; integración definitiva pendiente |
| AARI-260 | 15 | Pruebas locales y regresión |
| AARI-261 | 10 | Revisión de interfaz, ajuste visual y verificaciones |

Worklogs `10356`–`10366`, del 01/11/2026. HU y subtareas permanecen En curso.
No se alteran estimaciones, decisiones de alcance ni los pendientes anteriores.

## Integración HU20 aprobada el 02/11/2026

Rebase local sobre main `e5aa612`, conservando los validadores de avisos HU20
y HU23 en `prepare_notification_delivery`. Backup anterior `ce15adc` en la
rama local `codex/backup-AARI-250-pre-rebase-20261102`. Al finalizar la validación
el rebase seguía local, sin autorización nueva de publicación ni horas adicionales.
La autorización posterior para commit/push/PR consta al final de este documento.

Resultados posteriores, sin sumar tandas solapadas:

- `python -m pytest -q -p no:cacheprovider --tb=short tests/test_visits_postgres.py tests/test_visits_hu20_integration_postgres.py tests/test_quote_selections_postgres.py tests/test_visits.py tests/test_quote_selections.py`
  → **110 aprobadas**, 49,51 s, con PostgreSQL local. Incluye ocho recorridos
  HTTP (ordinario/extraordinario × exacto/mínimo × directo/negociación), selección
  real, replay, workers simultáneos, recreación, FK cruzada, migración aditiva
  con historia legada, importes alterados y contrato de compatibilidad HU21.
  En HTTP se sustituye sólo la identidad de sesión por cuentas ficticias; los
  repositorios, permisos de dominio, transacciones y subgrafos son reales.
- Regresión PostgreSQL de HU33, HU21 y portal HU19:
  `python -m pytest -q -p no:cacheprovider --tb=short tests/test_conversations_postgres.py tests/test_coordination_postgres.py tests/test_quote_portal_postgres.py`
  → **141 aprobadas**, 96,74 s. Tanda independiente, no otra suite backend
  completa. Incluye los checks de persistencia/recovery existentes de HU21.
- `python -m pytest tests -q -p no:cacheprovider --tb=short`
  → **1222 aprobadas / 565 omitidas**, 20,85 s; 18 advertencias SQLite previas.
  Sin `AARI_TEST_POSTGRES_URL`, dotenv deshabilitado y Supabase desactivado.
  No equivale a ejecutar toda la suite de integraciones PostgreSQL.
- `npm test -- --pool=forks --maxWorkers=1 --testTimeout=20000 --reporter=json --outputFile=tmp/hu23-integracion-frontend.json`
  → **488 aprobadas, 0 fallidas**, `success=true`. Tanda focal de comparación,
  visitas y navegación desde Mensajes: **33 aprobadas**. `npm run lint` y
  `npm run build` correctos; bundle 566,28/157,83 kB gzip, aviso >500 kB vigente.
  `compileall` y formato correctos al escribir este registro.

Diagnóstico conservado: la primera tanda de fixtures nuevos tuvo 36 aprobadas,
3 fallidas y 24 errores porque buscaba la solicitud ya respondida con el filtro
predeterminado «pendientes». Se corrigió sólo la consulta del fixture a «todas»;
las 27 de visitas pasaron después y luego se ejecutó la tanda integrada de 110.
La primera regresión backend sin ruta explícita intentó recolectar la copia
temporal de main dentro de `tmp/hu23-baseline` y falló por módulos duplicados;
se repitió apuntando a la carpeta oficial `tests`, sin excluir pruebas de ella.

En esas tandas locales no se usaron Supabase, SMTP, Meta ni Gemini.
Documentación versionada en el repo,
según la actualización de AGENTS.md incorporada desde HU20; Notion no es un
requisito ni un pendiente de cierre. HU/subtareas continúan En curso.

### Revisión visual aislada de la integración

Vista temporal ignorada por Git:
`http://127.0.0.1:13610/tmp/hu23-integracion-visual.html`. Usa los componentes
reales de comparación/coordinación y una API simulada explícita, sin cuentas
reales ni persistencia de formularios. No es el recorrido PostgreSQL de arriba.
Verificados: escritorio 1440 px, móvil 390 px (ancho de documento 1425/375 px,
respectivamente, sin desborde horizontal), foco de teclado en «Ver coordinación»,
navegación al formulario de tres fechas y variante del propietario sin formulario
de disponibilidad. Se mantuvieron componentes, tokens y estilos AARI.

El primer Enter tuvo una recarga transitoria en la vista de QA; el clic posterior
mostró el formulario esperado. El selector auxiliar se consultó por su rol
accesible después de que el locator de etiqueta exacta no lo encontrara.
La sesión del navegador se interrumpió al terminar: no se acredita la comprobación
visual final de «Resuelto» ni la restauración del tamaño, aunque la ocultación del
enlace para ese estado sí está cubierta por las pruebas automatizadas.

## Supabase y autenticación real — 02/11/2026

Talía autorizó aplicar/verificar las migraciones y probar con login real.
No se autorizó ni ejecutó un envío real de SMTP, Gemini o Meta. Se leyó la
configuración privada existente sin copiar claves al repositorio ni imprimirlas.

El preflight confirmó la ausencia de los tres cambios y de instalaciones
parciales. Antes de escribir se creó un respaldo privado con `pg_dump` en
`backend/tmp/` (ignorado por Git; contiene datos privados y no se publica).
Se ensayó la operación con rollback y luego se aplicaron, en una transacción:

1. `20261029120000_hu20_seleccion_presupuesto.sql`.
2. `20261101110000_hu23_coordinacion_visitas.sql`.
3. `20261102103000_hu23_seleccion_auditada.sql`.

Se registraron las tres versiones en el historial. Los conteos de las 42 tablas
públicas previas y el estado de sus secuencias se preservaron. Se verificaron
RLS, ausencia de permisos/políticas públicas, índices válidos y FK compuesta.
La consulta posterior confirmó las tres instaladas, sin repetir DDL.
No se borraron ni se completaron retrospectivamente decisiones existentes.

Comprobador versionado: `backend/scripts/check_visits_postgres.py`. Desde
`backend/`, con la ruta a la configuración privada sólo en el equipo:

```text
python scripts/check_visits_postgres.py --env-file <ruta-privada> --mode check
python scripts/check_visits_postgres.py --env-file <ruta-privada> --mode test
```

`check` sólo inspecciona. `dry-run` ensaya y revierte. `apply` requiere
autorización, `--pg-dump <ejecutable>` y respaldo correcto antes de escribir;
una instalación coherente ya aplicada no se repite. Rechaza destinos ajenos a
Supabase, historial inconsistente, objetos parciales y dependencias fuera de
orden. No es un migrador global ni habilita workers. `test` también requiere
autorización explícita y sólo ejecuta los casos HU23 acotados.

`backend/tests/test_visits_supabase_integration.py` → **4 aprobadas**, 428,93 s:
ordinario/extraordinario × confirmación directa/negociación excepcional. Usan
PostgreSQL compartido, repositorios reales, hash de contraseña real y cookies
JWT emitidas por `/auth/login`; no se sustituye `get_current_user`. La fábrica
de sesiones se enlaza a una transacción exterior para revertir cada caso.
Comprueban 401 sin sesión, identidad, selección HU20, tres intervalos, aceptación
ajena, visita única y plazo sin reinicio. Los casos de negociación usan mínimo;
los directos, importe exacto. No es una nueva evaluación de clasificación LLM.

Los registros ficticios usan IDs propios y número explícito, sin consumir la
secuencia pública. Cada caso revierte y comprueba inventario/secuencias y
ausencia del reclamo de QA. El inicio de coordinación se limita al reclamo
ficticio; no se ejecutó un worker global sobre reclamos existentes. Los correos
son ficticios y SMTP está bloqueado por la prueba.

Aceptación en navegador integrado: Talía ingresó con su cuenta administradora
en la app normal `http://localhost:5173`; se verificaron Inicio y `/visitas`
contra el backend normal `http://localhost:8000`, sin API simulada ni reemplazo
de autenticación. El listado real cargó sin errores y quedó vacío: las pruebas
no dejaron visitas ficticias. Esto acredita login/lectura reales, no un recorrido
manual de todos los roles. Se restauró el tamaño normal del navegador.

Para esta sesión se habilitaron visitas, portal y Mensajes sólo en el proceso
local. Se mantuvieron desactivados todos los workers generales y envíos; no se
editó el `.env` compartido. El despliegue/activación automática y el adaptador
terminal HU21 de AARI-345 no se presentan como resueltos por estas pruebas.
Al cerrar esta validación aún no se habían hecho nuevos commits, push, PR,
horas o cierres de Jira.

Regresión final después de agregar el comprobador y la prueba compartida:
`python -m pytest tests -q -p no:cacheprovider --tb=short` → **1230 aprobadas /
569 omitidas**, 20,80 s; 18 advertencias SQLite previas. Dotenv y Supabase
deshabilitados, sin URL PostgreSQL local ni opt-in compartido: las cuatro
pruebas externas quedan omitidas en esta tanda, no se vuelven a ejecutar.
Incluye ocho guardas nuevas sin red (`test_check_visits_postgres.py`): rechazo
de destinos ajenos/sufijos engañosos, parámetros ocultos, conexión acotada y
envoltorios SQL compatibles con la transacción exterior. La evidencia previa
de 1222/565 corresponde a la tanda anterior, sin estas nuevas pruebas.

## Publicación autorizada para revisión — 02/11/2026

Talía autorizó subir los cambios y crear el PR con contexto para Tobías.
Se publica la rama rebaseada sobre main `e5aa612`, sin reemplazar cambios ajenos:
la actualización remota verifica la cabeza anterior esperada. Se incluyen la
integración HU20, migración aditiva, comprobador compartido, regresiones y esta
evidencia. El respaldo, configuración privada y lanzadores temporales siguen
ignorados por Git. No se repiten migraciones ni se consume cuota al publicar.

El PR solicita revisión de la entrega HU23, no certifica el cierre de AARI-345.
Se deja explícito el límite de sincronización terminal HU21 y los workers
generales desactivados. HU/subtareas continúan En curso, sin horas adicionales
ni autorización de merge o cierre en esta publicación.
