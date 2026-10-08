# Sprint Planning — Sprint 4

**Acta y verificación:** 08/10/2026. Participantes: Talía y Tobías.

**Estado:** planning completada; Sprint 4 activo en Jira, iniciado por Talía.

**Período configurado en Jira:** 09/10/2026 al 06/11/2026, hora argentina (cuatro semanas). No se modifica ni se retrodata el inicio.

**Duración real de la planning:** 2 horas de reunión con ambos participantes = **4 HH del equipo**, registradas una sola vez en [AARI-344](https://taliazurbriggen.atlassian.net/browse/AARI-344), lista.

**Capacidad orientativa inicial:** aproximadamente **30 HH de implementación**, con reuniones aparte; el compromiso final aprobado pasó a **46 HH**, no se presenta como 30 HH.

**Total reestimado y verificado en Jira:** **46 HH de implementación** en nueve HU, sin despliegue ni reuniones.

**Origen de la prioridad:** el equipo informa que la cátedra pidió incluir la coordinación del agente con proveedores en este Sprint para entregar valor antes de las vacaciones.

El 08/10 se autorizó cargar toda la reestimación de las nueve HU en Jira y,
posteriormente, sumar 2 HH a cada una. Se actualizaron únicamente el tiempo
estimado y restante de sus subtareas, conservando los story points originales.
En esa primera etapa el Sprint 4 (ID 73) todavía era futuro; la carga de
estimaciones no lo inició ni cambió estados o responsables. Posteriormente,
Talía informó su inicio y una nueva consulta confirmó **state=active** y las
fechas indicadas arriba. Las nueve HU ya tienen el reparto acordado y se
asignaron sus 81 subtareas al responsable de cada historia. Se mantienen
**Por hacer** hasta iniciar cada implementación con su propuesta aprobada.
AARI-338 quedó fuera. Esta planificación no implementa funcionalidad nueva
ni sustituye la aprobación de cada propuesta de implementación.

## 1. Objetivo acordado

Que un reclamo clasificado pueda pasar de la decisión del responsable a un
proveedor seleccionado y una visita acordada con el inquilino, conservando
el contexto, las autorizaciones, las comunicaciones y el historial. Validar
el recorrido integrado en un entorno de prueba acordado, sin acreditar como
entregado el despliegue completo que queda fuera de esta reestimación.

El incremento acordado llega a **Visita programada**, no a **Resuelto**.
La conformidad y el cierre de la reparación pertenecen a HU25, que queda
fuera del compromiso inicial. Coordinar una visita ya entrega valor operativo,
pero no significa que toda la gestión del reclamo esté terminada.

## 2. Base disponible y trabajo que todavía falta

- Sprint 3: ocho HU listas; clasificación, contexto contractual revisado,
  notificaciones, historial, escalados y expensas integrados en main.
- Proveedores: padrón, especialidades, coberturas estructuradas, activación y
  horario habitual. Ese horario **no es una agenda ni confirma disponibilidad**.
- `03_modulo_coordinacion.sql` ya define presupuestos, proveedores externos,
  visitas, cancelaciones y sesiones del agente. Esto ahorra diseño inicial,
  pero no demuestra que sus restricciones, permisos y flujos estén listos:
  deben verificarse y ajustarse con migraciones aditivas si hace falta.
- El grafo actual clasifica y determina el actor responsable; no tiene
  checkpointing de la coordinación. HU21 no está implementada sólo porque
  exista la tabla `sesiones_agente`.
- `DisabledWhatsappSender` rechaza los envíos: el canal real no está
  configurado. HU19 necesita integración nueva, autenticación y recepción.
- AARI-338 está Por hacer, con sus cinco subtareas, sin Sprint activo/futuro.
  Su pertenencia histórica al Sprint 3 cerrado se conserva.

## 3. Reestimación aprobada y cargada en Jira

Se consultaron las HU y todas sus subtareas relevantes en Jira. Para las
estimaciones originales se sumó `Story point estimate` de las subtareas
según la convención académica del equipo: **1 punto = 1 HH original**.
Las HU padre no tienen ese valor; no se duplica el agregado.

| Jira | Historia / entrega | Original preservada | Reestimación cargada | Motivo de la nueva estimación |
| --- | --- | ---: | ---: | --- |
| [AARI-170](https://taliazurbriggen.atlassian.net/browse/AARI-170) | HU15 — buscar candidatos por especialidad y cobertura, con atención a faltantes | 27 HH | 5 HH | Reutiliza el padrón; incluye mapeo de rubro, filtros geográficos, estado, historial, alertas y QA. |
| [AARI-180](https://taliazurbriggen.atlassian.net/browse/AARI-180) | HU16 — autorizar o rechazar gasto extraordinario | 25 HH | 5 HH | Reutiliza autenticación/notificaciones; agrega decisión exclusiva, recordatorios y vencimiento. |
| [AARI-191](https://taliazurbriggen.atlassian.net/browse/AARI-191) | HU17 — elegir proveedor fidelizado o propio | 17 HH | 4 HH | Decisión acotada sobre el mismo reclamo; reutiliza recordatorios y persistencia compartida. |
| [AARI-199](https://taliazurbriggen.atlassian.net/browse/AARI-199) | HU18 — registrar proveedor externo | 10 HH | 4 HH | Formulario breve y entidad prevista; valida datos, permisos y derivación sin incorporarlo al padrón. |
| [AARI-206](https://taliazurbriggen.atlassian.net/browse/AARI-206) | HU19 — solicitar y recibir presupuestos por WhatsApp | 38 HH | 7 HH | Mayor riesgo: canal nuevo, webhook, parsing validado, persistencia, duplicados y timeout. |
| [AARI-220](https://taliazurbriggen.atlassian.net/browse/AARI-220) | HU20 — comparar y seleccionar presupuesto | 20 HH | 5 HH | UI/API conocidas; requiere validar la elección vigente y notificarla sin duplicados. |
| [AARI-229](https://taliazurbriggen.atlassian.net/browse/AARI-229) | HU21 — persistir y retomar el contexto de coordinación | 52 HH | 6 HH | Base nueva de orquestación y recuperación; incluye escenarios multi-turno e integración de los módulos. |
| [AARI-250](https://taliazurbriggen.atlassian.net/browse/AARI-250) | HU23 — acordar visita proveedor–inquilino | 33 HH | 6 HH | Opciones, confirmación, horarios, recordatorios, timeout y continuidad del grafo. |
| [AARI-262](https://taliazurbriggen.atlassian.net/browse/AARI-262) | HU24 — cancelar y volver a elegir proveedor | 24 HH | 4 HH | Reutiliza los pasos anteriores; incluye auditoría, invalidación de respuestas viejas, alertas y bloqueo tras visita programada. |
| **Total de implementación** | **9 HU** | **246 HH** | **46 HH** | **Time Tracking de 81 subtareas; agregado verificado sin duplicar padres.** |

**Actualización posterior solicitada el 08/10:** sumar **2 HH a cada una de las
nueve HU**, incluidas HU19 y HU20. La primera carga de 28 HH se conserva como
registro histórico; esta nueva estimación la sustituye: **28 + 18 = 46 HH**.
El ajuste no agrega funcionalidad ni reuniones al alcance.

[AARI-338](https://taliazurbriggen.atlassian.net/browse/AARI-338) conserva sus
4 HH y permanece pendiente, sin cambios por esta carga; su Sprint de destino
se acordará después. No se incorporó HU25. El nuevo total supera en **16 HH**
la capacidad orientativa inicial de 30 HH. La indicación posterior de completar
todo lo planificado confirma el compromiso de las nueve HU por 46 HH; no se
presenta ese alcance como si fueran 30 HH. Ante un bloqueo se discutirá el
alcance explícitamente, sin modificar silenciosamente esta línea base.

### Desglose y verificación de la carga

En cada HU se distribuyeron los 120 minutos adicionales como **30 minutos en
cuatro subtareas principales**, priorizando implementación, integración y
pruebas. Se ajustaron 36 subtareas; las otras 45 conservaron sus tiempos.
No se aplicó una regla de tres sobre los puntos originales.

El detalle por subtarea, su estimación original preservada y sus nuevos minutos
están en [el registro actualizado de 46 HH](gestion/sprint_4/reestimacion_jira_2026-10-08_ajuste_2hh.json).
Se conserva sin modificaciones [la primera carga de 28 HH](gestion/sprint_4/reestimacion_jira_2026-10-08.json).
Cada HU tiene un nuevo comentario con su total y los incrementos, manteniendo
el comentario anterior como evidencia histórica. Una lectura posterior de
Jira verificó las 81 estimaciones, el tiempo restante y los agregados de las
nueve HU: **46 HH exactas**. Se conservaron estados, sprints, asignaciones,
story points y ausencia de worklogs. Las HU padre no recibieron una segunda
estimación que duplicara el total de sus subtareas.

### Qué incluye y cómo se interpreta

Las 46 HH cargadas incluyen desarrollo, pruebas automáticas, revisión, correcciones,
integración, validación externa autorizada y documentación. No se agrega
otra estimación de pruebas sobre esos mismos trabajos.

La referencia es el esfuerzo informado en Sprint 2 y Sprint 3: CRUD de personas/
inmuebles alrededor de 1,5–2,5 horas y reutilización de notificaciones alrededor
de 0,8–1,7 horas. HU30 tomó 8 h 25 min y muestra que una dependencia nueva puede
exceder una previsión: por eso WhatsApp, persistencia y coordinación no reciben
la misma estimación que un formulario pequeño.

**No es una regla de tres ni una garantía de terminar en las HH estimadas.** No
se eliminan criterios de aceptación para hacerlas encajar. HU19 y HU21
concentran incertidumbre: si la prueba temprana contradice estas previsiones,
el equipo debe documentar el bloqueo y acordar cualquier ajuste de alcance.
Durante la ejecución se conservan las estimaciones iniciales del Sprint y
se registra el trabajo real aparte.

La reestimación ya se cargó en Time Tracking de las subtareas, sin duplicarla
en la HU padre y preservando puntos originales. Se conserva una
[fotografía inicial del alcance, reparto y tiempos](gestion/sprint_4/inicio_sprint_4_2026-10-08.json)
para los gráficos y la comparación estimado versus real.

### Reuniones fuera de las HH de implementación

La **planning ya realizada** duró dos horas con ambos integrantes: **4 HH
reales del equipo**, registradas en AARI-344 con un único worklog consolidado.
La tarea está lista, con estimación de 4 HH y restante cero. La asignación
administrativa y la autoría del registro no implican cuatro horas individuales
de Talía: se documenta expresamente el esfuerzo de los dos participantes.

Se mantienen separados **46 HH de implementación comprometida + 4 HH reales
de planning = 50 HH**, no 50 HH ya trabajadas. La review y retrospectiva
todavía no se realizaron; una reserva orientativa de **2 HH** llevaría el
total a **52 HH**, pero no es tiempo real ni un registro ya cargado.

## 4. Por qué van juntas estas historias

Recorrido principal:

1. Reclamo clasificado → actor responsable identificado por el flujo existente.
2. Si es extraordinario: el propietario autoriza o rechaza (**HU16**).
3. El responsable elige fidelizado o propio (**HU17**).
4. Propio: se registra el contacto y se deriva (**HU18**). No se promete
   coordinación automática para la rama externa, que tiene su propio estado final.
5. Fidelizado: se buscan candidatos (**HU15**) y se piden presupuestos (**HU19**).
6. El responsable compara y elige (**HU20**).
7. Se reciben opciones del inquilino, el proveedor confirma y se programa
   la visita (**HU23**).
8. Si el responsable cancela en una etapa permitida, se vuelve a elegir
   conservando el reclamo y descartando efectos tardíos del intento anterior (**HU24**).

**HU21** guarda y retoma el contexto durante todo ese recorrido. Se incluye
HU24 porque sus escenarios de cancelación/reelección ya están exigidos por
AARI-235 dentro de HU21. Dejar HU24 afuera y dar HU21 por terminada sin esos
casos no sería consistente con las subtareas actuales.

Las expensas conservan el circuito ya entregado de HU14. Los escalados de
clasificación conservan la decisión humana de HU13. No se vuelve a consultar
el modelo para reemplazar una clasificación que ya quedó decidida.

## 5. Reparto acordado y trabajo en paralelo

| Integrante | HU asignadas | Implementación HU |
| --- | --- | ---: |
| Talía | HU15, HU18, HU19 y HU23 | **22 HH** |
| Tobías | HU16, HU17, HU20, HU21 y HU24 | **24 HH** |
| **Equipo** | | **46 HH** |

El reparto está registrado y verificado en las nueve HU y sus 81 subtareas.
Antes del aumento ambas partes sumaban 14 HH; al añadir 2 HH por HU, Talía
agrega 8 HH por sus cuatro historias y Tobías 10 HH por sus cinco. Se conserva
ese reparto relacionado por flujo, con una diferencia de 2 HH:
candidatos/comunicación/visita por un lado y decisiones/presupuestos/contexto
por el otro. No se alteraron estados, estimaciones ni puntos al asignar.

Antes de programar en paralelo deben acordarse: estados/transiciones, payloads,
identificadores de intento, eventos de comunicación, permisos por actor y
responsable de cada migración. El estado persistido del reclamo y el checkpoint
deben actualizarse de forma coherente, no como dos fuentes divergentes.

Una rama y un PR por HU/tarea desde el main vigente. Definir contratos de
API permite desarrollar con dobles mientras se integra la dependencia real.
No implica que todas las HU puedan terminar simultáneamente: HU20 depende
de HU19 y HU23 depende de una selección válida. HU21 comienza como base
y termina con las pruebas integradas.

## 6. Secuencia propuesta para cuatro semanas

- **Inicio / primera semana:** definir estados y contratos; probar la viabilidad
  de WhatsApp y su endpoint HTTPS de prueba; comenzar persistencia HU21, candidatos HU15 y decisión HU16.
  La prueba técnica del canal se cuenta dentro de HU19, no como un trabajo
  adicional oculto.
- **Segunda semana:** completar decisiones HU16/HU17/HU18, envío/recepción
  HU19 y la base de persistencia; validar timeout sin esperar horas reales.
- **Tercera semana:** integrar presupuestos HU20, coordinación HU23,
  cancelación HU24 y recuperación por sesión.
- **Cuarta semana:** pruebas integradas, revisión cruzada, correcciones,
  demostración en el entorno de prueba acordado y cierre. Reservar los últimos dos días
  para integración y revisión, no para iniciar el webhook.

No esperar al cierre para integrar. Mantener un bloque diario protegido para
AARI y actualizar worklogs/estado al finalizar la jornada. La demora de una
aprobación externa no se cuenta como HH trabajadas, pero sí se registra como
bloqueo del calendario.

## 7. Riesgos y decisiones que requieren acuerdo

### WhatsApp real y restricción de costo

El equipo mantiene el requisito de **no pagar ni ingresar tarjeta**.
La plataforma oficial contempla tarifas por mensajes y categorías; no se
puede suponer que iniciar solicitudes de presupuesto sea gratis en todos los
casos. Fuente oficial consultada el 08/10:
[Precios de WhatsApp Business Platform](https://whatsappbusiness.com/products/platform-pricing/).

Al comienzo hay que verificar con la cuenta del equipo qué entorno de pruebas
y destinatarios controlados están disponibles, qué plantillas acepta y si
permite envío/recepción sin facturación. No se ha probado esa cuenta. La guía
de inicio de Meta devolvió 429 durante la consulta; no se afirma que la
configuración gratuita esté garantizada.

**Criterio de entrega propuesto:** un recorrido real de ida/vuelta con participantes
de prueba autorizados y un webhook verificado, además de la suite con mocks.
No activar facturación ni enviar datos de clientes/proveedores reales sin
autorización. No automatizar WhatsApp Web ni usar integraciones no oficiales.

Si sólo funciona una simulación, se informa como tal: **no acredita WhatsApp
real ni la finalización completa de HU19**. Un cambio de canal o alcance necesita
aprobación del equipo y, si modifica lo pedido, acuerdo con la cátedra; no se
decide silenciosamente durante la implementación.

### Orquestación, concurrencia y tiempo

- Definir explícitamente cómo se correlaciona cada respuesta con reclamo,
  proveedor e intento; un teléfono por sí solo no alcanza cuando hay varios
  reclamos. Verificar firma/autenticidad y deduplicar eventos del webhook.
- El agente coordina pasos; no autoriza gastos ni selecciona presupuestos
  por el responsable. La IA puede proponer una interpretación, pero montos,
  fechas y transiciones requieren validaciones del sistema y confirmación
  cuando la respuesta sea ambigua.
- Mapear rubro a especialidad sin inventar disponibilidad. Sin rubro válido,
  candidatos o acuerdo, conservar un estado visible y notificar al operador.
- Horarios y fechas en zona argentina; no confirmar turnos que el proveedor
  no aceptó. El horario habitual es una referencia, no un cupo reservado.
- Aplicar decisiones exclusivas e idempotentes. Un webhook repetido, worker
  duplicado o respuesta de un intento cancelado no debe generar otra visita,
  envío ni transición.
- Reutilizar la bandeja de salida y workers existentes; no suponer que porque
  hay scheduler ya están implementadas las reglas de 24/48/72 horas.
- Acordar la interacción entre expiración de sesión, recordatorios y una visita
  futura, para que un timeout no cambie arbitrariamente un caso ya programado.
- Persistencia y efectos externos deben poder retomarse tras reiniciar el backend.

### Despliegue

AARI-338 no forma parte de las nueve HU reestimadas por 46 HH. Conserva sus
4 HH y queda pendiente para acordar su planificación posterior. Cuando se
retome, se requiere endpoint público para recepción y un worker que procese recordatorios.
El servicio todavía no está seleccionado. Revisar CPU/memoria, OCR, tareas
en segundo plano, SMTP, HTTPS, secretos y cookies; no dar por viable un
hosting sólo porque tenga un plan gratuito. Si no cumple los requisitos,
replanificar explícitamente y mantener una demostración local identificada
como tal, sin presentar esa alternativa como despliegue entregado.

Aunque el despliegue completo queda fuera de esta reestimación, HU19 sigue necesitando un endpoint
público HTTPS para validar el webhook de WhatsApp. Hay que acordar ese entorno
de prueba; postergar AARI-338 no elimina la dependencia del canal.

## 8. Validación y Definition of Done

- Pruebas de permisos por propietario/inquilino/administración y consultas
  fuera del reclamo del actor; regresiones de HU12/HU13/HU14/HU30.
- Candidatos por especialidad y geografía; sin candidatos y datos incompletos.
- Autorizar/rechazar de forma exclusiva y concurrente; no coordinar un gasto
  extraordinario antes de su autorización.
- Ramas fidelizado/propio, presupuesto positivo, selección vigente y auditoría.
- Webhooks con firma inválida, repetidos, tardíos y respuestas ambiguas;
  no atribuir una respuesta a otro reclamo del mismo proveedor.
- Al menos cinco escenarios multi-turno exigidos por HU21, incluyendo
  cancelación/reelección y recovery después de reiniciar.
- No respuesta, cero presupuestos, expiración, recordatorios y ausencia
  de confirmación probados con reloj simulado; eventos únicos.
- Confirmación de visita, zona horaria, cancelación permitida y bloqueo
  después de Visita programada; pantalla responsive y accesible.
- Backend con PostgreSQL local y frontend completo, lint y build; pruebas
  automatizadas sin APIs externas. Al planificar sólo se consultaron fuentes
  y Jira: no se llamó a Gemini/Supabase ni se enviaron mensajes por WhatsApp/SMTP.
- Validaciones reales de WhatsApp, correo, Supabase y despliegue sólo con
  autorización y datos ficticios/participantes consentidos.
- PR revisado, documentación/evidencia y worklogs al día. Una HU sólo queda
  lista con sus criterios cubiertos, no por cerrar algunas subtareas.

## 9. Fuera del compromiso inicial

- **AARI-338:** despliegue completo del entorno compartido, fuera de las 46 HH
  aprobadas. Sin cambios en sus subtareas, estimaciones o estado.
- **HU22 / AARI-238:** recuperación avanzada del LLM. Ya existe escalado
  seguro y revisión manual, pero eso no cubre todos sus reintentos,
  pausas y recovery automático. Sigue pendiente, no se la da por hecha.
- **HU25 / AARI-272:** conformidad/disconformidad y cierre posterior al trabajo.
  Es el paso lógico del próximo incremento; no confundir visita con reparación.
- **HU26–HU28:** métricas, exportación y recurrencia. Se prioriza el recorrido
  operativo antes de sumar análisis.
- Interpretación jurídica autónoma de contratos y nuevas rondas de ajuste
  de prompt no indispensables para la coordinación.

Si sobra capacidad, HU25 puede volver a evaluarse, pero no se suma como promesa
gratuita ni se usa para justificar una estimación menor de los riesgos nuevos.

## 10. Estado de inicio y próximos pasos

Fuentes: [cierre del Sprint 3](gestion/sprint_3/review_retrospectiva.md);
Jira de AARI (HU15–HU25 y AARI-338, sus descripciones/subtareas/estimaciones
consultadas el 08/10); grafo de clasificación y servicio de notificaciones de
main `40d9c86`; migración inicial del módulo de coordinación.

Verificación de inicio: Sprint 4 activo, nueve HU asignadas y 81 subtareas
asignadas; estimación y restante de implementación **46 HH exactas**, con
**246 puntos originales** preservados. Planning AARI-344 lista: **4 HH**,
un solo worklog y restante cero. Las nueve HU y sus subtareas siguen Por hacer.

El acta completa también queda en la descripción de AARI-344. Notion rechazó
la creación del acta bajo Ceremonias y actas porque se agotaron los bloques
gratuitos del espacio. No se borró contenido ni se cambió el plan. La publicación
completa allí queda pendiente. Sí se pudo actualizar y verificar el estado del
[Hub de Notion](https://app.notion.com/p/3a0f9f68a0c180cfa9d8ef06ef7da616),
sin agregar bloques, con Sprint activo, fechas, alcance, reparto y planning.
El campo objetivo del Sprint en Jira está vacío; el objetivo acordado está en
AARI-344 y en esta acta. Completar ese campo desde la interfaz queda pendiente:
no hay acción disponible en la conexión y Chrome no está conectado.
La publicación de estos archivos fue autorizada el 08/10 en la rama
`codex/sprint-3-cierre-sprint-4`; queda pendiente crear, revisar y aprobar
el PR antes de integrarlos en main. Los JSON de las consultas previas se
conservan como fotografías históricas del momento de cada verificación,
incluido el estado de publicación observado entonces.

Próximos pasos:

1. Preparar y aprobar la propuesta de implementación de HU15 / AARI-170 para
   Talía; coordinar la base HU21 y autorización HU16 con Tobías.
2. Acordar estados, payloads, eventos, intentos, permisos y migraciones antes
   de integrar trabajo paralelo.
3. Comprobar temprano la viabilidad de WhatsApp sin pago/tarjeta y su entorno
   HTTPS de prueba, con autorización para cualquier llamada externa.
4. Registrar avances y trabajo real por jornada, preservando la línea base.
5. Revisar la documentación mediante PR, completar el campo objetivo del
   Sprint desde Jira y resolver la disponibilidad de bloques para incorporar
   el acta completa a Notion.

## 11. Ejecución — Sprint 4

Esta sección y Jira se actualizarán al completar cada implementación. No se
implementó código ni se consumieron Gemini, Supabase, WhatsApp o SMTP durante
la carga de esta planificación.

Cada resumen incluirá HU/subtareas, rama/commit/PR, qué se implementó,
decisiones, pruebas con resultados, límites o pendientes y horas reales.
Iniciar el Sprint no autoriza implementar todas las HU sin sus propuestas
y aprobaciones individuales.
