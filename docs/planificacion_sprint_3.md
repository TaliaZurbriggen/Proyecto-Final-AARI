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
