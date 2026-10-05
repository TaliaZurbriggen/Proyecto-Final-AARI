# Insumos locales de HU30

## Estado vigente al 05/10/2026

Se aprobó e implementó el [flujo asistido con respaldo literal](flujo_asistido_2026-10-05.md).
El ensayo real hizo una petición HTTP exitosa con Gemini 3.5 Flash-Lite; las
interpretaciones siguen requiriendo revisión humana y **no superaron los
umbrales automáticos**. El modo sin IA conserva el texto y no asigna responsables.
Esta decisión reemplaza como estado actual las propuestas pendientes descritas
en los registros históricos, que se mantienen intactos.

- [Respuesta original del ensayo asistido](asistida_2026-10-05.json).
- [Revisión documental separada](revision_asistida_2026-10-05.json).
- [Comprobación local de V01–V04](lectura_asistida_2026-10-05.json).
- [Decisión y resumen de implementación](flujo_asistido_2026-10-05.md).

Notion rechazó el registro del ADR por límite de bloques gratuitos del espacio.
La documentación queda en el repositorio; no se borraron páginas ni se cambió
la suscripción. H01–H02 siguen reservados. No se autoriza otra llamada externa
por el mero hecho de contar con estos ejecutores.

Preparación iniciada el 14/09/2026: copia anonimizada, resultados esperados y
[diseño técnico](../../hu30_extraccion_clausulas.md). Al 21/09 la funcionalidad
está implementada y validada con modelos simulados, OCR real y ejecuciones reales
de Gemini mediante `function_calling`. La salida continúa pendiente de revisión
humana y no se incorpora automáticamente al clasificador.

## Entregables

- [PDF de ejemplo anonimizado](../../../output/pdf/hu30_contrato_anonimizado.pdf).
- [17 controles de resultados esperados](resultados_esperados_ejemplo_01.md).
- [Verificación del PDF](../../../output/pdf/hu30_contrato_anonimizado.verificacion.json).
- [Resultado estructurado v1](resultado_gemini_ejemplo_01.json) y
  [evaluación v1](evaluacion_gemini_ejemplo_01.md).
- [Resultado estructurado v2](resultado_gemini_ejemplo_01_v2.json) y
  [evaluación v2](evaluacion_gemini_ejemplo_01_v2.md).
- [Registro de los tres intentos autorizados](intento_gemini_2026-09-21.json).
- [Corpus v2 de generalización](corpus_v2.md), con manifiesto verificable,
  cuatro modelos públicos y 23 resultados esperados.
- [Evaluación consolidada del corpus v2](evaluacion_corpus_v2.md): cuatro
  llamadas, revisión control por control y conclusiones.
- [Preparación local v3](preparacion_v3.md): anclaje exacto, tratamiento de
  ambigüedad, regresión local y manifiesto congelado.
- [Evaluación de regresión v3](evaluacion_corpus_v3.md): cuatro invocaciones sin
  reintentos manuales, 19/23 controles completos, 12/15 críticos y cero alucinaciones
  aceptadas.
- [Preparación local v4](preparacion_v4.md): reglas atómicas, evidencia breve,
  control explícito de coordinaciones ambiguas y manifiesto congelado.
- [Intento externo v4 del 24/09](intento_v4_2026-09-24.json): V01 bloqueado por
  cuota gratuita antes de generar resultados; V02-V04 no fueron enviados.
- [Intento externo v4 del 25/09](intento_v4_2026-09-25.json): V01 y V02
  recibieron `503 UNAVAILABLE`; V03 y V04 no fueron enviados.
- [Evaluación v4 de V01 por ventanas](evaluacion_v4_ventanas.md): checkpoints
  separados y corrección de los reintentos internos de Gemini.
- [Intentos v4 de V02 y V04 del 27/09](intento_v4_2026-09-27_v02_v04.json):
  extracción local completa, dos invocaciones externas y dos respuestas `503`;
  no se generaron resultados evaluables.
- [Diagnóstico de Interactions del 28/09](diagnostico_interactions_2026-09-28.md):
  las consultas mínimas de 3.5 Flash por Interactions y Flash-Lite por
  generateContent respondieron. La única extracción V04 con JSON nativo fue
  rechazada con `400 invalid_request`; no generó cláusulas ni métricas.
  Un intento posterior autorizado de V04 con `function_calling` por Interactions
  recibió `503` por alta demanda del modelo, también sin cláusulas evaluables.
  Resultados separados; no se cambió la integración de producción.
