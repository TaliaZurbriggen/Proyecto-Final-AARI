# HU23 / AARI-250 — Coordinación de visitas

Inicio autorizado: 01/11/2026. Rama `codex/AARI-250-coordinacion-visitas`, desde
main `879fa07`. Estimación vigente 6 HH, sin reestimación. Talía informó y
autorizó registrar 2 HH de implementación el 01/11/2026, distribuidas abajo.
Implementación en curso; no acredita una entrega integrada con HU20.

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

## Paralelo con HU20 y HU21

Contrato de entrada provisional, usando columnas ya existentes: reclamo en
`Proveedor seleccionado`, presupuesto y proveedor coherentes, solicitud HU19,
responsable original y participantes activos. Se conserva `updated_at` de la
selección y el contexto de participantes para rechazar resultados tardíos.
HU23 no decide ni simula selección en producción. La selección de prueba sólo
se prepara en PostgreSQL local. Cuando HU20 se integre hay que revisar este
contrato contra su versión/intento definitivo y repetir el flujo con módulos
reales. Integración multi-HU del checkpoint permanece en AARI-345 de Tobías.

Migración nueva `20261101110000_hu23_coordinacion_visitas.sql` sólo local hasta
autorización específica para Supabase. No editar migraciones ya desplegadas.
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
No se aplicó la migración en Supabase ni se enviaron mensajes externos.

Antes de declarar HU23 terminada: conectar el contrato definitivo de HU20,
validar la proyección/checkpoint y convivencia de plazos con HU21/AARI-345,
repetir el flujo integrado, completar aceptación visual, autorizar/verificar
el despliegue compartido y obtener revisión del PR. No se implementa la
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
