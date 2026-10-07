# HU30 — ensayo v6 con V04 y Flash-Lite (02/10/2026)

## Resultado y alcance

Gemini respondió correctamente a la llamada: **cinco propuestas**, dos
aceptadas por los controles locales y tres rechazadas. La conexión funciona
en este ensayo; no hubo error de cuota ni de disponibilidad. Se realizó una
invocación del adaptador con `gemini-3.5-flash-lite`, usando el mismo documento
y modelo del ensayo v5. No hubo reintento manual. El adaptador conserva
`max_retries=1`; no se afirma un número de peticiones HTTP que el registro no
verifica. El PDF público V04 y el prompt v6 coincidieron con sus hashes
congelados antes del envío. No se enviaron controles esperados ni contratos
privados. La lectura local conservó dos páginas y 4.709 caracteres.

La [salida completa](resultados_v6/resultado_v04_v6.json) mantiene propuestas,
rechazos, motivos y hashes. La [revisión](resultados_v6/revision_v04_v6.json)
se hizo contrastando el texto extraído del documento con los cinco controles
validados. El [ejecutor](../../../backend/scripts/evaluate_contract_clause_v6.py)
guarda un checkpoint antes de invocar y no repite una corrida ya registrada.

## Revisión de los cinco controles

| Control | Resultado de contenido | Evidencia y estado final |
|---|---|---|
| E01 — reparaciones entre páginas | Reconoce responsable y vigencia. | Coloca en página 2 una cita de página 1. Rechazada; parcial. |
| E02 — gastos y sintaxis ambigua | Esta vez preserva la ambigüedad como contexto, con responsable no especificado y confianza 0,6. | No cita consumos ni gastos comunes. Rechazada; parcial. |
| E03 — conservación y devolución | Reconoce deterioros y excepción por uso y tiempo; omite acta e inventario. | Cita sólo el inicio. Rechazada; parcial. |
| E04 — seguridad y normas | Resumen fiel a la fuente. | Pasa el filtro, pero no cita la parte de normas municipales. Parcial en revisión. |
| E05 — modificaciones | Resumen fiel, con autorización y ausencia de deber de restaurar. | Pasa el filtro, pero no cita la excepción de devolución. Parcial en revisión. |

Los **dos aceptados técnicamente no son dos controles completos**. Aplicando
la exigencia de evidencia para todas las condiciones relevantes, quedan
**0/5 completos**, **0/3 críticos completos** y cinco parciales. No hay una
interpretación inventada aceptada, pero sí dos propuestas que el filtro
considera aceptables pese a sus citas incompletas. **No cumple los umbrales**.

La revisión histórica v5 consideró completos algunos resúmenes correctos con
citas breves. Por eso no se debe describir el cambio de 4/5 histórico a 0/5
estricto como una pérdida equivalente de comprensión: ahora se está haciendo
explícita la cobertura de cada condición citada. Los resultados históricos
no se alteran. La comparación concreta que sí permite este ensayo es que
v6 preservó la ambigüedad de SEXTA, mientras que v5 la resolvía.

Los conteos se recalcularon sin API con `evaluate_contract_clause_corpus.py
--document V04 --manifest ../docs/evaluaciones/hu30/corpus_v4_manifest.json
--score-review ../docs/evaluaciones/hu30/resultados_v6/revision_v04_v6.json`
desde backend: cinco parciales, cero completos y `passed: false`. El encabezado
del ejecutor muestra v4 y su modelo porque reutiliza el manifiesto histórico
para controles y umbrales; la corrida revisada es v6/Flash-Lite, según su JSON.

## Qué aprendimos y siguiente propuesta

El modelo siguió copiando sólo las primeras líneas de cada cláusula pese a la
instrucción de citar condiciones y excepciones. Además, confundió una página.
El filtro de cinco palabras bloquea algunos casos, pero no demuestra respaldo
semántico: una paráfrasis puede pasar sin su cita. No corresponde usarlo como
garantía de que todas las afirmaciones estén probadas.

La siguiente propuesta recomendada es cambiar la forma de obtener evidencia:
el modelo identificaría tramos y extraería significado; el backend adjuntaría
el texto exacto de esos tramos y sus páginas desde la fuente local. Eso reduce
la dependencia de que Gemini transcriba bien, pero sigue requiriendo controles
de atribución, conservación de condiciones y revisión humana del resumen.
Es una propuesta de arquitectura pendiente, **no implementada ni aprobada**.
No conviene otra tanda de llamadas con esta misma v6 para resolver una falla
que ya quedó localizada. V01-V03 y los holdouts H01-H02 no se enviaron.

## Pruebas y documentación

Las nueve pruebas locales de v6 y del registro de corridas aprobaron. La suite
completa de backend terminó con **365 aprobadas, 23 omitidas y dos advertencias
de dependencias** (`pytest -q --tb=no`, base local en memoria). Se comprobó el
checkpoint de éxito, el de error seguro, la prevención de llamadas duplicadas
y el bloqueo de documentos ilegibles. No se modificaron registros en Supabase.

El resultado queda en el repositorio mientras Notion siga limitado. No se
hizo commit, push, PR ni cambio de Jira. La aplicación conserva su extractor
actual; la v6 continúa experimental.
