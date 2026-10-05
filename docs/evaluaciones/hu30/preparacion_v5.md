# HU30: preparación local de v5 experimental — 30/09/2026

## Motivo y decisión

La última corrida evaluable de V04 con v4 y Flash-Lite alcanzó sólo 2/5
controles completos y 1/3 críticos: omitió OCTAVA y no conservó correctamente
QUINTA entre páginas. El verificador por tramos v2 ya impide que una cita de
una cláusula vecina se acepte como propia, pero no obliga al modelo a revisar
todo el documento. Se aprobó ensayar una entrada v5 que haga visible el índice
de tramos **sin cambiar producción ni consumir cuota en esta etapa**.

Se eligió una sola invocación del adaptador por documento, no una llamada por
cláusula, para evitar multiplicar cuota y dificultar la reconstrucción de
reglas que continúan entre páginas. Los marcadores técnicos se agregan al
texto original; no reemplazan ni corrigen el OCR. Antes de preparar el prompt,
se comprueba que la concatenación de los bloques recupere exactamente cada
página. El preámbulo y cualquier texto sin tramo quedan incluidos. Los tramos
con encabezado ilegible se señalan como inciertos, sin inferir su número. El
prompt pide recorrer todos los tramos relevantes, preservar ambigüedades y
citar sólo el texto de la fuente. El modelo sigue entregando el mismo esquema
de cláusulas; el verificador `hu30-v4-tramos-v2` comprueba después las citas.

**Alternativas no elegidas:** una llamada por tramo aumentaría cuota y podría
partir continuaciones; enviar sólo los tramos detectados perdería el preámbulo
o texto sin encabezado; modificar v4 rompería las comparaciones históricas.

## Aislamiento y privacidad

- Nuevo prompt: `backend/prompts/prompt_extraccion_clausulas_v5.md`, SHA-256
  `2412cf4b50128b8ec307d05be07c22639acadf2683eeefb91e2777b6c8c4a4ba`.
- Preparación y ensayo con modelo inyectado: `backend/app/services/contract_clause_v5.py`.
  No lo llama el servicio de producción ni crea registros en Supabase.
- Previsualización sin modelo: `backend/scripts/preview_contract_clause_v5.py`.
  Sólo imprime hashes y conteos; nunca imprime el texto del contrato o el prompt.
- Pruebas con dobles: `backend/tests/test_contract_clause_v5.py`.
- Se aplican las mismas máscaras locales de DNI, email y teléfono antes de
  construir el prompt. Eso no autoriza a enviar contratos privados: la primera
  evaluación externa, si se aprueba, usará únicamente el PDF público V04.

El prompt v4, el modelo configurado en producción, el esquema de base de datos
y la lógica de reclamos no se cambiaron. La v5 no queda habilitada para usuarios.

## Comprobaciones locales

| Documento | Páginas | Tramos | No reconocidos | Continuaciones entre páginas | Texto conservado | Llamadas externas |
|---|---:|---:|---:|---|---|---:|
| V01 | 9 | 32 | 3 | 10, 16, 20, 24, 32 | Sí | 0 |
| V02 | 3 OCR español | 15 | 0 | 5 | Sí | 0 |
| V03 | 3 | 12 | 0 | 5, 10 | Sí | 0 |
| V04 | 2 | 12 | 0 | 5 | Sí, incluidos 604 caracteres de preámbulo | 0 |

V04 mantuvo sus 4.709 caracteres de origen; la entrada segmentada ocupa 5.114
caracteres y el prompt completo 9.029. Se verificó el hash del PDF y la
congelación histórica v4 antes de la previsualización. La suite completa de
backend con OCR local habilitado terminó con **348 aprobadas, 22 omitidas y dos
advertencias de bibliotecas**. No se ejecutaron Gemini ni Supabase.

## Límites y siguiente evaluación

La reconstrucción exacta garantiza que no se perdió texto, **no que el
segmentador interpretó todos los límites correctamente**. V01 conserva tres
tramos sin número seguro. En V02, el material de anexo posterior puede requerir
separación y revisión para no atribuirlo automáticamente al último artículo.
Una sola invocación del adaptador tampoco demuestra por sí sola cuántas
peticiones HTTP internas hizo el proveedor. Ninguna métrica de exactitud del
modelo mejoró todavía: v5 sólo se comprobó localmente con dobles.

Antes de una llamada externa se debe congelar la configuración exacta y pedir
autorización específica. La primera comparación adecuada es **V04 con el mismo
modelo Flash-Lite de la última corrida evaluable**, seguida de revisión humana
de sus cinco controles; no se usará la captura v4 con caracteres dañados como
referencia literal. Si V04 supera los umbrales, continuar con V01–V03 y los
holdouts reservados según el plan. Si no los supera, analizar los fallos antes
de introducir otra versión.

La decisión quedó registrada aquí porque el espacio de Notion continúa sin
bloques gratuitos disponibles; no se reintentó escribir allí. No se hicieron
commit, push, PR ni cambios de Jira en esta etapa.

## Ensayo externo posterior autorizado

Se ejecutó una única invocación experimental sobre V04 con Flash-Lite. El
resultado y la revisión se documentan en [evaluación v5 de V04](evaluacion_v5_v04_2026-09-30.md):
cinco propuestas técnicamente aceptadas, pero sólo cuatro controles completos,
dos de tres críticos y una interpretación no respaldada aceptada. **No aprueba**
los umbrales ni modifica producción. Los conteos de la tabla anterior describen
exclusivamente la preparación local previa a esa llamada.
