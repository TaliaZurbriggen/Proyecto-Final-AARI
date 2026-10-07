# HU30 — v7/V04 con referencias y evidencia local (02/10/2026)

## Resultado

Se hizo una invocación autorizada del adaptador a Flash-Lite con el modelo
público V04. Hubo 12 propuestas, 12 materializadas y ninguna referencia
inexistente o rechazada. Los hashes del prompt, pipeline y fuente se verificaron
antes de llamar. No hubo reintentos manuales. El resultado conserva propuestas
y correspondencias con los tramos locales; la cantidad de invocaciones no
demuestra un número independiente de peticiones HTTP internas.

La [revisión de controles](resultados_v7/revision_v04_v7.json) dio **4/5 completos
(80%)**, **2/3 críticos completos (66,7%)** y **dos propuestas con interpretación
no respaldada aceptadas**. Ambas provienen del mismo control E02. No cumple
85% general, 100% crítico y cero interpretaciones no respaldadas. Por la
condición de autorización, V01-V03 no se enviaron: sólo se utilizó una de las
cuatro invocaciones máximas previstas.

| Control | Estado | Hallazgo |
|---|---|---|
| E01 — reparaciones entre páginas | Completo | Fuente íntegra en ambas páginas y reparación a cargo del locador durante la vigencia. |
| E02 — gastos y ambigüedad | Incorrecto | Resuelve la excepción de gastos comunes y además atribuye su pago al locatario. |
| E03 — conservación y devolución | Completo | Recupera también acta e inventario; conserva excepciones. |
| E04 — seguridad | Completo | Incluye seguridad y normas municipales, ahora con evidencia completa. |
| E05 — modificaciones | Completo | Conserva autorización y el tratamiento particular de devolución, con evidencia completa. |

## Qué cambió respecto de v6

Obtener las citas en el backend resolvió la transcripción incompleta y las
páginas equivocadas. La evidencia de E01 y E03-E05 ya muestra todas sus
condiciones. Esto no valida automáticamente el resumen: SEXTA ahora cuenta
con toda la fuente y aun así recibió dos atribuciones inseguras. La evidencia
local demuestra procedencia y permite revisar; no es una prueba semántica.

El modelo también incluyó materias sin utilidad para reclamos. Marcó la
renovación como operativa y generó propuestas de precio y jurisdicción con uso
excluido. Debe reforzarse el alcance relevante y la necesidad de atribución
expresa antes de asignar un pago. La categoría semántica también sigue sujeta
a revisión de dominio.

## Conservación y publicación de evidencia

La captura original quedó preservada localmente en `tmp/hu30-v7-raw/`, ruta
ignorada por Git. La copia versionable del resultado retira únicamente el
pie de firmas de la cláusula 12, ajeno a los cinco controles, para no duplicar
identidades de la fuente pública. La redacción no modifica las propuestas del
modelo ni las evidencias de QUINTA-NOVENA y está señalada en
`publication_redactions`. El PDF fuente no cambió. No deben publicarse los
archivos originales del directorio temporal.

## Continuidad

No se habilita v7 en la app. El siguiente refinamiento conservará la evidencia
local y se limitará a las instrucciones de interpretación: asignación expresa,
prohibición de inferir un pagador por la eximición de otro, alcance de listas
con excepciones y omisión de contenido ajeno a reclamos. Se usarán ejemplos
artificiales distintos del corpus y se conservarán los controles históricos.
Una versión nueva requiere su propia congelación y autorización de prueba.
H01-H02 siguen reservados.

La suite local vigente pasó con 374 aprobadas y 23 omitidas. No se tocó Supabase,
ni se hizo commit, push, PR o cambio de Jira. El resultado queda en el repositorio
mientras Notion siga limitado.
