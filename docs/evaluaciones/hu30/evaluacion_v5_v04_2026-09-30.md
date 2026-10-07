# Ensayo experimental v5 sobre V04 — 30/09/2026

## Alcance y registro

Con autorización específica se hizo **una invocación del adaptador** de Gemini
`gemini-3.5-flash-lite` con el PDF público V04. No se enviaron contratos
privados ni los controles esperados. El archivo de [resultado íntegro](resultados_v5/resultado_v04_v5.json)
se guardó directamente en UTF-8, con las propuestas originales, aceptadas y
rechazadas. El [checkpoint y ejecutor](../../../backend/scripts/evaluate_contract_clause_v5.py)
impiden sobreescribirlo o repetir la llamada por accidente. El adaptador tiene
`max_retries=1`; el registro **no demuestra** cuántas peticiones HTTP internas
hubo. No se hizo ningún reintento manual.

El PDF conservó su SHA-256
`a921c2a9db516211b82398c52ad937e7a881d0ec6d248334fdf6d483bd303d1c`.
La lectura local obtuvo dos páginas digitales y 4.709 caracteres, reconstruidos
sin pérdidas en la entrada segmentada. El prompt experimental y el verificador
se identifican por sus hashes en el JSON. La ejecución terminó con cinco
propuestas, cinco aceptadas por el verificador de citas por tramo y ninguna
rechazada. **Aceptación técnica no equivale a corrección semántica.**

## Revisión documental

Se compararon QUINTA a NOVENA con el PDF y con los cinco controles validados
antes de este ensayo. La [revisión estructurada](resultados_v5/revision_v04_v5.json)
permite recalcular los porcentajes sin consultar a Gemini.

| Control | Estado | Observación |
|---|---|---|
| V04-E01 — reparaciones entre páginas | Completo | QUINTA recupera reparaciones necesarias del locador durante la vigencia y reconoce ambas páginas. Las citas guardadas son fragmentos, no el texto íntegro. |
| V04-E02 — impuestos y gastos comunes ambiguos | Incorrecto | SEXTA ya cita su propio tramo, pero el resumen trata la parte proporcional de gastos comunes como una excepción definida al pago del locador y la marca `operativa`. El control pide preservar la ambigüedad para revisión. |
| V04-E03 — mantenimiento y devolución | Completo | SÉPTIMA conserva deterioros, excepción por buen uso y tiempo, acta e inventario. |
| V04-E04 — seguridad | Completo | OCTAVA conserva seguridad de personas e instalaciones y normas municipales. La categoría `servicio` necesita revisión de dominio. |
| V04-E05 — modificaciones | Completo | NOVENA conserva autorización previa y ausencia de obligación de restaurar. La categoría `reparacion` necesita revisión de dominio. |

El resultado es **4/5 controles completos (80 %)** y **2/3 críticos (66,7 %)**.
Se contó **una interpretación no respaldada aceptada** en SEXTA. No alcanza los
umbrales congelados: al menos 85 % general, 100 % de críticos y cero
afirmaciones no respaldadas. La mejora frente al ensayo v4 con Flash-Lite
(2/5 y 1/3 críticos) es indicativa, no una comparación controlada de todas las
variables: cambiaron tanto la entrada/prompt como el verificador. V04 ya es un
caso conocido y por sí solo no demuestra generalización.

Las métricas se recalcularon con `evaluate_contract_clause_corpus.py
--document V04 --manifest docs/evaluaciones/hu30/corpus_v4_manifest.json
--score-review docs/evaluaciones/hu30/resultados_v5/revision_v04_v5.json`,
**sin llamada externa**. Ese comando reutiliza exclusivamente los controles y
umbrales congelados de v4; por ello su encabezado muestra `prompt_version: v4`
y el modelo histórico, aunque el resultado evaluado sea v5/Flash-Lite.

## Verificaciones finales

- La respuesta JSON es válida, conserva el texto fuente y no contiene caracteres
  de reemplazo `U+FFFD`, a diferencia de la captura anterior de consola.
- La suite local de backend, incluido OCR real en español, terminó con
  **351 pruebas aprobadas, 22 omitidas y dos advertencias de bibliotecas**.
  Las omitidas requieren autorización o entorno de integración externa.
- `git diff --check` no detectó problemas de formato. Una búsqueda de patrones
  de claves en los tres archivos nuevos de resultado/revisión/informe no halló
  coincidencias. No se registraron valores de `.env`.

## Decisión y pendientes

La v5 **permanece experimental**. Producción sigue usando v4 y no se habilita
la extracción automática para decisiones sobre reclamos. El problema que queda
no es de conectividad ni de citas cruzadas: el modelo todavía convierte una
redacción ambigua en una regla operativa. No conviene seguir ajustando el
prompt sólo para V04. El siguiente paso propuesto es una salvaguarda local que
mantenga en revisión las cláusulas ambiguas antes de cualquier uso operativo,
con pruebas de regresión, y después evaluar los demás documentos conocidos.
Esa decisión de diseño requiere acuerdo antes de implementarse. H01-H02 siguen
reservados. La revisión de categorías y alcance jurídico corresponde al equipo
y a Oikos; esta comparación documental no la sustituye.

La decisión queda aquí mientras Notion no admita nuevos bloques por su límite
gratuito. No se hizo commit, push, PR ni cambio de Jira en este ensayo.
