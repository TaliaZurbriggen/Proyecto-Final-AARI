# HU30 / AARI-319 - Propuesta de extracción y revisión de cláusulas

## Estado al 21/09/2026

HU29 está finalizada e integrada en `main`. La rama
`feat/AARI-319-extraccion-clausulas` se actualizó sobre `origin/main` antes de
implementar HU30. La funcionalidad se encuentra implementada y validada
localmente, sin commit ni push: lectura digital/OCR selectivo, trabajo durable,
extracción estructurada, revisión humana, auditoría, interfaz e integración del
contexto confirmado con el clasificador.

Las migraciones 23 y 24 se aplicaron al Supabase compartido de desarrollo el
21/09. No crearon análisis ni consumieron Gemini. Se verificaron RLS y ausencia
de lectura para roles públicos. El análisis externo permanece deshabilitado por
defecto. Todas las validaciones externas usaron exclusivamente la copia
anonimizada y verificada; ningún contrato original fue transmitido.

HU30 está incluida en el Sprint 3 (09/09/2026-07/10/2026), asignada a Talía.
Se mantienen las **5 HH** de estimación vigente, ya cargadas en Time Tracking
de las subtareas. Las descripciones de Jira conservan el texto histórico de 4 HH;
se debe aclarar sin cambiar los puntos originales. También sigue pendiente
corregir el vínculo de bloqueo invertido: HU29 precede a HU30.

## Objetivo y experiencia del usuario

La inmobiliaria solicita el análisis del PDF desde el detalle del contrato.
AARI identifica cláusulas relevantes y muestra el fragmento original, páginas,
apartado, resumen, tema, responsable expresamente indicado y condiciones.
El administrador puede confirmar, editar y confirmar o descartar cada propuesta.
Solo se habilita contexto confirmado para el clasificador.

Flujo propuesto:

1. Seleccionar la versión del PDF y solicitar análisis.
2. Extraer texto localmente, por página; usar OCR donde sea necesario.
3. Preparar el texto que se enviaría a Gemini, con control de privacidad.
4. Analizar con salida estructurada y validarla contra la evidencia de origen.
5. Guardar resultados pendientes y mostrar las incidencias.
6. Revisar y confirmar desde la inmobiliaria.
7. Incorporar al clasificador el contexto contractual aplicable al reclamo.

Las cláusulas confirmadas reflejan una revisión de fidelidad al documento;
no se presume con ello validez jurídica ni aplicabilidad universal a un gasto.

## Base existente aprovechable

- HU29: `contratos`, `contrato_documentos`, `contrato_eventos`, versiones,
  participantes históricos, acceso privado, fechas y restricciones.
- `pypdf` ya es dependencia del backend para validar documentos.
- `ClassificationState` y el prompt vigente admiten `clausulas_contrato`.
  `SqlAlchemyClaimsRepository.get_for_classification()` todavía devuelve `[]`.
- Frontend: detalle de contrato, tokens visuales y componentes compartidos.

## Diseño técnico propuesto

### 1. Extracción local, OCR y unión de texto - AARI-326

Leer el texto digital con `pypdf`. Para páginas escaneadas, renderizar con
`pypdfium2` y aplicar Tesseract local con español. La instalación del motor,
datos de idioma y configuración Windows/Docker forma parte de la implementación.
Controlar tiempos, páginas, memoria y longitud; un truncamiento debe quedar
marcado como incompleto, nunca como análisis completo sin cláusulas.

Mantener la trazabilidad de página, orden de lectura y apartado, incluso cuando
una oración cruza una página. Si el contrato se divide en fragmentos por límites
del modelo, conservar secciones completas cuando sea posible y solapamiento
controlado, con deduplicación posterior y verificación de condiciones.
Normalizar ligaduras (fi/ti/fl) y espacios de extracción sin quitar negaciones,
números, excepciones o referencias. Detectar calidad insuficiente y permitir
reintento; OCR exitoso no garantiza una lectura semánticamente correcta.

### 2. Persistencia, revisión y auditoría - AARI-327

Migración aditiva posterior a la última de main con registros de análisis,
cláusulas y eventos de revisión. RLS y privilegios restringidos como HU29.