- [Ensayo V04 con Flash-Lite del 30/09](evaluacion_flash_lite_v04_2026-09-30.md):
  el adaptador existente respondió con cinco propuestas; cuatro pasaron el
  anclaje actual y una fue rechazada. La revisión documental dio 2/5 controles
  completos, 1/3 críticos y una afirmación no respaldada aceptada. No supera
  los umbrales ni cambia el modelo de producción. El JSON capturado perdió
  algunas tildes y no sirve para repetir el anclaje literal.
- [Verificador local por tramos del 30/09](verificador_tramos_2026-09-30.md):
  análisis nuevos comprueban que cada cita pertenezca a una única cláusula,
  con continuaciones entre páginas y descarte conservador de encabezados OCR
  ilegibles. El prompt y el modelo no cambiaron.
- [Preparación local v5 experimental](preparacion_v5.md): entrada por tramos que
  conserva todo el texto de V01–V04, con un solo punto de invocación a un modelo
  inyectado. No está conectada a producción; la preparación local no llamó a Gemini.
- [Ensayo v5 de V04 del 30/09](evaluacion_v5_v04_2026-09-30.md): una invocación
  autorizada y registro UTF-8 completo. Hubo cinco propuestas aceptadas por
  anclaje, pero la revisión documental dio 4/5 controles completos, 2/3 críticos
  y una interpretación no respaldada aceptada. No supera los umbrales.
- [Intento v5/V04 con Flash del 02/10](intento_v5_v04_flash_2026-10-02.md):
  comprobación previa y archivo independientes del ensayo Flash-Lite; la única
  invocación recibió HTTP 503 y no generó cláusulas evaluables.
- [Preparación local v6 del 02/10](preparacion_v6.md): prompt y control
  experimental de cobertura de citas, preflight de V01-V04 y replay sin modelo
  sobre V04. No modifica producción ni demuestra una mejora de exactitud.
- [Ensayo v6/V04 con Flash-Lite del 02/10](evaluacion_v6_v04_2026-10-02.md):
  Gemini respondió con cinco propuestas; dos pasaron el filtro y tres fueron
  rechazadas. La ambigüedad se conservó, pero la revisión de citas dejó los
  cinco controles parciales. No cumple los umbrales y expone los límites del
  control de cobertura literal.
- [Preparación v7 del 02/10](preparacion_v7.md): Gemini interpretaría un tramo
  por su identificador y el backend adjunta evidencia y páginas de la fuente
  local. Las pruebas y el preflight de V01-V04 aprobaron; la ejecución externa
  fue bloqueada antes de llamar al proveedor por requerir autorización específica.
- [Ensayo v7/V04 del 02/10](evaluacion_v7_v04_2026-10-02.md): tras la autorización
  específica, la evidencia local resolvió citas y páginas; cuatro controles
  quedaron completos y uno incorrecto por atribución ambigua. No se ejecutaron
  V01-V03 porque V04 no superó los umbrales.
- [Preparación v8 del 02/10](preparacion_v8.md): refinamiento de atribuciones
  expresas y alcance de listas, conservando evidencia, texto extraído y controles.
  Suite y preflight aprobados; luego se autorizó el ensayo condicionado a V04.
- [Ensayo v8/V04 del 02/10](evaluacion_v8_v04_2026-10-02.md): seis propuestas
  con evidencia completa, cuatro controles completos y uno parcial. Reconoce
  ambigüedad y no inventa pagador, pero condiciones todavía elige un alcance
  de la excepción. No supera los umbrales; V01-V03 no se enviaron.
- [Preparación v9 del 02/10](preparacion_v9.md): coherencia de incertidumbre
  entre resumen y condiciones sin cambiar evidencia ni controles. Suite local:
  385 aprobadas y 23 omitidas; preflight de V01-V04 aprobado. Las pruebas con
  dobles no demuestran mejora semántica.
- [Ensayo v9/V04 del 02/10](evaluacion_v9_v04_2026-10-02.md): cinco propuestas
  con evidencia completa, pero sólo 3/5 controles completos y 1/3 críticos.
  Regresión en ambigüedad y una condición tomada del prompt, no del contrato.
  No cumple los umbrales; V01-V03 no se enviaron.
- [Comparación v9/V04 con Flash del 02/10](comparacion_v9_flash_2026-10-02.md):
  mismo texto y prompt que Lite, ejecutor independiente y 402 pruebas locales
  aprobadas. La única invocación recibió 503; no generó cláusulas evaluables,
  no se reintentó y no modificó la referencia Lite ni producción.
- [Ensayo v9/V04 con Flash 3.8 del 02/10](comparacion_v9_flash38_2026-10-02.md):
  entrada idéntica y registro independiente; 420 pruebas locales aprobadas.
  La única invocación también recibió 503, sin cláusulas evaluables y sin
  reintento manual. Luego se ejecutó el diagnóstico mínimo separado.
