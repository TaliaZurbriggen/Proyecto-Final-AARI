# HU30 - Evaluación de generalización del prompt v2

**Fecha:** 24/09/2026. **Modelo:** `gemini-3.5-flash`. **Prompt:** `v2`.
**Llamadas externas:** 4, una por documento. **Reintentos:** 0.

Los hashes del prompt, adaptador y documentos se verificaron antes de cada
corrida. Los 23 resultados esperados se definieron y validaron por lectura de
las fuentes antes de observar las respuestas. El prompt no cambió entre V01 y
V04. H01 y H02 permanecieron reservados y no fueron inspeccionados ni enviados.

## Resultado por documento

| Documento | Propuestas | Evidencia válida | Contenido localizado | Completo y aceptable | Críticos localizados | Críticos completos | Resultado estricto |
|---|---:|---:|---:|---:|---:|---:|---|
| V01 | 16 | 7 (43,8%) | 8/8 (100%) | 1/8 (12,5%) | 5/5 (100%) | 0/5 (0%) | No cumple |
| V02 | 10 | 9 (90%) | 5/5 (100%) | 3/5 (60%) | 4/4 (100%) | 2/4 (50%) | No cumple |
| V03 | 9 | 9 (100%) | 5/5 (100%) | 5/5 (100%) | 3/3 (100%) | 3/3 (100%) | Cumple |
| V04 | 6 | 6 (100%) | 4/5 (80%) | 4/5 (80%) | 2/3 (66,7%) | 2/3 (66,7%) | No cumple |
| **Total** | **41** | **31 (75,6%)** | **22/23 (95,7%)** | **13/23 (56,5%)** | **14/15 (93,3%)** | **7/15 (46,7%)** | **No cumple** |

No se aceptaron afirmaciones inventadas: **0 alucinaciones aceptadas**. Hubo
9 resultados parciales, 1 incorrecto y 0 controles totalmente omitidos.

## Cómo interpretar las dos coberturas

`Contenido localizado` cuenta una regla cuando Gemini reconoció su significado,
aunque la propuesta haya quedado bloqueada por una cita no literal. `Completo y
aceptable` exige además que la evidencia pueda comprobarse exactamente en las
páginas declaradas y que no se pierdan condiciones o ambigüedades.

Por eso el 95,7% no significa que el resultado pueda entrar al clasificador. El
backend actuó correctamente al rechazar citas modificadas. Tampoco corresponde
describir el 56,5% como falta de comprensión: gran parte de la diferencia está
en que Gemini corrigió o normalizó palabras extraídas con espacios o defectos de
OCR, en vez de copiarlas literalmente.

## Hallazgos

### V01

Gemini encontró los ocho contenidos esperados, pero nueve de sus dieciséis
propuestas contenían al menos una cita no literal. Entre ellas estaban las reglas
principales de conservación, reparaciones, expensas, aviso de 72 horas y
reparaciones urgentes. Sólo la regla de modificaciones quedó completa dentro de
los controles. También sugirió como `operativa` información de terminación del
contrato que requiere corrección humana antes de cualquier uso.

### V02

El OCR local recuperó completas las tres páginas. Gemini cubrió los cinco
resultados esperados. La cláusula central sobre reparaciones estructurales,
urgencia, aviso de 24 horas e intimación fue semánticamente correcta, pero su
cita no coincidió literalmente y quedó rechazada. Las reglas de gastos,
mantenimiento, daños e inventario sí conservaron evidencia válida.

### V03

Fue el mejor resultado: nueve propuestas con evidencia válida y los cinco
controles completos. Conservó el reparto de servicios y expensas, el acceso sin
inventar un plazo y la excepción de adecuaciones no estructurales que continúa
en la página siguiente.

### V04

La continuidad de la cláusula de reparación entre páginas funcionó y se mantuvo
al locador como responsable. El único resultado incorrecto fue la cláusula sexta:
el texto tiene una sintaxis ambigua sobre consumos y gastos comunes, y Gemini la
resolvió en vez de conservarla para revisión. No inventó evidencia, pero su
resumen no es seguro para uso automático.

## Conclusión

El prompt v2 **generaliza bien para localizar contenido**, pero todavía no
alcanza el criterio de aceptación de HU30: 85% completo, 100% crítico y cero
alucinaciones aceptadas. Cumple únicamente el último punto. El problema dominante
es la trazabilidad literal sobre texto digital defectuoso u OCR; el segundo es
el tratamiento de cláusulas sintácticamente ambiguas.

No conviene revertir el trabajo ni ajustar v2 silenciosamente a estos cuatro
archivos. Una propuesta de v3 debería separar mejor dos responsabilidades:

1. Gemini identifica significado, condiciones y responsables.
2. El backend localiza de forma conservadora el fragmento exacto en la página y
   sólo guarda texto proveniente del PDF, con revisión cuando no haya coincidencia
   única y suficientemente cercana.
3. Ante sintaxis ambigua, la salida debe conservar la ambigüedad, usar
   `no_especificado` cuando corresponda y marcar revisión en vez de resolverla.

V01-V04 pasan a ser regresión conocida para esa mejora. La generalización final
de una eventual v3 debe medirse con H01-H02, que continúan sin revelar.

## Evidencia

Los resultados crudos y las revisiones control por control están en
`docs/evaluaciones/hu30/resultados_corpus_v2/`. Cada resultado conserva modelo,
versiones, hashes, páginas, propuestas válidas, propuestas rechazadas y motivo
del rechazo. La tasa de evidencia válida no se presenta como precisión semántica.