Datos propuestos por análisis: ID, documento/version/hash, estado, fechas,
método de lectura por página, versión de extractor/prompt/modelo, incidencias
y completitud. Por cláusula: ID estable, páginas, número/título/apartado,
fragmento original, resumen, tema, responsable o `no_especificado`, condiciones,
referencias cruzadas, confianza del modelo y estado de revisión.

Conservar la propuesta inicial, las correcciones humanas y quién/cuándo revisó.
No sobrescribir confirmaciones si cambia el PDF o se reintenta un análisis.
Impedir trabajos simultáneos duplicados y confirmaciones sobre una versión
desactualizada mediante restricciones y control de revisión.

La ejecución se desacopla de la subida del PDF y conserva su estado en la base.
El mecanismo de ejecución tendrá timeout y recuperación de trabajos interrumpidos
mediante reintento explícito; no se presume una cola durable por usar únicamente
tareas en memoria. No añadir Redis/Celery sin que resulte necesario y se acuerde.

### 3. Extracción estructurada con Gemini - AARI-328

Prompt de extracción separado del de clasificación. Debe adaptarse al significado
de contratos diferentes, sin depender de una inmobiliaria, página, título o
numeración fija. Analizar mantenimiento, reparación, daños, gastos y expensas.
Separar otros temas o contexto de las reglas operativas.

Además del esquema previsto en Jira (texto, resumen, categoría, responsable y
confianza), incluir explícitamente **condiciones, páginas/apartados y referencias**.
No inventar responsables ausentes, no confundir quién avisa/autoriza con quién
paga, ni convertir una eximición en asignación de pago a otra persona.
Cada fragmento citado debe corresponder al texto recibido y a las páginas
declaradas. Una cita existente no basta para validar el resumen: también deben
comprobarse fidelidad, condiciones y revisión humana.

El documento es dato no confiable a efectos de instrucciones: no ejecutar órdenes
que contenga, abrir enlaces ni permitir que altere las reglas de extracción.
Validar salida en el backend. Confianza declarada alta no permite confirmación
automática. No trasladar el umbral del clasificador a esta tarea de extracción.

### 4. Interfaz - AARI-329

Sección "Cláusulas del contrato" dentro del detalle existente, exclusiva de
administración para el análisis y revisión. Mostrar versión y progreso, pendientes,
confirmadas/descartadas, vacío, fallas e incidencias de lectura.
Comparar fragmento con campos editables; preservar condiciones visibles y permitir
abrir el PDF para revisar contexto. La corrección no modifica el archivo firmado.

Aplicar la skill `aari-frontend`, reutilizando `PageContainer`, `PageHeading`,
`Button`, `FormField`, `StatusBadge`, `AlertMessage` y los tokens existentes.
En escritorio, evidencia y revisión pueden mostrarse en columnas; en móvil
se apilan. Mantener foco, etiquetas, controles táctiles y ausencia de scroll
horizontal global. Los participantes conservan consulta/descarga de sus PDFs
según HU29, sin permisos de revisión.

### 5. Integración con LangGraph - AARI-330

Consultar por propiedad e inquilino del reclamo, con fecha de referencia explícita.
Se propone la fecha de creación del reclamo; usar el período contractual
correspondiente, incluida finalización anticipada, y un conjunto confirmado
de la versión documental aplicable. Una renovación no debe cambiar de forma
retroactiva el contexto utilizado por reclamos anteriores.

Registrar los IDs/versiones de las cláusulas empleadas en cada clasificación.
Las cláusulas de otros inquilinos, pendientes, descartadas o sustituidas no se
incorporan por el simple hecho de pertenecer a la misma propiedad. Cambiar el PDF
obliga a revisar el nuevo contexto; no reutilizar silenciosamente aprobaciones.

Mantener las restricciones de la base de conocimiento sobre excepciones
contractuales. Ante ambigüedad o conflicto, aplicar el escalado acordado sin
inferir nuevas reglas de Oikos a partir del contrato de ejemplo. Sin contrato
se conserva el flujo actual; si una regla requiere cláusula y falta, no inventarla.
Una falla al consultar contexto no equivale a verificar que no existe contrato:
debe quedar identificada y tener una salida controlada.

## Privacidad y proveedor

Mantener texto completo y PDF en almacenamiento local/privado autorizado. No
registrar contenidos personales en logs o trazas externas. OCR local no consume
Gemini. La preparación de una copia anonimizada requiere revisión del contenido
enviado: quitar nombres y DNI por regex no garantiza eliminar toda información
identificatoria o confidencial.

