# Sprint Planning — Sprint 3

**Fecha de preparación:** 08/09/2026  
**Participantes:** Talía Zurbriggen y Tobías Gasparotto  
**Duración:** 4 semanas, del 09/09/2026 al 07/10/2026  
**Estado:** Sprint configurado y activo en Jira; alcance y reestimación acordados.

**Seguimiento HU29 (12–13/09/2026):** comenzó su implementación en una rama
desde main. La inmobiliaria administra los PDF; inquilino y propietario solo
consultan sus contratos firmados. No se incorpora firma electrónica ni fecha
de firma manual; la firma queda en el documento. Se mantiene la estimación.
Decisiones, ejecución y pendientes en
[`hu29_gestion_contratos.md`](hu29_gestion_contratos.md).

## Seguimiento verificado — 07/10/2026

La fecha prevista de cierre es el 07/10/2026, pero el Sprint sigue activo en
Jira y mantiene trabajo pendiente. No se cerró el Sprint ni se alteró su alcance.

| Elemento | Estado verificado | Entrega |
| --- | --- | --- |
| HU29 / AARI-318 | HU y subtareas listas | PR #24 mergeado. |
| HU10 / AARI-116 | HU y subtareas listas | PR #25 mergeado. |
| HU12 / AARI-135 | HU y subtareas listas | PR #26 mergeado. |
| HU11 / AARI-125 | HU y nueve subtareas listas el 07/10 | PR #27 aprobado y mergeado el 05/10 (`80afb67`); 1 h 15 min registrados. |
| HU30 / AARI-319 | HU y seis subtareas listas | PR #28 aprobado y mergeado (`439ee3c`). |
| HU13 / AARI-147 | HU y nueve subtareas listas | PR #29 aprobado y mergeado (`69d0ec6`); 2 h 15 min registrados. |
| HU31 / AARI-332 | HU y cinco subtareas En curso, Talía | Rebase sobre `69d0ec6`, conexión a escalados y revalidación completas; acción visible Resolver clasificación incorporada durante la revisión. Continuación autorizada para publicación y revisión del PR. 3h 15m acumuladas, incluidas 1h 15m adicionales autorizadas el 07/10. Sin merge o cierre autorizado. |
| HU14 / AARI-157 | Código integrado; HU todavía En curso en Jira | PR #30 mergeado (`37b179d`); 1 h 40 min registrados. Su cierre administrativo no se modificó durante HU31. |
| Despliegue / AARI-338 | Por hacer, conjunto | Pendiente integración del incremento y definición del servicio. |

## Registro cronológico de ejecución

Los siguientes párrafos conservan las etapas previas de entrega, pruebas y
publicación; la tabla anterior refleja el estado vigente verificado al retomar HU31.

El cierre de HU11 fue autorizado; no se agregaron worklogs ni se modificaron
estados del trabajo pendiente de Talía. `main` local se sincronizó mediante
fast-forward al merge `80afb67`. Detalle del cierre y pruebas en
[`hu11_historial_reclamos.md`](hu11_historial_reclamos.md).

La siguiente historia individual es HU14, con sus **5 HH planificadas**. Sus
dependencias base (HU10 y HU12) están integradas, por lo que la implementación
puede prepararse en paralelo al trabajo de Talía. La persona responsable aprobó
el 07/10 las decisiones de estado de envío, privacidad de notas e integración.
HU y doce subtareas se verificaron En curso. La migración se aplicó al Supabase
AARI de desarrollo el 07/10 con permisos y lecturas de FastAPI verificados, sin
datos de prueba ni correos. La incremental de índice compuesto también fue
autorizada, aplicada y verificada: el aviso de esa FK desapareció de los asesores.
La revalidación funcional posterior al índice pasó con administración, operación
e inquilino en escritorio/móvil y con permisos por API; SMTP fue simulado y el
entorno local descartable se retiró al terminar, sin datos compartidos de prueba.
Evidencia local, validación compartida y pendientes en
[`hu14_derivacion_expensas.md`](hu14_derivacion_expensas.md); no hay nuevos
commit o PR al momento de esa validación inicial. El usuario confirmó y se registraron
**1 h 20 min** en AARI-157 el 07/10 (worklog 10268, una única entrada).
Se validó después un único reporte SMTP real con datos ficticios y el usuario
confirmó su recepción. La combinación temporal con HU13/HU31 pasó 527 pruebas
backend (35 omitidas), 214 frontend, lint/build, flujo manual en navegador y
16 verificaciones API/SQL. Ajustes de integración y expectativa de prueba de
HU13 solo en la copia; no se modificaron ramas reales ni se publicó un PR.
En esa etapa HU13 seguía con PR #29 abierto y HU31 En curso. La integración definitiva y la
activación del botón interno de revisión del Home seguían pendientes de esas
historias. Después, la persona responsable autorizó completar la entrega y
publicar HU14 para revisión. Validación final de la rama real: 387 backend
aprobadas/26 omitidas, 122 frontend, lint/build correctos. El PR de HU14 incluye
solo su desarrollo desde el main vigente y una guía de integración; no incorpora
las historias pendientes de Talía ni implica revisión/merge aprobados.