- [Diagnóstico mínimo de Flash 3.8 del 02/10](diagnostico_flash38_minimo_2026-10-02.md):
  dos invocaciones autorizadas sin contratos respondieron `OK`, con texto simple
  y esquema mínimo. Suite: 429 aprobadas y 23 omitidas. La revisión local conserva
  los nueve campos del esquema completo, pero su aceptación por el proveedor y
  la causa del 503 siguen pendientes; no se modificó producción.
- [Diagnóstico con esquema completo del 02/10](diagnostico_flash38_esquema_completo_2026-10-02.md):
  una invocación autorizada con prompt v9 y dos reglas sintéticas (140 caracteres
  de fuente) recibió HTTP 503. No produjo cláusulas ni se reintentó. Suite:
  438 aprobadas y 23 omitidas; no cambia las métricas ni demuestra la causa.
- [Diagnóstico con instrucciones breves del 02/10](diagnostico_flash38_prompt_breve_2026-10-02.md):
  fuente y esquema idénticos, petición reducida a 504 caracteres; la única
  invocación también recibió 503, sin cláusulas ni reintento. Suite: 450
  aprobadas y 23 omitidas. Se estudió localmente una alternativa JSON nativa,
  todavía no implementada ni autorizada; no cambia producción o métricas.
- [Comparación V04 con Flash 3.6 del 02/10](comparacion_v9_flash36_2026-10-02.md):
  a pedido de probar otro modelo, se mantuvieron V04, prompt v9 y esquema.
  La única invocación también recibió 503, sin cláusulas ni reintento.
  No se cambió producción; después se autorizó el ensayo separado con 3.1.
- [Comparación V04 con 3.1 Flash-Lite del 02/10](comparacion_v9_flash31lite_2026-10-02.md):
  autorización específica, misma entrada y una invocación, también HTTP 503.
  Sin cláusulas de IA ni métricas. La inspección local reconoce 12 cláusulas y
  conserva QUINTA entre páginas. Incluye una propuesta, todavía sin aprobar,
  para extracción literal y revisión humana sin depender de Gemini.
- [Diagnóstico directo sin herramientas del 02/10](diagnostico_directo_flash38_2026-10-02.md):
  SDK oficial sin LangChain, texto público V04, sin MIME ni esquema impuesto.
  La primera etapa recibió HTTP 503: una solicitud HTTP verificada, cero
  reintentos. No se ejecutaron los dos modos JSON preparados. Suite: 469
  aprobadas y 23 omitidas; producción y métricas intactas.
- [Activación explícita de cláusulas del 01/10](activacion_explicita_2026-10-01.md):
  todas las propuestas de IA quedan inicialmente como contexto; sólo una edición
  que seleccione uso operativo puede habilitarlas para reclamos.
- [Ensayo de contexto en reclamos del 02/10](validacion_contexto_reclamo_2026-10-02.md):
  comparación con y sin cláusula ficticia entre Flash y Flash-Lite; la integración
  aislada con Supabase pasó tras la reactivación del proyecto.

**Aclaración de conteo:** los `external_calls: 1` de resultados históricos
representan una invocación del ejecutor. Antes de fijar `max_retries=1`, esa
invocación podía producir más de un intento HTTP ante errores transitorios.
No existe un registro individual que permita recalcular los intentos de las
evaluaciones antiguas.

## Comprobaciones realizadas

| Comprobación | Resultado |
|---|---|
| Documento de origen | Hash antes/después idéntico; no se modificó. No se copia su ruta, nombre ni contenido privado al repositorio. |
| Paginación | 13 páginas, conservadas. |
| Zonas retiradas | 17 zonas revisadas: identidades, domicilios, contactos, administración identificable, fechas y montos concretos. |
| Identificadores reconocibles | 15 ocurrencias de DNI/correo/teléfono recuperadas en memoria del contenido retirado; ninguna reaparece en la salida. |
| Secuencias retiradas | 208 secuencias particulares de tres palabras contrastadas, sin reapariciones en el texto de salida. Este chequeo complementa la revisión; no prueba anonimización de cualquier documento. |
| Conservación de texto | Todos los caracteres fuera de las zonas suprimidas coinciden en orden por página usando pdfplumber. |
| Lectura digital | PDF final legible con pypdf; se corrigió la primera reconstrucción para conservar frases en lugar de generar saltos entre cada letra. |
| Privacidad del contenedor | PDF reconstruido desde cero; sin objetos del original, adjuntos, anotaciones, formularios ni acciones de apertura. Metadatos genéricos nuevos. |
| Revisión visual | 13/13 páginas renderizadas con Poppler e inspeccionadas; sin datos identificatorios visibles, solapamientos ni texto cortado. |
| Lectura local de HU30 | 13 páginas digitales, lectura completa y 21.126 caracteres; no requirió OCR. |
| Supabase | Migraciones 23 y 24 aplicadas; RLS comprobado y prueba aislada con rollback aprobada. |
| Gemini v1 | 18 propuestas, 14 con evidencia válida y 4 descartadas. Cobertura aceptada: 11/17 controles y 6/7 críticos. |
| Gemini v2 | 20 propuestas, 17 válidas y 3 rechazadas conservadas. Encontró los 17 controles; 14/17 quedaron con evidencia aceptada y 6/7 críticos. Recuperó E07 entre páginas. |
| OCR real | **Aprobado** con Tesseract 5.4.0 y español sobre un PDF sintético compuesto sólo por una imagen: 1 prueba aprobada. |

