# HU30: verificación local por tramos de cláusula — 30/09/2026

## Decisión y alcance

La corrida experimental con Flash-Lite reveló que una cita de SÉPTIMA podía
respaldar por error una propuesta marcada SEXTA: el verificador v4 sólo exigía
que el texto existiera en la **página**, no dentro de la cláusula indicada.
Se aprobó corregir el anclaje y probar localmente la segmentación, sin llamadas
adicionales a Gemini, cambio de modelo, prompt, dependencias ni migraciones.

Se conservó sin cambios `contract_clause_evidence.py` y el manifiesto congelado
v4 para no alterar las evaluaciones históricas. El procesamiento nuevo usa
`contract_clause_segments.py` y se identifica como `hu30-v4-tramos-v1`; mantiene
el prompt v4. La versión se guarda al solicitar el análisis y al completarlo.
Si se vuelve a solicitar uno fallido o incompleto sin revisión humana, también
se actualizan extractor, prompt y modelo para que la etiqueta refleje el nuevo
intento. No se reemplazan análisis ya revisados.

**Alternativas descartadas:** cambiar directamente a Flash-Lite no resolvería
sus omisiones ni la cita de la cláusula equivocada; conservar el anclaje por
página permitiría el mismo error; inferir el número de un encabezado OCR o
corregir la cita del modelo crearía una apariencia de evidencia no emitida;
editar el validador v4 congelado rompería la comparabilidad histórica.

## Reglas implementadas

1. Detectar encabezados numerados al inicio de línea (`QUINTA`, `ARTÍCULO
   QUINTO`, `DÉCIMO PRIMERA`, números arábigos y romanos). Conservar la
   diferencia entre cláusula y artículo para que una norma del prefacio no
   suplante una cláusula contractual con el mismo número.
2. Extender cada tramo hasta el siguiente encabezado. El texto anterior al
   primer encabezado de la página siguiente continúa el tramo previo: QUINTA
   de V04 queda en páginas 1 y 2. Una página ilegible o ausente corta esa
   continuidad.
3. Tratar un encabezado con número dañado por OCR como límite **desconocido**.
   No se infiere el número por contexto ni se permite usar su texto para
   respaldar la cláusula anterior.
4. Aceptar una propuesta sólo si todas sus citas son anclables literalmente a
   las páginas declaradas **y a un único tramo** compatible con su número y
   tipo. Una página marcada como ilegible no se usa para respaldar ni para unir
   cláusulas, aunque haya quedado algún texto parcial. Si no se puede delimitar
   el contrato, conservar la propuesta como rechazada para revisión en vez de
   aceptarla automáticamente.

Esto verifica procedencia, **no la verdad semántica del resumen**. La revisión
humana de responsables, excepciones y categorías sigue siendo obligatoria.
No se corrige automáticamente una cita mal paginada ni una afirmación ambigua.

## Validaciones

- Diez pruebas nuevas para continuación entre páginas, cita de cláusula vecina,
  página equivocada, encabezados compuestos, OCR ilegible y artículos del
  prefacio; además dos pruebas del flujo de servicio que conservan la propuesta
  rechazada y no aceptan evidencia de una página con lectura incompleta.
- Suite de backend con `DATABASE_URL=sqlite:///:memory:`:
  **338 aprobadas, 23 omitidas, dos advertencias de bibliotecas** tras el
  ajuste de páginas ilegibles. Las omisiones incluyen integraciones externas
  no habilitadas; no se consultó Supabase ni Gemini.
- Comprobación local sobre las dos páginas públicas V04: se detectaron las
  12 cláusulas, QUINTA abarca páginas 1–2; una cita literal de QUINTA en ambas
  páginas fue aceptada y SEXTA con cita de SÉPTIMA fue rechazada.
- V01 y V03 se segmentaron localmente. En la primera comprobación, V02 era un PDF
  escaneado y la instalación
  local sólo tiene OCR `eng`, no `spa`; con `eng` se detectaron varios artículos
  pero otros encabezados quedaron ilegibles. El verificador los deja como
  límites desconocidos. **No se declara validación completa de V02** hasta
  disponer de OCR español o una lectura equivalente comprobada.

### Comprobación posterior de V02 con OCR español (30/09/2026)

Se descargó sólo para esta prueba, en `tmp/` ignorado por Git, el modelo oficial
`spa.traineddata` de `tessdata_fast` (SHA-256
`6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464`,
igual al usado el 27/09). Con la resolución actual del servicio (2,2), las tres
páginas se leyeron por OCR y dieron 11.750 caracteres en total, lectura completa,
sin llamadas a Gemini. El verificador reconoció los artículos 2, 4, 5, 7–11 y
13–15; el 6 quedó como límite desconocido, pero el 12 dañado ni siquiera produjo
un límite. Eso puede extender indebidamente el tramo 11: **tener texto legible no
implica tener segmentación segura**.

Una comparación local sin editar código mostró que a escala 3,0 se reconocen
los artículos 2–15 y a escala 4,0 los 15 artículos del PDF. A escala 4,0 apareció
un límite falso dentro del artículo 3 (`CI ).`) causado por una lectura OCR que
parece un número romano. Estos resultados fueron exploratorios: el PDF se
contrastó visualmente en sus tres páginas y no se modificó la fuente.

### Ajuste implementado y comprobado

Con aprobación posterior se elevó la resolución del OCR local de 2,2 a 4,0 y
se corrigieron dos límites del verificador: un número romano inválido sin
prefijo `ARTÍCULO`/`CLÁUSULA` ya no divide un tramo; un encabezado con prefijo y
número dañado seguido sólo de un punto sí corta el tramo, pero conserva número
desconocido. No se adivina el artículo a partir de su posición. Los análisis
nuevos se identifican como `hu30-v4-tramos-v2`; el prompt v4 y los registros
históricos se mantienen intactos.

La comprobación real de V02, con el mismo archivo y OCR español, recuperó las
tres páginas completas y **los artículos 1 a 15 en orden, sin falsos tramos**.
El artículo 5 continúa de la página 1 a la 2. La prueba sintética de OCR real
y las pruebas específicas terminaron con **28 aprobadas**; toda la suite de
backend, sin integraciones externas, terminó con **342 aprobadas, 22 omitidas
y dos advertencias de bibliotecas**. No se llamó a Gemini ni a Supabase.
El paquete de idioma quedó sólo en `tmp/`, ignorado por Git; cada entorno debe
tener instalado `spa` conforme al README. Esta comprobación valida la lectura y
segmentación de V02, **no** la calidad semántica de las propuestas del modelo.

## Riesgos y próximos pasos

- Una cita correcta en otro PDF con encabezados no reconocibles puede rechazarse.
  Es una degradación conservadora, visible en propuestas rechazadas, no una
  asignación automática errónea. Requiere revisión con más formatos reales.
- El modelo todavía puede omitir una cláusula o resumir mal una coordinación:
  este cambio no eleva la cobertura 2/5 de la prueba Flash-Lite ni justifica
  sustituir el modelo actual.
- Para evaluar una mejora del prompt o de la entrada segmentada hace falta una
  propuesta de nueva versión y autorización separada para cada llamada externa.

No se hicieron commits, push, PR ni cambios de estado en Jira por esta
implementación local.

La incorporación a la página de decisiones técnicas de Notion se intentó,
pero el espacio informó que agotó los bloques gratuitos y no creó contenido.
Este documento conserva la decisión hasta que el equipo decida cómo recuperar
espacio o ampliar el plan. No se reintentó la operación.