**Entrega publicada el 07/10:** commit de implementación `734386b` en
`codex/AARI-157-derivacion-expensas` y
[PR #30](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/30)
abierto, no borrador, con Talía solicitada como revisora. AARI-158 a AARI-169
verificadas listas; AARI-157 conserva En curso hasta revisión/integración.
El tiempo registrado sigue en 1 h 20 min, sin nuevas entradas. Notion continúa
bloqueado por el límite de bloques; ejecución y decisiones quedan en el repo.

**Seguimiento HU31 (05/10/2026):** implementación del Home operativo en una
rama independiente desde `main` (`80afb67`). El equipo aprobó navegación en
tarjetas para escritorio y desplegable en móvil. HU13 aún no está integrada;
se acordó avanzar con los contadores y accesos existentes y completar
“Revisar casos” después de su merge, sin apilar las ramas. No se cambia la
estimación ni el compromiso del Sprint. Decisiones, pruebas locales y pendientes:
[`hu31_home_administrador.md`](hu31_home_administrador.md).

**Ampliación aprobada de HU31 (05/10/2026):** durante la revisión se autorizó
agregar filtros en propiedades, propietarios e inquilinos **en la misma rama**,
con búsqueda visible en los listados de personas y paginación conservando
criterios. No se modifican estimaciones ni se registra otra HU. Alcance y pruebas:
[`hu31_filtros_listados.md`](hu31_filtros_listados.md). Sincronización en Notion
pendiente por el límite de bloques del espacio.

**Publicación y tiempo de HU31 (05/10/2026):** la persona responsable aprobó
la revisión visual y autorizó commit/push. Se registraron **2h reales** en
AARI-333 a AARI-337 (10, 40, 35, 15 y 20 min), sin duplicarlas en la HU padre
ni cambiar la estimación original. HU y subtareas continúan en curso hasta
completar la integración y revisión; todavía no se autoriza merge o cierre.

**Continuación HU31 (07/10/2026):** propuesta aprobada tras los merges de HU30
y HU13. Se creó un respaldo recuperable del head anterior y se rebaseó sobre
main `69d0ec6`, conservando Home/filtros y las funcionalidades integradas de
contratos, escalados y expensas. **Revisar casos** abre ahora la cola de HU13;
al regresar el Home vuelve a consultar el resumen. Clasificar reduce pendientes,
no el total de activos ni resuelve la reparación. PostgreSQL/HTTP locales
verifican los tres tipos de gasto con administrador y operador, la auditoría,
el contexto contractual y la ausencia de duplicados. Suite final:
**808 backend aprobadas / 37 omitidas**, **235 frontend aprobadas**, lint/build
correctos. Navegación, teclado, filtros y paginación entre 320 y 1440 px aprobados.
No se tocaron Supabase ni servicios externos; no se consumió cuota. Evidencia en
[`hu31_home_administrador.md`](hu31_home_administrador.md).
La continuación no tiene nuevo commit/push/PR; no se cierra HU31 ni se agregan
worklogs o cambios de estimación sin indicación. Notion sigue pendiente por
el límite de bloques; el repo conserva la documentación.

**Ajuste de usabilidad aprobado (07/10/2026):** se agregó **Resolver clasificación**
en la cola de HU13, dentro de esta misma rama de HU31. Abre el detalle sin mutar
el reclamo; mantiene el enlace del número, los dos roles y el regreso con búsqueda
y página. Usa los estilos compartidos de la skill visual AARI y una acción de
ancho completo en móvil. Frontend completo: **238 passed**; lint y build aprobados.
Chrome aislado verificó teclado, foco, paginación y ausencia de desborde en ambos
roles a 1440, 1024, 901, 900, 768, 390 y 320 px, sin servicios externos.
La comprobación de una foto privada fue externa, separada y explícitamente
autorizada: el proceso backend carecía de la configuración de Storage y devolvía
503; se reinició con variables locales existentes y se verificó la descarga de
una imagen válida. No se cambiaron registros, permisos o archivos de entorno.
No se registra tiempo nuevo ni se publica o cierra la HU sin indicación.

**Revisión final y publicación autorizada (07/10/2026):** la persona responsable
aprobó el resultado visual y pidió revisar y subir los cambios. Se repitieron
backend completo con PostgreSQL local (**808 passed / 37 skipped**), frontend
(**238 passed**), lint, build y el recorrido Home/cola/clasificación/regreso en
Chrome aislado, además de la acción para ambos roles en siete anchos. Sin APIs
externas en esta revisión final. La base de QA quedó sin bases de prueba y se
retiró únicamente su contenedor descartable, conservando la vista del usuario.
Se confirmó y registró **1h 15m adicional**: AARI-333 20m, AARI-334 30m,
AARI-335 15m, AARI-336 5m y AARI-337 5m. El agregado de Jira es **3h 15m**;
la HU padre no tiene un worklog duplicado y se mantienen las estimaciones
originales. La mayor asignación corresponde a pruebas e integración; el
reparto es orientativo, no una medición automática por subtarea.
Se autoriza commit/push de la continuación; revisión del PR y merge pendientes.
HU y subtareas siguen En curso. Notion continúa pendiente por el límite de
bloques. Detalle y worklogs en [`hu31_home_administrador.md`](hu31_home_administrador.md).

## Punto de partida

Durante el Sprint 2 se completaron ocho historias de usuario y se registraron **22 h 20 min** de trabajo. El alcance quedó terminado casi dos semanas antes del cierre previsto. La estimación original de 190 HH no representó la duración real de las implementaciones, por lo que el equipo acordó reestimar el Sprint 3 utilizando:

- El tiempo real observado en las historias del Sprint 2.
- La complejidad relativa de cada nuevo alcance.
- Las dependencias entre historias.
- La incertidumbre adicional de OCR, Gemini, notificaciones y despliegue.
- Un margen para integración, revisiones y correcciones.

La capacidad teórica proyectada para cuatro semanas se ubica aproximadamente entre **40 y 44 HH**. Se comprometen **39 HH**, con un margen acotado que deberá protegerse evitando ampliar el alcance durante el Sprint.

## Sprint Goal

Consolidar el flujo posterior al alta de un reclamo, incorporando información contractual revisada, trazabilidad, notificaciones al responsable, resolución humana de casos escalados y derivación de expensas, y disponer de un entorno compartido en la nube para validar y demostrar el incremento.

## Historias comprometidas y reestimación

| Jira | Historia | Estimación original | Reestimación Sprint 3 | Responsable |
|---|---|---:|---:|---|
| AARI-318 | HU29 — Gestión de contratos de alquiler | 3 HH | 3 HH | Talía |
| AARI-319 | HU30 — Extracción automática y revisión de cláusulas | 4 HH | 5 HH | Talía |
| AARI-116 | HU10 — Actualizaciones del estado del reclamo | 23 HH | 5 HH | Tobías |
| AARI-125 | HU11 — Historial de reclamos de una propiedad | 26 HH | 3 HH | Tobías |
| AARI-135 | HU12 — Notificación al actor responsable | 25 HH | 5 HH | Tobías |
| AARI-147 | HU13 — Resolución de casos escalados | 26 HH | 5 HH | Talía |
| AARI-157 | HU14 — Notificación y derivación de expensas | 30 HH | 5 HH | Tobías |
| AARI-332 | HU31 — Home del administrador | 4 HH | 4 HH | Talía |
| AARI-338 | Tarea técnica — Despliegue en la nube | 4 HH | 4 HH | Trabajo conjunto |
|  | **Total** | **145 HH** | **39 HH** |  |

La tarea AARI-338 fue creada en el Product Backlog el 08/09/2026 con cinco subtareas que suman 4 HH. Como es un elemento nuevo, su estimación inicial y su reestimación coinciden.

## Distribución del trabajo

### Talía — 19 HH

- AARI-318 — Gestión de contratos: **3 HH**.
- AARI-319 — Extracción y revisión de cláusulas: **5 HH**.
- AARI-147 — Resolución de casos escalados: **5 HH**.
- AARI-332 — Home del administrador: **4 HH**.
- Participación en el despliegue: **2 HH**.

Talía concentra el circuito contractual, su integración con el clasificador, la resolución manual de escalados y el Home administrativo. La combinación incluye dos historias de complejidad alta y dos de complejidad media.

### Tobías — 20 HH

- AARI-116 — Actualizaciones del reclamo: **5 HH**.
- AARI-125 — Historial de reclamos: **3 HH**.
- AARI-135 — Notificación al actor responsable: **5 HH**.
- AARI-157 — Derivación de expensas: **5 HH**.
- Participación en el despliegue: **2 HH**.

Tobías concentra la infraestructura de notificaciones y sus reutilizaciones posteriores, además de la trazabilidad para el administrador. Aunque contiene tres historias relacionadas, la reutilización del servicio de notificaciones evita implementar la misma lógica varias veces.

La diferencia es de **1 HH** y ambos integrantes tienen historias con dificultad técnica alta, trabajo de frontend y backend, pruebas e integración.

## Secuencia prevista

### Semana 1 — Bases del Sprint

- Talía: AARI-318 — Gestión de contratos.
- Tobías: AARI-116 — Infraestructura y actualizaciones de estado.
- Trabajo conjunto: definir la alternativa de despliegue, costo, variables de entorno y criterios de seguridad.

### Semana 2 — Contexto y trazabilidad

- Talía: AARI-319 — Extracción y revisión de cláusulas, luego de AARI-318.
- Tobías: AARI-135 — Notificación al actor responsable, reutilizando AARI-116.

### Semana 3 — Intervención operativa

- Talía: AARI-147 — Cola y resolución de casos escalados.
- Tobías: AARI-157 — Derivación de expensas, reutilizando la infraestructura de notificaciones.

### Semana 4 — Experiencia integrada y cierre

- Talía: AARI-332 — Home del administrador.
- Tobías: AARI-125 — Historial de reclamos.
- Trabajo conjunto: despliegue, pruebas integrales, revisión responsive, documentación y correcciones.

## Dependencias y acuerdos de alcance

- AARI-319 comienza después de disponer del modelo contractual de AARI-318.
- AARI-135 reutiliza la infraestructura definida en AARI-116.
- AARI-157 reutiliza AARI-116 y AARI-135 para evitar servicios y plantillas duplicados.
- AARI-147 puede avanzar en paralelo con el circuito de notificaciones porque utiliza los estados de escalado ya generados por el clasificador.
- AARI-332 se implementa cuando los módulos que enlazará estén estables.
- El despliegue final se realiza con el incremento integrado, aunque la selección del servicio y la preparación de configuración comienzan en la primera semana.
- Para Sprint 3 se propone correo real y una interfaz de WhatsApp desacoplada y simulada en pruebas. La integración real con WhatsApp Business continúa en HU19.
- Los gráficos, tendencias y análisis históricos no forman parte del Home administrativo; corresponden a HU26.

## Historias que quedan fuera del Sprint

Las siguientes historias permanecen priorizadas en el Product Backlog, pero no forman parte del compromiso de 39 HH:

- AARI-170 — HU15: asignación de proveedores candidatos.
- AARI-180 — HU16: autorización o rechazo de gastos extraordinarios.
- AARI-191 — HU17: elección entre proveedor fidelizado o propio.

HU15 queda como primera candidata para el Sprint siguiente porque inicia el módulo de coordinación agéntica una vez consolidado el flujo de reclamos.

## Registro de estimaciones en Jira

Para conservar las tres mediciones sin borrar la información histórica se utiliza el siguiente criterio:

1. **Story point estimate:** conserva la estimación original existente, utilizando la convención académica de 1 punto = 1 HH.
2. **Original estimate de Time Tracking:** registra la reestimación aprobada para el Sprint 3. Aunque Jira denomina al campo “Original estimate”, para el equipo representa la estimación vigente al comenzar este Sprint.
3. **Remaining estimate:** refleja el trabajo que todavía falta durante la ejecución.
4. **Time spent:** se calcula con los worklogs y representa las horas reales.

Las horas se registran en las subtareas para que la suma coincida con la reestimación de cada historia. No se modifican los puntos originales utilizados en las planificaciones anteriores.

El 10/09/2026 se verificó en Jira que las subtareas suman exactamente **39 HH** de estimación original y restante, y que el tiempo trabajado comienza en cero. La distribución proporcional preserva el peso relativo de los story points de cada subtarea.

## Acuerdos de seguimiento

- Cargar los worklogs el mismo día en que se realiza el trabajo.
- Mantener una descripción breve y concreta en cada registro de tiempo.
- Revisar estimación restante y bloqueos al menos una vez por semana.
- Mantener Pull Requests separados por historia y revisarlos antes del merge.
- No incorporar nuevas historias durante el Sprint sin una replanificación explícita.
- Documentar decisiones técnicas y de producto en el repositorio mientras Notion permanezca bloqueado por su límite de bloques.
- Comparar al cierre las 145 HH originales, las 39 HH reestimadas y las horas reales registradas.