Los títulos, apartados y condiciones de mantenimiento/reparación se conservan.
La copia cambia las zonas de identificación y su tipografía se reconstruye con
fuentes locales, por lo que no pretende ser un facsímil ni un documento firmado.
Los plazos relativos y porcentajes contractuales se conservan para no alterar el
sentido de esas cláusulas; los importes particulares se retiraron.

## Reproducir la preparación local

`preparar_ejemplo_local.py` es una herramienta de autoría para **este ejemplo ya
revisado**, no el anonimizador de HU30 ni un servicio de la aplicación. No usarla
con otro contrato sin nueva revisión de las zonas. No incorpora el original ni
contiene sus valores personales. Requiere un archivo fuente local proporcionado
por su titular, Python con `pdfplumber`, `pypdf`, `reportlab` y las fuentes Calibri
del sistema. Estas dependencias se utilizaron desde el runtime de documentos;
no se cambiaron los requisitos del backend.

Desde la raíz de este worktree, con las dependencias disponibles:

```powershell
python docs/evaluaciones/hu30/preparar_ejemplo_local.py RUTA_PDF_LOCAL output/pdf/hu30_contrato_anonimizado.pdf --font-dir C:/Windows/Fonts
```

La herramienta valida el documento concreto, construye la copia sin datos
retirados, verifica el texto y genera el reporte JSON. Al regenerarlo, la revisión
visual vuelve a `pending`: renderizar e inspeccionar las 13 páginas antes de
marcarla como aprobada. Nunca subir el PDF original ni volcados de su texto.

## Pendientes de evaluación

1. Extender la comprobación OCR/segmentación a otros formatos reales. V02 ya
   recupera las tres páginas y sus 15 artículos sin falsos tramos con la versión
   `hu30-v4-tramos-v2`; ver [verificador por tramos](verificador_tramos_2026-09-30.md).
   Los tramos no reconocibles en otros documentos quedan para revisión.
2. V04 ya se evaluó con v5-v9 y no superó los umbrales. V9 además introdujo
   una condición ajena al contrato. Las comparaciones controladas v9/Flash
   3.5 y 3.8 quedaron sin resultado evaluable por 503. El diagnóstico mínimo 3.8
   respondió con texto y esquema de un campo; la prueba posterior con esquema
   completo, prompt v9 y texto sintético recibió 503. También falló con
   instrucciones breves y al cambiar únicamente a Flash 3.6 y 3.1 Flash-Lite.
   El diagnóstico directo posterior también recibió 503 sin LangChain,
   herramientas ni esquema impuesto por la API. Consumió una solicitud HTTP
   y se detuvo; los modos JSON están preparados con mocks, pero no ejecutados
   externamente. No se deben repetir estos intentos ni reutilizar el cupo no
   consumido con otro experimento sin autorización nueva. La extracción literal
   local de V04 reconoce 12 cláusulas;
   habilitarla en la interfaz como modo independiente requiere aprobación
   de la [propuesta de continuidad](comparacion_v9_flash31lite_2026-10-02.md).
   La salvaguarda de
   activación explícita evita que las
   propuestas se usen en reclamos por simple confirmación, pero no corrige su
   interpretación. Decidir después la regresión V01–V03. Las ventanas v4 de V01 quedaron
   inconclusas y sus resultados históricos no cambian. H01-H02 continúan
   reservados por Tobías/Oikos hasta que la regresión conocida cumpla.
3. Revisar con la inmobiliaria qué cláusulas deben usar `operativa`, `contexto` o
   `excluir`; la revisión continúa editable y auditable.

La implementación no crea un PR por sí sola. Los cambios quedan locales en la
rama de HU30 hasta la indicación de commit/push. Se mantiene el acuerdo del
Sprint 3 de documentación en el repositorio mientras Notion esté limitado.
