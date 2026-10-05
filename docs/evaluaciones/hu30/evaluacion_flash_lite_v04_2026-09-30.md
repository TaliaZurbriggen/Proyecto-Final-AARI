# Ensayo V04 con Gemini 3.5 Flash-Lite — 30/09/2026

## Alcance

Una invocación externa autorizada sobre el PDF **público** V04, por el adaptador
existente `generateContent` + `function_calling`, con `gemini-3.5-flash-lite` sólo
para este proceso. Se conservaron el prompt v4 y los archivos congelados; no se
enviaron controles esperados, contratos privados ni cambios de producción.
`max_retries=1` se configuró en el adaptador. El registro confirma una invocación
del adaptador, pero no permite demostrar el número de peticiones HTTP internas.

El documento verificado mantiene su SHA-256 original y se leyó completo: dos
páginas, 4.709 caracteres. Ambas páginas se inspeccionaron visualmente para
comparar las cláusulas QUINTA a NOVENA con la salida. La respuesta llegó en
9,846 segundos: cinco propuestas, cuatro aceptadas por el anclaje actual y una
rechazada. La salida íntegra y la revisión están en
[resultado](resultados_flash_lite_v4/resultado_v04_2026-09-30.json) y
[revisión](resultados_flash_lite_v4/revision_v04_2026-09-30.json).

**Limitación del registro:** la captura de consola reemplazó algunas tildes
por `U+FFFD` al transportar el JSON. Los conteos y la revisión visual de esta
corrida se conservan, pero ese archivo **no es apto para repetir el anclaje
literal**. No se reconstruyeron ni corrigieron citas a mano. Las pruebas
posteriores del nuevo verificador usan texto extraído localmente del PDF y
casos sintéticos, no ese registro degradado.

## Revisión contra los controles validados

| Control | Estado | Observación |
|---|---|---|
| V04-E01 — reparaciones del locador entre páginas | Omitido | El modelo propuso QUINTA, pero citó en la página 2 palabras que están en la página 1; el filtro descartó la propuesta. |
| V04-E02 — impuestos, consumos y gastos comunes ambiguos | Incorrecto | SEXTA pasó el filtro citando un fragmento de SÉPTIMA. El resumen atribuye gastos comunes al locador pese a la ambigüedad. `no_especificado`/`contexto` no neutraliza ese resumen. |
| V04-E03 — mantenimiento, devolución, excepción, acta e inventario | Completo | Dos propuestas de SÉPTIMA conservan los elementos esperados. |
| V04-E04 — seguridad y normas municipales | Omitido | No se extrajo OCTAVA. |
| V04-E05 — modificaciones con conformidad previa | Completo | Se conserva la autorización y la ausencia de obligación de restaurar. La categoría `reparacion` aún merece revisión de dominio. |

Según los umbrales congelados, la cobertura general es **2/5 = 40 %** y la de
controles críticos **1/3 = 33,3 %**. Se contó **una afirmación no respaldada en
una propuesta aceptada**: la atribución no neutral de los gastos comunes. El
resultado **no aprueba** los mínimos de 85 %, 100 % crítico y cero afirmaciones
no respaldadas. Los omitidos y rechazados permanecen en el denominador.

La aceptación técnica de cuatro propuestas no equivale a exactitud: el anclaje
actual comprueba que la cita exista en la página, pero **no que corresponda a la
cláusula identificada ni que respalde su resumen**. SEXTA/SÉPTIMA revela esa
brecha. Esta revisión es documental; no constituye interpretación jurídica ni
validación de reglas por Oikos.

## Consecuencia y próximos pasos propuestos

La conectividad dejó de ser el bloqueo principal: este modelo respondió a una
extracción real. No corresponde, sin embargo, sustituir el modelo de producción
ni pasar a H01-H02 con esta calidad. Antes de otra llamada se propone:

1. Hacer que el anclaje verifique el **tramo de la cláusula**, incluyendo
   continuaciones entre páginas, y no cualquier texto de la página. Una cita
   de SÉPTIMA no debe validar SEXTA.
2. Agregar pruebas locales de esas dos fallas y del tratamiento de una cita de
   continuación con paginación equivocada. Mantener el descarte conservador si
   no hay anclaje seguro; no inventar una cita corregida automáticamente.
3. Evaluar una forma de extraer por tramos ya segmentados para que el modelo
   trabaje con menos texto y citas exactas. Decidirla antes de implementarla,
   porque modifica el diseño de extracción y podría aumentar el número de
   llamadas/cuota si se hace externamente por tramo.
4. Sólo con una nueva aprobación de ejecución externa, repetir V04 y luego la
   regresión V01–V03; conservar H01-H02 reservados hasta pasar los umbrales.

No se hizo otra consulta a Gemini ni se cambió el código, el prompt, `.env` o el
modelo de reclamos para este ensayo. No hubo commit, push ni cierre de Jira.

## Corrección local posterior aprobada

La implementación del verificador por tramos se documenta en
[verificador por cláusula](verificador_tramos_2026-09-30.md). No modifica el
resultado experimental de arriba ni lo hace aprobar retroactivamente.