La primera prueba externa usaría material sintético o una copia revisada apta
para el servicio. En Gemini sin facturación, las condiciones del proveedor indican
no enviar datos personales, confidenciales o sensibles. Antes de habilitar el
uso con contratos reales se debe acordar una configuración y tratamiento de datos
compatibles. No se infiere esa habilitación a partir de aprobar esta preparación.

Referencias técnicas consultadas:

- [pypdf: extracción y limitaciones de OCR](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
- [Tesseract: formatos de entrada](https://tesseract-ocr.github.io/tessdoc/InputFormats.html).
- [pypdfium2](https://pypdfium2.readthedocs.io/en/stable/).
- [Condiciones Gemini API](https://ai.google.dev/gemini-api/terms).

## Insumos preparados y ajustes derivados del ejemplo 01

El 14/09 se preparó un PDF anonimizado de 13 páginas, manteniendo las divisiones
del original y verificando la conservación del texto no retirado. Se reconstruyó
el PDF con contenido permitido; no se copiaron objetos privados del archivo fuente.
El original no se incorpora al repositorio ni se modifica.

- [PDF anonimizado](../output/pdf/hu30_contrato_anonimizado.pdf).
- [Resultados esperados y 17 controles](evaluaciones/hu30/resultados_esperados_ejemplo_01.md).
- [Verificación mecánica de la copia](../output/pdf/hu30_contrato_anonimizado.verificacion.json).

El ejemplo exige continuidad entre páginas, separación de incisos, diferenciación
de avisos de 24 horas y devolución al final de la locación, y conservación de
posibles tensiones entre obligaciones amplias y condicionadas. Estos hallazgos
refinan los criterios de HU30; no cambian sus estimaciones ni validan normas.

Para evaluar generalización, usar otro contrato de estructura diferente reservado
hasta congelar el prompt. Las variantes del mismo ejemplo no son validación
independiente. No modificar la suite histórica de 80 reclamos para acomodarla a
este contrato; conservarla como referencia del clasificador y agregar pruebas
específicas de contexto contractual por separado.

## Pruebas y resultados - AARI-331

1. PDF digital, escaneado, mixto, ilegible, sin cláusulas y con lectura incompleta.
2. Comparación de extracción con los 17 controles; omisiones, invenciones,
   negaciones, excepciones, referencias, saltos de página y duplicados.
3. Fallas OCR/Gemini, cuota agotada, timeout y respuestas/citas inválidas.
4. Confirmación/edición/descarte, historial, concurrencia y cambio de PDF.
5. Permisos por rol y participante, RLS y ausencia de datos privados en logs.
6. Contrato aplicable por fecha, renovación, finalización, contexto histórico,
   y cláusulas no autorizadas excluidas del grafo.
7. Regresión de clasificación sin contexto contractual y escalado por conflicto.
8. Frontend: estados, responsive y teclado; lint y build.

Resultados al 21/09/2026:

| Validación | Resultado |
|---|---|
| Suite completa backend | **319 aprobadas, 23 omitidas** en la ejecución estándar; las omitidas son integraciones opcionales, incluido OCR real. La corrida OCR autorizada anterior permanece aprobada. |
| Suite completa frontend | **24 archivos y 105 pruebas aprobadas** en ejecución estable con un worker. |
| Calidad frontend | ESLint y build de producción aprobados. |
| PostgreSQL real | Migraciones 20, 23 y 24 presentes; RLS/privilegios correctos. |
| PostgreSQL aislado | Solicitud idempotente, worker, revisión, evidencia, contexto operativo y permisos aprobados en un esquema temporal con `ROLLBACK`. |
| PDF anonimizado | 13/13 páginas digitales, lectura completa y 21.126 caracteres extraídos localmente. |
| Interfaz | Revisión autenticada de escritorio y móvil; panel apilado y ancho global sin overflow. |
| Integración Gemini | V3 evaluada en V01-V04 con una llamada por documento y sin reintentos: 19/23 controles completos, 12/15 críticos y cero alucinaciones aceptadas. V4 quedó congelada y aprobó **20 pruebas locales específicas y 1 OCR opcional omitida**, todavía sin llamadas externas. |
| Formato | `git diff --check` aprobado. |

La prueba OCR real se completó el 21/09 con Tesseract 5.4.0 y el modelo oficial
rápido de español, SHA-256
`6F2E04D02774A18F01BED44B1111F2CD7F3BA7AC9DC4373CD3F898A40EA6B464`.
El motor leyó una página PDF sintética compuesta únicamente por una imagen y
recuperó las expresiones esperadas en español: **1 prueba aprobada**. El paquete
quedó instalado en Windows; el idioma se utilizó desde una carpeta temporal
porque el proceso no tenía permiso para escribir dentro de `Program Files`.

El 21/09 se autorizaron cinco intentos reales con la copia anonimizada. El hash,
la revisión visual y la ausencia de identificadores residuales se validaron antes
de los envíos. Los dos primeros fueron rechazados con `400 INVALID_ARGUMENT` por
el modo `response_json_schema`; la alternativa mediante `function_calling`
conservó la validación final con Pydantic y permitió la ejecución v1. Un primer
intento de v2 se interrumpió al cortarse la conexión local de Windows mientras se
esperaba la respuesta y no generó resultados parciales. El reintento autorizado
finalizó correctamente.

La v1 devolvió 18 propuestas: 14 superaron la comprobación literal y su cobertura
aceptada fue 11/17 controles (64,7%), con 6/7 críticos. La v2 devolvió 20
propuestas: 17 fueron válidas y 3 quedaron preservadas como rechazadas con su
texto, página y motivo. Encontró contenido para los 17 controles; 14/17 (82,4%)
quedaron respaldados por propuestas con evidencia válida y 6/7 críticos fueron
aceptados. Recuperó el control crítico E07, cuya condición cruza las páginas
5-6. E06 quedó propuesto pero rechazado porque Gemini atribuyó a la página 6 un
fragmento que estaba en la 5; E08 sustituyó una palabra y E16 parafraseó el texto
en vez de citarlo literalmente. El validador actuó correctamente al no aceptar
esas tres evidencias.

La etiqueta de uso también requiere revisión humana: E01 y dos disposiciones
ajenas al tratamiento ordinario de reclamos fueron sugeridas como `operativa`.
En la implementación de ese momento, una confirmación conservaba la etiqueta
`operativa` sugerida por el modelo; el administrador podía corregirla antes.
La decisión del 01/10 reemplaza esa política: ahora sólo una edición con
habilitación explícita puede alimentar al clasificador. Los detalles de esas
evaluaciones históricas están en `docs/evaluaciones/hu30/`.

La suite automática usa mocks del proveedor. OCR local se prueba también con
fixtures sintéticas reales; el mock del motor no demuestra que esté instalado.
Pruebas de PostgreSQL/Storage y llamadas reales a Gemini requieren autorización
para esa ejecución. Registrar versión de fuente/prompt/modelo y resultados.
La meta de 85% de HU9 no se traslada automáticamente a HU30; medir cobertura y
fidelidad de extracción con sus propios controles.

## Componentes implementados

- Migraciones 23 y 24 de análisis, cláusulas, evidencia por página, propuestas
  rechazadas, uso en el clasificador y eventos de auditoría.
- Servicios de extracción PDF/OCR, análisis contractual, revisión y acceso a Storage.
- Esquemas, repositorio, worker recuperable y API de cláusulas dentro de `backend/app/`.
- Prompts versionados `prompt_extraccion_clausulas_v1.md`,
  `prompt_extraccion_clausulas_v2.md`, `prompt_extraccion_clausulas_v3.md` y
  `prompt_extraccion_clausulas_v4.md`.
- Consulta de contexto en `backend/app/db/reclamos.py` e integración contractual
  con `backend/app/services/classification_service.py` y el grafo existente.
- Panel y pruebas en `frontend/src/features/contratos/`.
- Requisitos/configuración del backend, instalación Docker y README para OCR.
- Pruebas unitarias, integración PostgreSQL y evidencia en
  `docs/evaluaciones/hu30/`.

## Estimaciones vigentes, sin cambios

| Subtarea | Trabajo | Estimación Sprint 3 |
|---|---|---:|
| AARI-326 | Lectura local y OCR | 1 h 15 min |
| AARI-327 | Modelo y revisión | 35 min |
| AARI-328 | Gemini estructurado | 55 min |
| AARI-329 | Interfaz | 55 min |
| AARI-330 | Integración y privacidad | 40 min |
| AARI-331 | Pruebas | 40 min |
| **Total** | | **5 h** |

La calidad de PDFs/OCR, las ambigüedades y la integración temporal del contexto
son las incertidumbres principales. Registrar el tiempo real sin modificar
retroactivamente la estimación del Sprint.

## Corpus de generalización preparado el 24/09/2026

El prompt v2 quedó congelado mediante hashes de su plantilla y adaptador. Se
prepararon cuatro modelos públicos (dos digitales y dos escaneados), con 23
controles esperados redactados antes de observar nuevas respuestas de Gemini.
El ejemplo 01 permanece como regresión conocida; V01-V04 forman validación y dos
holdouts H01-H02 quedan reservados por Tobías/Oikos.

La preparación inicial no realizó llamadas externas. El 24/09 se autorizaron y
ejecutaron cuatro llamadas, una por V01-V04, sin cambiar el prompt ni repetir
documentos. El ejecutor controla hashes, mantiene omitidos e inválidos en el
denominador y conserva propuestas rechazadas. V2 localizó 22/23 contenidos
(95,7%), pero sólo 13/23 quedaron completos con evidencia aceptable (56,5%); los
críticos completos fueron 7/15 y no hubo alucinaciones aceptadas. No alcanzó los
criterios de 85% completo y 100% crítico. Ver [evaluación consolidada](evaluaciones/hu30/evaluacion_corpus_v2.md).

## Preparación v3 del 24/09/2026

V3 agrega un anclaje local conservador: tolera únicamente diferencias de
formato, exige una coincidencia única en la página y guarda el texto exacto del
PDF. Las palabras cambiadas, paráfrasis, citas breves o repetidas siguen
rechazándose. El prompt también deja en `no_especificado` y `contexto` las
redacciones ambiguas en lugar de resolverlas.

El reprocesamiento local recuperó 2/10 descartes v2. Los otros ocho debían seguir
rechazados: siete contenían elipsis con texto omitido y uno cambiaba palabras.
La suite completa quedó en 317 aprobadas y 23 omitidas. El prompt, adaptador y
anclaje v3 están congelados; V01-V04 pasaron a regresión y H01-H02 siguen
reservados. Ver [preparación v3](evaluaciones/hu30/preparacion_v3.md).

La regresión externa v3 se ejecutó con cuatro llamadas, una por V01-V04 y sin
reintentos. Alcanzó 19/23 controles completos (82,6%), 12/15 críticos completos
(80%) y cero alucinaciones aceptadas. V02 y V03 cumplieron; V01 conservó tres
controles parciales por evidencia no literal y V04 volvió a resolver una sintaxis
ambigua sobre gastos comunes. Ver [evaluación v3](evaluaciones/hu30/evaluacion_corpus_v3.md).

## Documentación y siguiente paso

Según el acuerdo del Sprint 3, conservar documentación en el repositorio mientras
Notion continúe limitado. La implementación y las validaciones quedan locales en
la rama hasta revisar el diff y recibir autorización para commit y push. OCR real,
Supabase y las evaluaciones v2/v3 quedaron validados. V3 mejoró materialmente,
pero no alcanzó 85% general ni 100% crítico. El siguiente paso es proponer una
iteración general sobre evidencia y ambigüedad; H01-H02 permanecen reservados
hasta que la regresión conocida cumpla.

## Preparación v4 del 24/09/2026

V4 separa reglas independientes, pide citas breves y continuas y añade una
revisión gramatical explícita antes de asignar responsables. Cuando una excepción
o conjunción admita dos agrupaciones razonables, exige responsable
`no_especificado`, uso `contexto`, explicación neutral y confianza máxima de 0,6.
Los ejemplos son sintéticos y el anclaje conservador no se flexibiliza.

El manifiesto v4 congela prompt, adaptador y anclaje. La evaluación externa
requiere una nueva autorización específica para V01-V04 y no puede incluir
reintentos automáticos. El preflight de los cuatro documentos y la suite completa
de 319 pruebas quedaron aprobados. Ver [preparación v4](evaluaciones/hu30/preparacion_v4.md).

El primer intento externo de v4 fue bloqueado por Gemini con `429
RESOURCE_EXHAUSTED` al alcanzar el límite gratuito diario de 20 solicitudes por
proyecto y modelo. V01 no produjo archivos y no se reintentó; V02-V04 no fueron
enviados. La regresión deberá reiniciarse desde V01 después del restablecimiento
de cuota y con una nueva autorización.

El 25/09 se intentó continuar con V01 y V02. Ambos recibieron `503 UNAVAILABLE`
por alta demanda y no produjeron resultados; V03-V04 no fueron enviados. La
regresión v4 sigue pendiente de disponibilidad del modelo.

## Decisión posterior del 01/10/2026: activación explícita

Tras el ensayo experimental v5 de V04, se aprobó que las propuestas de IA se
guarden inicialmente como contexto. Confirmar sólo conserva ese contexto;
para que una cláusula aporte al clasificador, administración debe editarla y
elegir expresamente uso `operativa`. Se conserva la propuesta original y la
activación queda auditada. La consulta de reclamos excluye cualquier fila sin
ese evento, incluidas las revisiones históricas que no lo registraron. Ver
[decisión y alcance](evaluaciones/hu30/activacion_explicita_2026-10-01.md).

Esta política de seguridad no mejora retroactivamente las métricas del modelo
ni autoriza utilizar contratos privados con Gemini. H01-H02 siguen reservados.

## Refinamientos experimentales del 02/10/2026

V7 trasladó la materialización de citas y páginas al backend: el modelo propone
el identificador de un tramo y el backend adjunta sus fragmentos completos.
Esto mejora la procedencia, no garantiza que la interpretación sea correcta.
V8 dejó la cláusula ambigua como contexto sin pagador definido, pero en sus
condiciones todavía eligió un alcance de la excepción. Su ensayo V04 dio 4/5
controles completos y 2/3 críticos, sin alcanzar los umbrales.

Se aprobó preparar v9 para mantener la incertidumbre coherente entre todos los
campos, especialmente resumen y condiciones. Conserva el esquema y la evidencia
local, sin reemplazar respuestas del modelo por controles esperados. La suite
local aprobó 385 pruebas, con 23 omitidas, y los cuatro preflights aprobaron sin
llamadas externas. Ver [alcance, pruebas y limitaciones de v9](evaluaciones/hu30/preparacion_v9.md).

Tras la autorización, V04 se ejecutó con v9. La revisión dio 3/5 completos y
1/3 críticos, con dos propuestas no respaldadas: interpretación del alcance
ambiguo y una condición copiada del prompt. No se enviaron V01-V03 porque V04
no cumplió. Ver [ensayo v9](evaluaciones/hu30/evaluacion_v9_v04_2026-10-02.md).

Las versiones experimentales siguen fuera de producción. La regresión completa
y los holdouts continúan pendientes; no se da la HU por terminada por haber
aprobado pruebas con dobles. Preparar un diagnóstico controlado antes de otra
iteración; no se cambian los controles ni los umbrales.

La comparación autorizada v9/V04 con Gemini 3.5 Flash conservó exactamente la
entrada Lite y los controles. Se agregó un ejecutor/manifiesto independiente
y la suite aprobó 402 pruebas, con 23 omitidas. La única invocación terminó
en HTTP 503, sin cláusulas para evaluar y sin reintento manual. El resultado
Lite quedó intacto. Ver [registro de comparación](evaluaciones/hu30/comparacion_v9_flash_2026-10-02.md).
La disponibilidad del servicio sigue siendo una dependencia distinta de los
errores semánticos observados en Lite; este intento no demuestra mejora ni
empeoramiento del modelo Flash.

Después se autorizó un ensayo equivalente con Flash 3.8, también aislado.
La suite completa aprobó 420 pruebas, con 23 omitidas. La única invocación
recibió HTTP 503 sin cláusulas; no se reintentó. Ver [registro 3.8](evaluaciones/hu30/comparacion_v9_flash38_2026-10-02.md).
La entrada y referencia Lite siguen intactas.

Después se autorizó y ejecutó un diagnóstico mínimo sin contratos. Flash 3.8
respondió `OK` tanto con texto simple como con un esquema estructurado de un
campo: dos invocaciones, sin reintentos manuales. Se agregó un ejecutor aislado
con checkpoints y nueve pruebas; suite completa: 429 aprobadas y 23 omitidas.
La inspección local del esquema completo conserva los nueve campos de las
cláusulas, pero no equivale a aceptación real por Gemini. Ver
[diagnóstico, límites y evidencia](evaluaciones/hu30/diagnostico_flash38_minimo_2026-10-02.md).
El 503 de la extracción completa sigue sin causa demostrada.

Se autorizó después una única solicitud con el esquema completo, el mismo
prompt v9 y dos reglas sintéticas (140 caracteres de fuente). También terminó
en HTTP 503, sin propuestas ni reintento manual. El ejecutor aislado valida los
archivos congelados y protege su checkpoint; se agregaron nueve pruebas, con
suite completa de 438 aprobadas y 23 omitidas. Ver
[registro del esquema completo](evaluaciones/hu30/diagnostico_flash38_esquema_completo_2026-10-02.md).
Reducir la fuente no produjo una respuesta; no permite atribuir el error al
esquema ni descartar indisponibilidad.

Después se aprobó la comprobación con instrucciones breves, sin cambiar
fuente, esquema, modelo o método. La petición pasó a 504 caracteres y su
única invocación también recibió HTTP 503. El bloqueo previo de permisos
no ejecutó la API; tras retomar se hizo una sola invocación, sin reintento.
Se agregaron doce pruebas y la suite quedó en 450 aprobadas y 23 omitidas.
Ver [resultado y alternativa estudiada](evaluaciones/hu30/diagnostico_flash38_prompt_breve_2026-10-02.md).
Se propone revisar JSON nativo en un ensayo separado; está soportado por la
biblioteca instalada, pero no validado para este esquema. Se conserva el
antecedente HTTP 400 de Interactions/v4 y se requiere nueva aprobación antes
de implementar o invocar. No se repiten los ensayos actuales, no cambian
producción, controles ni métricas y no se da la HU por terminada.

Ante el pedido de probar otro modelo y la proximidad del cierre del Sprint
el 07/10, se realizó una comparación V04 con Gemini 3.6 Flash. Se usó el
pipeline existente sin editar código; preparación y hashes idénticos al ensayo
v9/Lite, cambiando sólo modelo. También recibió HTTP 503, sin cláusulas y sin
reintento manual. Ver [comparación 3.6](evaluaciones/hu30/comparacion_v9_flash36_2026-10-02.md).
Después se autorizó un único ensayo del contrato público V04 con 3.1
Flash-Lite. Conservó entrada, prompt y esquema y también recibió HTTP 503,
sin propuestas. No hubo reintento manual ni quedan llamadas adicionales
autorizadas. Ver [registro 3.1 y propuesta de continuidad](evaluaciones/hu30/comparacion_v9_flash31lite_2026-10-02.md).

La inspección local posterior, sin Gemini, reconoce las 12 cláusulas de V04,
conserva QUINTA entre las páginas 1 y 2 y reconstruye los 4.709 caracteres
originales. Se propone habilitar ese resultado literal en la pantalla de
revisión, con origen explícito y revisión humana de sus interpretaciones.
El cambio sigue pendiente de aprobación; no sustituye la validación semántica,
no permite activar cláusulas operativas automáticamente y no autoriza cerrar
HU30 ni bajar sus umbrales por la proximidad del cierre del Sprint.

Se aprobó después un diagnóstico directo con el SDK oficial, sin LangChain ni
herramientas, enviando solamente el texto público V04. Se prepararon tres modos
(texto, JSON, esquema nativo), condicionados a respuestas utilizables y con
detención ante errores. La primera solicitud, sin formato impuesto por la API,
recibió HTTP 503 en 14,555 segundos. El transporte verificó una solicitud y cero
reintentos; los modos JSON no se ejecutaron. Esto reproduce el fallo sin el
adaptador anterior, pero no identifica su causa ni valida una sustitución de
producción. Se agregaron 19 pruebas simuladas; la suite completa aprobó 469,
con 23 omitidas y dos advertencias conocidas. Ver
[diagnóstico directo y límites](evaluaciones/hu30/diagnostico_directo_flash38_2026-10-02.md).
Los prompts congelados, evidencia anterior y umbrales permanecen intactos.

## Decisión vigente e implementación — 05/10/2026

Talía aprobó continuar como **extracción asistida con revisión humana obligatoria**
y aplicar la migración aditiva 25 con pruebas aisladas en Supabase. No se rebajaron
los umbrales congelados ni se declaró validada una interpretación autónoma.

El módulo actual `contract_clause_assisted.py` integra lectura local completa,
materialización de tramos existentes y propuestas JSON de Gemini 3.5 Flash-Lite.
Reutiliza los helpers de segmentación/materialización conocidos sin editar
los archivos congelados de v5/v7/v9; el esquema HTTP nuevo vive en
`schemas/analisis_asistido.py` para preservar sus hashes históricos.

La pantalla ofrece **Extraer sin IA**, conserva texto no interpretado y muestra
origen e historial. Ese modo no invoca Gemini ni asigna responsable. Los resultados
se agregan sin borrar cláusulas revisadas; los intentos se auditan con un UUID
que impide aplicar una respuesta tardía sobre una ejecución nueva.
Confirmar mantiene `contexto`; sólo editar y habilitar expresamente permite
aportar a un reclamo. Una interpretación literal pendiente no puede activarse
con su mensaje de relleno y los resúmenes de sólo espacios se rechazan.

La migración 25 fue aplicada sin borrar datos. La prueba PostgreSQL aislada con
rollback pasó. La suite local completa aprobó **520 pruebas, con 23 omitidas**;
frontend aprobó **112**, lint y build. Se revisó la interfaz con datos sintéticos
a 320, 390, 768 y 1440 px, sin desbordamiento horizontal y con teclado.
La lectura local de V01–V04 conservó el texto por página (comparación sin
espacios), incluyendo las tres páginas OCR de V02.

Una única petición real autorizada de V04 respondió HTTP 200: **7 propuestas
de IA y 7 bloques literales**. La revisión documental dio 3/5 controles completos
(60%), 1/3 críticos completos (33,3%) y una propuesta con atribución no respaldada.
La procedencia de las citas no prueba la corrección de resumen o condiciones.
No se enviaron contratos privados, no se probaron los holdouts ni se escribió
ese resultado externo en Supabase.

La [decisión completa y resultados](evaluaciones/hu30/flujo_asistido_2026-10-05.md)
detallan el alcance y la revisión pendiente. Notion rechazó el ADR por límite
de bloques gratuitos; la documentación quedó en el proyecto. Talía autorizó
entregar los cambios de `feat/AARI-319-extraccion-clausulas` mediante commit/push
y registrar dos horas adicionales el 05/10. El PR #28 está abierto para revisión de Tobías;
la HU sigue en curso, sin autorización de cierre o merge. Antes del cierre, corresponde revisar el
flujo asistido y aceptar explícitamente ese alcance, sin confundirlo con haber
cumplido los indicadores del modelo automático.

Las [correcciones del PR #28](evaluaciones/hu30/correcciones_pr28_2026-10-05.md)
integran `main` preservando AARI-135, corrigen la vigencia en horario argentino
y protegen la reserva de cada trabajo de extracción. Se verificaron con
PostgreSQL local descartable y Gemini simulado, sin modificar Supabase.

La segunda revisión del PR #28 incorpora localmente `main` con HU11/AARI-125
(`80afb67`), resuelve el README conservando ambos módulos y agrega una política
Git de fin de línea para reproducir los hashes en Windows. Los manifiestos y
resultados congelados no se recalculan; los PDF conservan hash de bytes originales.
El nuevo motor `contract_ocr.py` libera explícitamente los recursos de PDFium
y usa una copia PIL independiente. El worker actual lo inyecta sin editar el
adaptador histórico congelado. La evaluación asistida actual usa el mismo motor.

El checkout Windows independiente con `core.autocrlf=true` aprobó **588 pruebas
de backend, con 50 omitidas**, y **122 de frontend** con un worker; lint y build
aprobados. Se documenta
un fallo intermitente preexistente de foco en operadores que pasó aislado; no se
modificó ese módulo. En esta ronda no se usaron servicios externos ni se
ejecutaron migraciones. Detalle y límites en la segunda revisión de
[correcciones del PR #28](evaluaciones/hu30/correcciones_pr28_2026-10-05.md).
Talía autorizó entregar esta actualización mediante commit/push y respuestas
en GitHub/Jira. Sigue pendiente la nueva revisión de Tobías; no se cierra la HU
ni se fusiona el PR por esta entrega.
