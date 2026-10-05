# HU30 — preparación local de v6 experimental (02/10/2026)

## Motivo

La regresión v3 localizó los tres controles parciales de V01, pero sus citas
contenían omisiones con `...` y el anclaje las rechazó correctamente. En el
ensayo v5 de V04, la propuesta sobre la cláusula sexta fue aceptada porque su
cita literal pertenecía al tramo; sin embargo, citaba sólo el inicio y el
resumen resolvía una excepción ambigua que no aparecía en la evidencia. El
resultado v5 fue 4/5 controles completos, 2/3 críticos y una interpretación
no respaldada aceptada. El intento posterior de v5 con Flash respondió 503 y
no produjo una comparación evaluable.

## Cambio aislado

- `backend/prompts/prompt_extraccion_clausulas_v6.md` pide identificar primero
  citas literales separadas para sujeto, obligación, condición y excepción;
  prohíbe unir fragmentos con puntos suspensivos. Después exige comprobar el
  alcance de las coordinaciones antes de atribuir responsabilidades. No enumera
  respuestas esperadas ni texto de un contrato del corpus.
- `backend/app/services/contract_clause_v6.py` reutiliza la entrada completa
  por tramos y el anclaje de v5. Un control adicional rechaza citas con
  elipsis y propuestas cuyo resumen o condiciones reutilizan frases de al
  menos cinco palabras presentes en la fuente, pero ausentes de sus citas.
  La comprobación es de **cobertura literal**, no demuestra la interpretación
  jurídica ni detecta toda paráfrasis inventada.
- `backend/scripts/preview_contract_clause_v6.py` comprueba documentos y
  permite repetir una salida v5 archivada sin invocar Gemini ni escribir
  resultados históricos. Sólo informa hashes y conteos, no texto contractual.
- La app sigue usando v4. V5 y sus resultados históricos tampoco se modifican.
  No se tocó el esquema ni se registraron cláusulas en Supabase.

## Comprobación sin modelo

| Documento | Páginas | Tramos | Texto conservado | Observación |
|---|---:|---:|---|---|
| V01 | 9 | 32 | Sí | Lectura digital local. |
| V02 | 3 | 15 | Sí | OCR local con `eng`: aquí falta `spa.traineddata`; no se usa este texto para comparar exactitud. |
| V03 | 3 | 12 | Sí | Lectura digital local. |
| V04 | 2 | 12 | Sí | Lectura digital y repetición de v5. |

El replay de las cinco propuestas archivadas de V04 con el nuevo control
conservó **2** y descartó las propuestas 1, 2 y 3 por mencionar contenido de
la fuente no incluido en sus citas. La 2 es la interpretación problemática ya
conocida. Las 1 y 3 eran correctas en contenido según la revisión histórica,
pero sus citas breves no muestran todas las condiciones que resumen. Por eso
el replay **no es una medición de precisión de v6**: sólo muestra que el nuevo
control reduce aceptación sin respaldo a costa de mayor descarte. La nueva
instrucción busca que una corrida v6 aporte citas completas para recuperarlas,
pero aún no hay evidencia de que el modelo la obedezca.

El prompt v6 quedó con SHA-256
`76a11d51a39be29f0429377b573bd5fc4e3afd4cafcfefc3a237239b47c96314`.
Las seis pruebas específicas de v6 aprobaron. La suite local completa de
backend (`pytest -q --tb=no`, con base en memoria) terminó con **362 aprobadas,
23 omitidas y 2 advertencias de dependencias**. `git diff --check` no informó
problemas de formato y se revisaron los archivos nuevos para evitar secretos.
No se consumió cuota de Gemini y no se tocaron H01/H02. Los umbrales del plan
siguen siendo 85% general, 100% crítico y cero interpretaciones no respaldadas
aceptadas. Antes de cualquier corrida externa debe autorizarse el documento y
modelo exactos, congelarse este prompt y revisarse el resultado control por
control. Sólo entonces se decidirá si v6 sirve para producción.

La decisión queda en el repositorio mientras Notion no permita añadir bloques.
No hubo commit, push, PR ni cambio de estado en Jira en esta etapa.

## Ensayo externo posterior autorizado

Se ejecutó una invocación de V04 con Flash-Lite tras la indicación de probar.
El [resultado y la revisión](evaluacion_v6_v04_2026-10-02.md) registran cinco
propuestas y dos aceptadas técnicamente, pero ninguna completa con cobertura
de todas las condiciones citadas. La ambigüedad de SEXTA se conservó; siguen
las citas truncadas y apareció una atribución de página incorrecta. Los
conteos anteriores corresponden sólo a la preparación local previa al ensayo.
