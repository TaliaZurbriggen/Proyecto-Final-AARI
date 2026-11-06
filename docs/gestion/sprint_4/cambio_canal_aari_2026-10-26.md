# SC-2026-10-26 — Canal AARI + correo para proveedores

> Las secciones 1–9 y el encabezado fechado el 26/10 conservan el registro
> original de la decisión. Para el estado vigente, consultar la sección 10,
> incorporada el 06/11/2026. No se retrodató su aceptación ni la ejecución.

**Fecha real:** 26/10/2026, Argentina. **Estado:** cambio de producto y planificación
aprobado por Talía; implementación y aceptación todavía pendientes.

**Control:** [AARI-346](https://taliazurbriggen.atlassian.net/browse/AARI-346).
**Origen:** propuesta comunicada por Talía de habilitar un perfil del proveedor
y mantener la conversación dentro de AARI, avisando por correo. Talía aprobó
crear ambas HU, asignárselas e incorporarlas al Sprint 4. No se atribuye una
aprobación formal a Tobías, Oikos o la cátedra sin constancia. Es un registro
asíncrono: no se inventa una reunión, duración ni carga de horas.

## 1. Problema, evidencia y valor que se conserva

La dependencia de APIs externas ya figuraba en el registro de riesgos; la
planning también advertía la viabilidad de WhatsApp. Lo que se materializó fue
la restricción concreta de Meta, no un riesgo totalmente inexistente en el plan.
La última evidencia disponible del 25/10 mantiene el bloqueo y el error real
131031 del intento de envío. No se hizo una nueva consulta ni se afirma un
desbloqueo el 26/10. Las respuestas automáticas de soporte no acreditan revisión
humana ni una fecha de solución.

Se mantiene el Sprint Goal: avanzar desde el reclamo clasificado y autorizado
hasta proveedor seleccionado y **Visita programada** con contexto y trazabilidad.
No equivale a reparación finalizada, que pertenece a HU25. Se cambia el canal
para no depender de la habilitación de Meta en el recorrido principal.

## 2. Decisión y alternativas (ADR-2026-10-26)

| Alternativa | Evaluación | Decisión |
| --- | --- | --- |
| Esperar la habilitación oficial de Meta | Aprovecha el canal previsto, pero sin fecha confirmada y con dependencia externa bloqueante | Diferida; conservar evidencia y trabajo |
| Telegram | Posibilita automatización, pero obliga al proveedor a adoptar otra aplicación | No elegida como canal principal |
| Cuenta y comunicación en AARI + correo | Control del flujo, datos y permisos; exige nuevo acceso/UI, correo y despliegue | Aprobada por Talía |

No se adopta automatización no oficial de WhatsApp Web, no se activan pagos ni
tarjetas y no se elimina el portfolio o recursos de Meta. El correo es un aviso
con enlace a una pantalla autenticada, no la fuente de verdad del proceso.

El proveedor fidelizado accede sólo a sus solicitudes/conversaciones. La
inmobiliaria conserva gestión y supervisión. La matriz exacta de participación
de responsable e inquilino por etapa se acuerda antes de programar permisos.
Un candidato nunca accede a presupuestos, conversaciones o datos de competidores.

Presupuesto y fecha/hora se cargan con **acciones estructuradas y confirmadas**.
Los mensajes permiten aclaraciones, pero no seleccionan proveedor, autorizan
gastos ni programan visitas por sí solos. El agente sigue coordinando pasos,
eventos y vencimientos. No se promete un chatbot autónomo de interpretación libre.

## 3. Cambio de requisitos y trazabilidad

| Elemento | Tratamiento aprobado |
| --- | --- |
| HU32 / [AARI-347](https://taliazurbriggen.atlassian.net/browse/AARI-347) | Nueva: identidad, activación, acceso y solicitudes propias del proveedor; 6 HH, Talía |
| HU33 / [AARI-348](https://taliazurbriggen.atlassian.net/browse/AARI-348) | Nueva: conversación privada por solicitud/intento; 12 HH, Talía |
| HU19 / [AARI-206](https://taliazurbriggen.atlassian.net/browse/AARI-206) | Sigue En curso: solicitar/recibir presupuestos mediante AARI y avisar por correo |
| HU20 / [AARI-220](https://taliazurbriggen.atlassian.net/browse/AARI-220) | Conserva comparación y selección; aviso al seleccionado por AARI/correo |
| HU23 / [AARI-250](https://taliazurbriggen.atlassian.net/browse/AARI-250) | Conserva disponibilidad, confirmación y recordatorios; comunicación en AARI/correo |
| HU24 / [AARI-262](https://taliazurbriggen.atlassian.net/browse/AARI-262) | Conserva cancelación/reelección; invalida acciones tardías y conserva conversación |
| [AARI-345](https://taliazurbriggen.atlassian.net/browse/AARI-345) | Integra identidades/eventos nuevos; mantiene los cinco recorridos reales pendientes de HU21 |
| HU18 | Sin obligación nueva de registrar al proveedor externo; conserva su circuito |
| [AARI-338](https://taliazurbriggen.atlassian.net/browse/AARI-338) | Dependencia de acceso remoto; sigue fuera del Sprint y sin nueva estimación |

Las descripciones de Jira conservan el alcance anterior y una actualización
fechada. Las subtareas de canal se adaptan sin borrar horas ni cambiar las
estimaciones históricas. AARI-208 y AARI-211 quedan rotuladas **Diferido** y
`canal-meta-diferido`; mantienen su estado técnico anterior por trazabilidad,
no porque se siga ejecutando Meta. AARI-217 identifica su mock como evidencia
del canal anterior. No se presentan como implementación del portal.

**No cerrar HU19 por dejar de usar WhatsApp.** Antes del cierre deberá acordarse
si las tareas exclusivas de Meta se trasladan a seguimiento futuro o se cancelan
con motivo visible, sin contarlas como entrega completada. HU19 queda lista
únicamente al satisfacer los criterios del nuevo recorrido y la revisión.

## 4. Desglose aprobado y verificado en Jira

Ambas HU y sus 14 subtareas están en Sprint 4 (ID 73), asignadas a Talía y
**Por hacer**. Crear el backlog no equivale a iniciar programación.

### HU32 — 6 HH

Como proveedor habilitado, quiero acceder a mi espacio en AARI para consultar
y responder mis solicitudes sin depender de WhatsApp.

| Subtarea | Entrega | Minutos |
| --- | --- | ---: |
| AARI-349 | Identidad y vínculo seguro con el padrón de proveedores | 60 |
| AARI-350 | Activación e inicio de sesión | 60 |
| AARI-351 | Permisos y bloqueo de cuenta inactiva | 30 |
| AARI-352 | Habilitación desde gestión administrativa | 45 |
| AARI-354 | Portal responsive con solicitudes propias | 45 |
| AARI-353 | Pruebas de acceso, documentación y revisión | 120 |
| **Total** | | **360 = 6 HH** |

Reutilizar autenticación y padrón; no crear registro público libre, directorio
duplicado ni múltiples empleados por proveedor en este alcance. Validar cuenta
inactiva, enlace expirado, reintento, identidad vinculada y acceso a datos ajenos.
El detalle de activación/vigencia se aprueba en la propuesta técnica.

### HU33 — 12 HH

Como participante autorizado, quiero intercambiar mensajes y consultar el
historial de una solicitud para resolver dudas y dar seguimiento a la coordinación.

| Subtarea | Entrega | Minutos |
| --- | --- | ---: |
| AARI-355 | Matriz de participantes y contratos de conversación | 60 |
| AARI-357 | Modelo privado e historial | 75 |
| AARI-356 | API con permisos, paginación e idempotencia | 90 |
| AARI-358 | Interfaz responsive por solicitud | 135 |
| AARI-360 | No leídos y actualización | 60 |
| AARI-359 | Eventos del agente y contexto por intento | 90 |
| AARI-361 | Aislamiento, concurrencia y recuperación | 150 |
| AARI-362 | Documentación, QA y revisión | 60 |
| **Total** | | **720 = 12 HH** |

Talía elevó la estimación propuesta de 8 a 12 HH, manteniendo alcance: mayor
reserva para integración, seguridad y pruebas. Conversación privada por
reclamo/proveedor/solicitud/intento, sólo texto, autor y hora, origen humano o
agente, orden estable, no leídos y recuperación durable. Cancelar conserva
historial pero invalida acciones viejas. Sin audios, videollamadas, nuevos
adjuntos, presencia/"escribiendo", correo por cada mensaje ni chatbot general.

HU32 habilita HU33 y el acceso de HU19. HU19 produce presupuestos para HU20;
la selección habilita HU23. HU33 se integra a HU23 y al seguimiento AARI-345.
Los enlaces de dependencia indican prerequisitos de entrega, no impiden
desarrollar contratos o pruebas con dobles en paralelo.

## 5. Impacto sobre tiempo, capacidad y línea base

| Concepto | HH | Interpretación |
| --- | ---: | --- |
| Línea base original de nueve HU | 46 | Conservar: Talía 22, Tobías 24 |
| Nuevas HU32 + HU33 | 18 | Talía; 6 + 12 |
| Agregado bruto | 64 | Talía 40, Tobías 24; no es restante ni previsión final |

Las estimaciones de las HU nuevas están sólo en subtareas, sin duplicarlas en
el padre. Sus puntos expresan HH según convención académica. No se corrigen
puntos ni estimaciones originales para aparentar mejor desempeño.

HU19 conserva su línea base de 7 HH; a la consulta del 26/10 suma 9 HH reales
en subtareas. No todo es demora de Meta ni trabajo perdido: hay núcleo de
solicitudes, presupuestos, auditoría, plazos y pruebas reutilizable. El tiempo
calendario de espera no se convierte automáticamente en horas trabajadas.

**Pendiente:** evaluar esfuerzo restante de adaptación, trabajo reutilizable,
capacidad diaria real hasta el cierre y elementos a postergar. Las 18 HH nuevas
no absorben tácitamente toda la adaptación o el despliegue. Incorporación al
Sprint autorizada no equivale a capacidad demostrada ni garantiza el alcance.
No cambiar las fechas configuradas (09/10–06/11), extender el Sprint para ocultar
desvíos ni modificar fechas reales en burndown/burnup. Reuniones se contabilizan
aparte; no se registra un nuevo worklog por crear esta documentación.

## 6. Gestión adaptada de PMBOK y Scrum

Este procedimiento es una adaptación del equipo, no una afirmación de que
PMBOK exige estos nombres, formularios o un comité formal para este proyecto.

1. **Registrar el problema materializado:** evidencia de restricción de Meta,
   efecto sobre HU19 y dependencias, responsables y estado conocido; separar
   riesgo futuro de impedimento actual. Control AARI-346.
2. **Analizar alternativas e impacto:** valor de negocio, costo cero/sin tarjeta,
   adopción, seguridad, tiempo, calidad, dependencias y nuevo alcance. Conservar
   la línea base y cuantificar el cambio, sin reescribir el plan original.
3. **Registrar la decisión y su autoridad:** Talía aprobó el cambio y Sprint 4.
   Queda pendiente constancia de validación con responsables de producto/Oikos
   y cátedra si el canal original es requisito de aceptación. La idea comunicada
   de Tobías no se convierte en una aprobación formal ficticia.
4. **Adaptar Product Backlog y Sprint Backlog:** HU32/HU33, criterios versionados
   de las HU afectadas, dependencias y tareas Meta diferidas. Mantener el Goal y
   calidad. Contrastar con capacidad y acordar recortes/reordenamiento con quien
   ejerza Product Owner y desarrolladores; no añadir alcance silenciosamente.
5. **Ejecutar con control:** propuesta técnica y aprobación por HU, rama desde
   main vigente, pruebas aisladas, revisión cruzada y evidencia diferenciada de
   mock/local/real. No continuar soporte Meta como trabajo crítico del canal AARI.
6. **Monitorear y comunicar:** registrar horas efectivas por tarea, cambios de
   previsión sin reemplazar línea base, bloqueos y decisiones diarias. Priorizar
   un recorrido integrado temprano sobre pantallas aisladas.
7. **Validar y cerrar:** review del incremento real, criterios de aceptación y
   límites; cerrar HU sólo después de revisión/merge y autorización. En retro,
   evaluar prueba temprana de dependencias y criterio de abandono de canales.

Referencias de encuadre, sin copiar formularios: [Scrum Guide — The Sprint](https://scrumguides.org/scrum-guide.html#the-sprint),
[PMI — Tailoring](https://www.pmi.org/-/media/pmi/documents/public/pdf/pmbok-standards/pmi-tailoring.pdf)
y [PMI — Risks vs. issues](https://www.pmi.org/learning/library/risks-vs-issues-project-failure-2328).

## 7. Riesgos y respuesta propuesta

| Riesgo o problema | Respuesta / evidencia de control | Responsable de seguimiento |
| --- | --- | --- |
| Meta restringido (problema materializado) | Diferir canal; preservar evidencia sin reclamar solución ni seguir reintentando como requisito principal | Talía / AARI-346 |
| Sobrecarga del Sprint y reparto 40/24 HH | Revisar capacidad/restante; priorizar o postergar explícitamente; conservar línea base | Talía y Tobías, acuerdo pendiente |
| Correos fallidos, spam o tardíos | AARI como fuente de verdad; avisos mínimos, auditoría, reintentos y alerta; comprobar entrega real autorizada | HU19 e integración |
| Proveedor sin cuenta activa o poca adopción | Activación guiada, UI móvil y pendientes visibles; no confundir falta de acceso con silencio | HU32 / Talía |
| Filtración entre proveedores o intentos | Permisos backend, aislamiento, mínimos datos en mail, pruebas negativas y de concurrencia | HU32/HU33 e integración |
| Uso remoto sin despliegue | Resolver planificación AARI-338 aparte; localhost no acredita acceso de un proveedor externo | Acuerdo de equipo pendiente |
| Coordinación duplicada o respuesta vieja | Identificadores de intento, acciones idempotentes, historial y rechazo tras cancelación | HU19/HU23/HU24/AARI-345 |
| Cambio de canal no aceptado por interesados | Validar y registrar alcance/criterios con responsables pertinentes antes de afirmar aceptación final | Talía / AARI-346 |

No se asignan probabilidades o severidades numéricas sin evaluación del equipo.

## 8. Pendientes técnicos antes de implementar

- Aprobar matriz exacta de acceso por etapa y qué datos ve cada candidato.
- Definir activación, email único/vínculo, expiración de enlaces y baja segura.
- Ratificar el inicio de las 24 h: propuesta desde publicación a cuenta activa,
  no desde apertura del mail; distinguir fallos de aviso, inactividad y no respuesta.
- Acordar payloads/eventos/versiones con HU20/HU23/HU24 y AARI-345.
- Definir retención del historial, actualización de mensajes y recuperación.
- Confirmar proveedor/condiciones de correo y entorno accesible sin tarjeta/costo.
- Acordar disposición administrativa de tareas Meta antes del cierre de HU19.
- Reconciliar capacidad y previsión de adaptación; no iniciar toda la carga por
  la mera creación de tickets.

## 9. Validación y cierre de esta gestión

Planificado/creado: HU32/HU33, sus 14 subtareas, control de cambio y criterios
versionados de las HU afectadas. Se verifican responsable, Sprint, estado y suma
de estimaciones; no hay código de las nuevas HU ni pruebas funcionales nuevas.

Validación del 26/10: 14 subtareas presentes, todas de Talía, Por hacer y en el
Sprint activo; 6/12 HH originales y restantes, cero horas reales y sin duplicar
estimaciones en los padres. Se compararon 43 subtareas históricas con la
fotografía de reestimación del 08/10: cero diferencias en estimación original
y puntos. HU19 sigue En curso, el despliegue sigue fuera del Sprint y las
dependencias de Jira quedaron verificadas en su dirección correcta.
`git diff --check` aprobado; enlaces locales presentes y revisión de los tres
archivos sin patrones de credenciales. No se ejecutaron suites funcionales,
API externas ni migraciones porque este cambio es documental.

El código local previo de HU19 se conserva en su rama independiente
`codex/AARI-206-solicitudes-presupuesto`; no se copia a esta rama documental ni
se afirma que ya está en main. El trabajo exclusivo de Meta no se elimina.
Esta documentación parte de main `19d06fa7` en
`codex/cambio-canal-proveedores`, sin commit ni push autorizados.

**Publicación en Notion:** el límite gratuito de bloques rechazó la creación
del ADR/acta completos, sin crearlos parcialmente. Sí se actualizaron los
resúmenes existentes del [Hub](https://app.notion.com/p/3a0f9f68a0c180cfa9d8ef06ef7da616),
[Riesgos](https://app.notion.com/p/3a6f9f68a0c181b6928bd356d0a20c50),
[ADR](https://app.notion.com/p/3a6f9f68a0c181e793f4dcfe66867b4e) y
[Ceremonias](https://app.notion.com/p/3a6f9f68a0c181eabecfc113a214e45c),
con referencias al detalle en Jira y este archivo, sin borrar el historial ni
cambiar el plan de Notion. La publicación completa allí queda pendiente.

Próxima entrega: propuesta técnica de HU32 con archivos, decisiones, dependencias,
pruebas y riesgos; aprobación antes de tocar código. Luego HU33 y adaptación
integrada del flujo. La creación en Jira o una demo con dobles no acredita esas
entregas ni habilita su cierre.

## 10. Conciliación de entrega y preparación del cierre — 06/11/2026

**Estado actual:** implementación integrada en main; control AARI-346 En curso.
Talía autorizó actualizar documentación y seguimiento en este chat. Esta
autorización no se registra como aceptación de Oikos/cátedra ni como una reunión.
Durante esta actualización Talía ratificó que ella y Tobías aceptaron AARI +
correo por no haber podido completar la integración con Meta. Se registra esa
confirmación del equipo, sin atribuir una aceptación externa no documentada.
La base de esta revisión es main `9d38ca04698dec10a3c26478a983e7958c105865`.
La rama documental nueva es `codex/AARI-346-cierre-canal`; preserva intactos los
tres archivos locales de `codex/cambio-canal-proveedores`.

### 10.1. Evidencia y requisitos satisfechos

Se verificaron los estados actuales de Jira y los merges de GitHub; no se
deduce entrega sólo de la creación de tickets.

| Entrega | Jira actual | Evidencia integrada |
| --- | --- | --- |
| Acceso y activación del proveedor HU32 | AARI-347 Listo | [PR #37](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/37), base del portal completada con HU19 |
| Solicitudes y presupuestos en AARI HU19 | AARI-206 Listo | [PR #38](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/38) |
| Conversación privada HU33 | AARI-348 Listo | [PR #39](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/39) |
| Comparación y selección HU20 | AARI-220 Listo | [PR #41](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/41) |
| Coordinación hasta Visita programada HU23 | AARI-250 Listo | [PR #42](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/42) |
| Cancelación y reelección HU24 | AARI-262 Listo | [PR #43](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/43) |
| Integración terminal y multi-turno HU21 | AARI-345 Listo | [PR #44](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/44), merge `9d38ca0` |
| Configuración/webhook exclusivos de WhatsApp | AARI-208 y AARI-211 Cancelada | Disposición autorizada el 28/10, comentario de AARI-346; no cuentan como WhatsApp implementado |
| Entorno remoto compartido | AARI-338 Por hacer | Fuera del Sprint por acuerdo previo; no se presenta localhost como despliegue |

HU15, HU16, HU17, HU18 y HU21 base también figuran Listo. El alcance llega a
Visita programada o derivación externa, no a reparación resuelta/HU25.
El bloqueo de Meta se mitigó sustituyendo el canal principal: no se afirma
que Meta haya habilitado la cuenta ni que se haya reparado WhatsApp.

La matriz técnica ya está definida en las entregas aprobadas:

- Sólo el proveedor invitado y activado accede a sus solicitudes; no hay alta
  pública ni lectura de datos de competidores.
- En presupuesto, el proveedor abre consultas técnicas y las cierra al terminar.
  Mensajes no elige presupuesto, no autoriza gasto ni confirma una visita.
- El responsable del gasto elige el presupuesto; la disponibilidad de visita
  la aporta el inquilino, también cuando paga el propietario.
- Si no sirve ninguna opción, se habilita negociación proveedor–inquilino.
  La otra parte confirma una propuesta estructurada; administración no sustituye
  a los participantes ni interviene como autor en el chat.
- Las 24 h empiezan desde la publicación durable para una cuenta activa,
  no desde la apertura de un email. Fallo del aviso y silencio son distintos.
  Historial, reintentos, permisos y rechazo de acciones obsoletas quedan auditados.

Las pruebas SMTP reales previas de HU32 y HU19 documentan recepción confirmada
por Talía; no prueban todos los futuros avisos ni el canal desplegado. En esta
actualización no se enviaron correos ni se consumieron Gemini o Meta.

### 10.2. Balance observado, no reestimación retrospectiva

La línea base de nueve HU permanece en **46 HH**; HU32 y HU33 agregaron
**18 HH**, dando **64 HH de alcance estimado**. Las 30 HH fueron la capacidad
orientativa inicial, no el compromiso final. El traslado de integración a
AARI-345 no agrega nuevamente la previsión ya incluida en HU21.

| Elemento | Tiempo agregado registrado en Jira al 06/11 |
| --- | ---: |
| HU15 / AARI-170 | 4 h 30 min |
| HU16 / AARI-180 | 6 h 40 min |
| HU17 / AARI-191 | 5 h |
| HU18 / AARI-199 | 4 h 50 min |
| HU19 / AARI-206 | 13 h 15 min |
| HU20 / AARI-220 | 6 h 10 min |
| HU21 base / AARI-229 | 6 h 30 min |
| HU23 / AARI-250 | 4 h 50 min |
| HU24 / AARI-262 | 6 h 15 min |
| HU32 / AARI-347 | 6 h |
| HU33 / AARI-348 | 12 h |
| Integración / AARI-345 | 2 h 35 min |
| **Total implementación, revisión y validación registradas** | **78 h 35 min** |

La diferencia contra las 64 HH es **14 h 35 min**. Es una conciliación a la
fecha, no evidencia de que se haya acordado esa capacidad antes de trabajar.
Se sumó `aggregatetimespent` de cada padre de alcance una sola vez; no se
volvieron a sumar sus subtareas. AARI-345 contiene subtareas trasladadas, fuera
del agregado actual de AARI-229. Las 7 h 10 min de AARI-208/AARI-211 se conservan
**dentro** de HU19, no se suman otra vez ni se borran por cancelar el canal.
No se atribuye todo ese esfuerzo a un integrante ni todo el desvío a Meta.

Reuniones aparte: la planning conserva sus 4 HH históricas. No se inventa
duración de Review/Retrospectiva ni se cargan nuevas horas por esta revisión.
Los restantes que Jira aún muestre en incidencias terminales no se trataron
como trabajo abierto ni se pusieron en cero sin autorización. No se cambiaron
fechas, puntos, estimaciones, responsables, worklogs ni el estado del Sprint.

### 10.3. Validación integrada y límites de evidencia

La entrega AARI-345 registra 1257 pruebas backend aprobadas/632 omitidas y
90 PostgreSQL locales aprobadas, con módulos de negocio reales, recuperación,
cancelación/reelección y sincronización terminal. La evidencia histórica se
conserva en [la guía de integración](../../hu21_integracion_end_to_end.md).
Las cuatro pruebas Supabase de HU23 acreditan el recorrido HU20→HU23 con
cuentas ficticias, login/cookies reales y rollback, no toda la nueva integración
AARI-345 ni una instalación remota.

La repetición local final aprobó **102 pruebas con psycopg 3** (133,01 s) y
**120 con psycopg2** (124,76 s, incluye 18 pruebas adicionales de reglas/API).
No sumar ambos totales: las suites y la regresión cruzada se solapan. Usa
main `9d38ca0` más el hotfix aprobado de esta rama, PostgreSQL descartable y cuentas ficticias,
sin cargar .env, ejecutar workers generales o contactar servicios externos.
No equivale a login manual de todos los roles, envío SMTP, QA compartido
ni comprobación del esquema actual de Supabase.

### 10.4. Pendientes con destino explícito

| Pendiente | Seguimiento y condición de resolución |
| --- | --- |
| Aceptación del cambio de canal | Talía confirmó el 06/11 el acuerdo de ella y Tobías. No se afirma conformidad de Oikos/cátedra; si fuese exigida para la entrega académica, deberá registrarse aparte |
| Validación compartida y operación | Talía confirmó el 06/11 que el despliegue en la nube se hará en próximos sprints mediante AARI-338. Allí se conserva el entorno accesible, HTTPS, cookies, correo y workers; verificar primero migración HU24 y todas las versiones lectoras HU21. No se incorpora al Sprint ni se estima de nuevo |
| Ensayo de la versión integrada | AARI-346 conserva la verificación de cierre; la prueba local no sustituye el smoke test del entorno compartido. No activar workers que recorran reclamos reales por esta actualización |
| Capacidad y resultado del alcance | Balance actual documentado, sin atribuir capacidad demostrada al 26/10. Las entregas funcionales están Listo; el despliegue queda expresamente para próximos sprints según confirmación de Talía el 06/11 |
| Review y Retrospectiva | Registrar cuando ocurran, con fecha/duración reales. Este texto prepara evidencia y temas, no es el acta de ceremonias realizadas |
| Publicación documental | Talía autorizó commit, push y PR el 06/11. Resultado de publicación en Jira/PR; revisión cruzada y merge pendientes. Los enlaces al acta no se consideran disponibles en main hasta su integración |

Talía confirmó el 06/11 el destino del despliegue en AARI-338 para próximos
sprints. Su validación remota y puesta en operación quedan allí y no se
presentan como entrega de AARI-346 ni como bloqueo del cierre administrativo
del cambio. No hay servicio de nube, fecha o nuevo responsable técnico elegidos
por esta actualización: es trabajo conjunto según la tarea de despliegue.
Para cerrar AARI-346 restan publicar/revisar esta documentación y el hotfix,
aceptar su evidencia y dar la indicación de cierre. La Review/Retrospectiva
se registrará en el seguimiento del Sprint cuando ocurra; no se afirma realizada
ni se inventan participantes, fecha o duración para cerrar esta gestión.

### 10.5. Checklist conciliado

- [x] Decisión original, alternativas, impedimento y riesgos preservados.
- [x] HU32/HU33 creadas e implementadas, con revisión e integración.
- [x] Requisitos de HU19/20/23/24 y AARI-345 adaptados e integrados.
- [x] Matriz técnica, activación, plazos y manejo de fallo del aviso definidos.
- [x] Tareas exclusivas de Meta canceladas, con sus horas/historia preservadas.
- [x] Evidencia local y balance de esfuerzo recopilados sin reemplazar línea base.
- [x] Ratificación de Talía del acuerdo de ambos integrantes para AARI + correo; sin atribuir aceptación externa.
- [x] Balance de esfuerzo documentado y despliegue remitido a AARI-338 para próximos sprints por confirmación de Talía.
- [ ] Publicar y revisar esta actualización documental.
- [ ] Publicación/revisión del hotfix y aceptación de la verificación integrada con sus límites.

Seguimiento posterior separado: despliegue/QA remota en AARI-338 y ceremonias
reales en el cierre del Sprint. No se marcan realizados ni se cargan horas.

Notion no es requisito ni pendiente de cierre según la guía vigente del
repositorio. Se conserva como hecho histórico el intento del 26/10 y su límite
de bloques, sin exigir una publicación adicional allí. El registro durable de
esta actualización vive en Jira y estos archivos versionables.

### 10.6. Hallazgo de compatibilidad y corrección autorizada

La repetición sobre main `9d38ca0` detectó que la consulta de destinatarios
de cancelación en `coordination_cancellations.py` evalúa `:selected IS NULL`
antes de que PostgreSQL pueda determinar el tipo del parámetro. El segundo
uso con CAST no tipa necesariamente el primer parámetro enviado por psycopg 3.
No es un problema de Meta, SMTP o cuota. Afecta cancelaciones con y sin
proveedor seleccionado cuando SQLAlchemy utiliza ese controlador.

Resultado previo de las cinco suites: con psycopg 3, **71 aprobadas y 19
fallidas** (`AmbiguousParameter`, 106,49 s); con psycopg2, **90 aprobadas**
(110,74 s). Son configuraciones distintas sobre el mismo main, no se borra
una tanda ni se atribuye a servicios externos. Versiones reutilizadas,
coincidentes con los pins declarados para este diagnóstico: psycopg 3.3.6,
psycopg2-binary 2.9.12 y SQLAlchemy 2.0.51. No es una instalación limpia nueva.

Talía autorizó en este chat tipar explícitamente el parámetro UUID y agregar
regresión con ambos controladores, sin cambiar reglas, migraciones o dependencias.
La regresión cubre ordinario/extraordinario, recepción/comparación/selección,
dos proveedores, destinatarios correctos y replay sin duplicados. Antes de
corregir la consulta, sus 12 combinaciones dieron **6 fallidas/6 aprobadas**
(20,91 s), exactamente por el controlador. Después de agregar
`CAST(:selected AS uuid) IS NULL`, las cinco suites completas dieron
**102 aprobadas con psycopg 3** y, agregando reglas/API HU24,
**120 aprobadas con psycopg2**. Las 12 regresiones nuevas pasan en ambas
tandas y verifican directamente ambos controladores; no sumar tandas solapadas.
No acredita publicación ni vuelve a cerrar automáticamente AARI-346 o HU24.

Comando de integración (desde backend, sin .env):

```text
python -m pytest tests/test_coordination_workflow_postgres.py
  tests/test_coordination_postgres.py tests/test_coordination_provider_choice_postgres.py
  tests/test_visits_hu20_integration_postgres.py
  tests/test_coordination_cancellations_visits_postgres.py
  -q -p no:cacheprovider --tb=line
```

Es una sola invocación; los saltos se usan para facilitar la lectura.
La tanda psycopg2 agregó `tests/test_coordination_cancellations.py`. Se utilizó
`AARI_TEST_POSTGRES_URL` con el controlador correspondiente y sólo host local;
`PYTHON_DOTENV_DISABLED=1`, `DATABASE_URL=sqlite:///:memory:` y workers/opt-ins
externos desactivados. No se documentan conexiones privadas. Compilación Python
de los dos archivos modificados correcta. No se cambió frontend ni se le
atribuye una nueva ejecución de lint/build o su suite completa.

Preparación del entorno: un primer intento no pudo acceder a la conexión local
desde el entorno restringido; el siguiente detectó que el PostgreSQL nuevo
no tenía los roles `anon`, `authenticated` y `service_role` que esperan las
migraciones. Se crearon sin LOGIN sólo en ese contenedor temporal y se repitió.
Ninguno de esos intentos se informa como una suite aprobada. La base compartida
no fue consultada ni modificada y no se cargaron valores de archivos .env.
Al terminar se verificaron cero bases de QA restantes y se retiró únicamente
el contenedor temporal creado para esta ejecución; otros contenedores intactos.

### 10.7. Autorización de publicación — 06/11/2026

Talía autorizó hacer commit, subir la rama y crear un PR con contexto para la
revisión de Tobías. La fotografía JSON conserva el estado previo a publicar;
el commit y enlace resultantes se registran en Jira y en la descripción del PR.
Esta autorización no fusiona la rama ni cierra AARI-346. La revisión, el merge
y la indicación posterior de cierre siguen pendientes. No se agregan horas.
