# HU30 — ensayo real v9/V04 (02/10/2026)

## Resultado

Tras la autorización específica se hizo una invocación del adaptador a
`gemini-3.5-flash-lite` sobre V04, modelo público de contrato. Gemini respondió
con cinco propuestas, todas materializadas con evidencia local completa. No
hubo referencias rechazadas ni reintentos manuales. Los hashes del manifiesto
y documento se comprobaron; el texto extraído coincide con v7/v8.

La [revisión documental](resultados_v9/revision_v04_v9.json) dio **3/5 completos
(60%)**, uno parcial y uno incorrecto; **1/3 críticos completos (33,3%)**, y
**dos propuestas con afirmaciones no respaldadas aceptadas**. No cumple 85%
general, 100% crítico y cero interpretaciones no respaldadas.

Se detuvo la tanda sin enviar V01-V03, como establecía la autorización
condicional. Se utilizó una de las cuatro invocaciones máximas autorizadas.
H01-H02 continúan reservados. Una invocación del adaptador no acredita por sí
sola el número de peticiones HTTP internas.

| Control | Estado | Hallazgo |
|---|---|---|
| E01 — reparaciones entre páginas | Parcial | Resumen y fuente correctos, pero condiciones incluye exclusiones del prompt ausentes de QUINTA. |
| E02 — alcance ambiguo de gastos | Incorrecto | Define gastos comunes como excepción y marca operativa, responsable condicional y confianza 0.9. |
| E03 — conservación y devolución | Completo | Incluye deterioros y excepciones, acta e inventario con evidencia íntegra. |
| E04 — seguridad | Completo | Conserva seguridad y normas municipales; categoría aviso requiere revisión aparte. |
| E05 — modificaciones | Completo | Conformidad previa y tratamiento particular de devolución, sin inventar restauración. |

## Errores y comparación

En E01, `condiciones` dice que se excluyen precios, mora y garantías financieras
«según las reglas de alcance». Eso es una instrucción para seleccionar qué
extraer, no una condición contractual de QUINTA. El resumen es correcto, pero
la propuesta completa no queda fiel a su fuente.

En E02, resumen y condiciones eligen una de las coordinaciones posibles y el
uso vuelve a ser operativo con confianza alta. `condicional` significa una
atribución clara sometida a una condición; no equivale a reconocer que el
alcance del texto es incierto. V8 mantenía este punto como contexto, sin
pagador definido y confianza 0.6, aunque tampoco lograba neutralidad completa.

E04 conserva el contenido esperado, pero `aviso` no representa bien una
prohibición de seguridad. Se registra aparte: los controles congelados no
especificaban categoría esperada y no se cambian después de ver la respuesta.

| Ensayo V04 | Completos | Críticos completos | Propuestas no respaldadas |
|---|---:|---:|---:|
| v7 / Flash-Lite | 4/5 | 2/3 | 2 |
| v8 / Flash-Lite | 4/5 | 2/3 | 1 |
| v9 / Flash-Lite | 3/5 | 1/3 | 2 |

Son resultados de una ejecución por versión, no promedios ni prueba de
estabilidad. V9 fue peor **en esta ejecución**; no permite atribuir la causa
a la longitud del prompt o concluir incapacidad del modelo. Las instrucciones
adicionales no garantizaron mejora. Seguir ajustando un único caso conocido
aumenta el riesgo de adaptación al corpus.

Las cinco propuestas originales quedan sin reescritura. La revisión es de
fidelidad documental, no de validez jurídica ni de reglas de Oikos. La
salvaguarda de activación humana sigue vigente: estos ensayos no habilitan
reglas automáticas en reclamos ni justifican rebajar los umbrales.

## Próximo diagnóstico propuesto, no ejecutado

Antes de agregar otro prompt largo, preparar una comparación que mantenga
entrada, esquema y controles y cambie una sola variable, por ejemplo el
modelo. Sería un diagnóstico de la configuración actual, no una prueba de
generalización. La regresión V01-V03 y los holdouts continúan necesarios.

Cambiar modelo, salida estructurada o separar extracción e interpretación
requiere primero propuesta y aprobación, con consumo de cuota explícito.
No se implementó ninguna alternativa ni se envió a otro modelo. No introducir
reglas basadas en cláusulas concretas ni respuestas esperadas en el backend.

## Validaciones y estado

La suite local previa pasó con **385 aprobadas, 23 omitidas y dos advertencias
de dependencias**; los cuatro preflights aprobaron. Hoy se hizo la llamada real
y la comparación de los cinco controles. Los dobles prueban el ejecutor y la
conservación de fuentes, no la comprensión de Gemini.

Cálculo reproducible sin API externa, desde `backend`:

```text
python scripts/evaluate_contract_clause_corpus.py --document V04 --manifest ../docs/evaluaciones/hu30/corpus_v9_manifest.json --score-review ../docs/evaluaciones/hu30/resultados_v9/revision_v04_v9.json
```

No se cambió código tras la congelación ni se escribió en Supabase. Tampoco
se activó v9 en producción ni se hizo commit/push/PR o cambios de Jira. La
documentación queda en el repositorio mientras Notion esté limitado.
