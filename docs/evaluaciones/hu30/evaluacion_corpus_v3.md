# HU30 - Evaluación de regresión del prompt v3

**Fecha:** 24/09/2026. **Modelo:** `gemini-3.5-flash`. **Prompt:** `v3`.
**Llamadas externas:** 4, una por documento. **Reintentos:** 0.

Los hashes del prompt, el adaptador, el anclaje y los documentos se verificaron
antes de cada corrida. Se reutilizaron sin cambios los 23 resultados esperados
que habían sido definidos y validados antes de observar v2. El prompt permaneció
congelado durante V01-V04. H01 y H02 no fueron inspeccionados ni enviados.

## Resultado por documento

| Documento | Propuestas | Evidencia válida | Contenido localizado | Completo y aceptable | Críticos localizados | Críticos completos | Resultado estricto |
|---|---:|---:|---:|---:|---:|---:|---|
| V01 | 16 | 12 (75%) | 8/8 (100%) | 5/8 (62,5%) | 5/5 (100%) | 3/5 (60%) | No cumple |
| V02 | 8 | 8 (100%) | 5/5 (100%) | 5/5 (100%) | 4/4 (100%) | 4/4 (100%) | Cumple |
| V03 | 7 | 7 (100%) | 5/5 (100%) | 5/5 (100%) | 3/3 (100%) | 3/3 (100%) | Cumple |
| V04 | 7 | 5 (71,4%) | 4/5 (80%) | 4/5 (80%) | 2/3 (66,7%) | 2/3 (66,7%) | No cumple |
| **Total** | **38** | **32 (84,2%)** | **22/23 (95,7%)** | **19/23 (82,6%)** | **14/15 (93,3%)** | **12/15 (80%)** | **No cumple** |

No se aceptaron afirmaciones inventadas: **0 alucinaciones aceptadas**. Hubo
3 controles parciales, 1 incorrecto y 0 controles omitidos. `Contenido
localizado` cuenta sólo controles completos o parciales; una interpretación
incorrecta no se considera localizada de forma segura.

## Comparación con v2

| Métrica | v2 | v3 | Variación |
|---|---:|---:|---:|
| Evidencias válidas | 31/41 (75,6%) | 32/38 (84,2%) | +8,6 puntos |
| Controles completos | 13/23 (56,5%) | 19/23 (82,6%) | +26,1 puntos |
| Críticos completos | 7/15 (46,7%) | 12/15 (80%) | +33,3 puntos |
| Alucinaciones aceptadas | 0 | 0 | Sin cambio |

V3 quedó a un control completo de superar el 85% general: 20/23 equivaldría a
87%. Sin embargo, aun alcanzándolo seguiría incumpliendo el requisito separado
de 100% para controles críticos.

## Hallazgos

### V01

El anclaje local recuperó cinco controles completos que en v2 habían quedado
parciales. Persisten tres resultados parciales: distribución completa de gastos,
procedimiento de reparaciones urgentes y aviso de 72 horas. Gemini entendió los
tres, pero sus citas cambiaron caracteres del PDF y el backend las rechazó. El
bloqueo es correcto: el significado no debe entrar automáticamente sin evidencia
trazable.

### V02 y V03

Ambos documentos cumplieron todos sus controles. V02 preservó incluso una
alternativa contradictoria `tendrá/no tendrá` como contexto y revisión humana.
V03 unió correctamente la cláusula de modificaciones entre páginas, mantuvo sus
excepciones y no inventó un plazo de aviso.

### V04

La continuidad de la cláusula quinta entre páginas funcionó. La cláusula sexta
sigue siendo el defecto semántico principal: pese a la instrucción de v3, Gemini
resolvió que los gastos comunes están a cargo del locador. La redacción admite
más de una lectura y debía quedar con responsable `no_especificado`, uso
`contexto` y explicación de la ambigüedad. Las dos propuestas rechazadas de V04
eran contexto ajeno a los controles y no redujeron la cobertura esperada.

## Conclusión

V3 demuestra una mejora material y mantiene el comportamiento seguro: la
evidencia no literal se bloquea y no hubo alucinaciones aceptadas. No obstante,
**no cumple aún el criterio de aceptación de HU30**: obtuvo 82,6% completo frente
al 85% requerido y 80% crítico frente al 100% requerido.

No corresponde revelar H01-H02 ni declarar generalización final. El siguiente
ajuste debería ser pequeño y general, no una enumeración de estos contratos:

1. reforzar que cualquier coordinación dudosa de sujetos u objetos debe quedar
   en `contexto`, con `responsable: no_especificado`, aunque la cita sea literal;
2. pedir citas más cortas y continuas por cada regla para reducir cambios de OCR
   sin relajar el anclaje;
3. repetir V01-V04 una única vez con una versión nueva congelada antes de usar
   los holdouts.

## Evidencia

Los resultados crudos y las revisiones control por control están en
`resultados_corpus_v3/`. Cada archivo conserva modelo, versión, hashes, páginas,
propuestas válidas, descartes y motivos. La tasa de evidencia válida se reporta
separada de la precisión semántica.
