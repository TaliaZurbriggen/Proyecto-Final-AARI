# HU30 — ensayo v8/V04 (02/10/2026)

## Ejecución y resultado

Tras la autorización específica se ejecutó una invocación del adaptador a
`gemini-3.5-flash-lite` con V04, modelo público de contrato. Respondió con seis
propuestas, todas materializadas con evidencia local completa. No hubo
referencias rechazadas ni reintentos manuales. Se comprobaron los hashes del
manifiesto v8, la fuente y los archivos congelados; el texto extraído es el
mismo utilizado en v7. Una invocación del adaptador no acredita por sí sola
el número de peticiones HTTP internas.

La [revisión documental](resultados_v8/revision_v04_v8.json) dio:

- **4/5 controles completos (80%)** y uno parcial.
- **2/3 controles críticos completos (66,7%)**.
- **Una propuesta con interpretación no respaldada aceptada**: el alcance de
  la excepción de gastos comunes. No es una cita inventada ni una atribución
  de pago a un actor; es una elección sintáctica que debía quedar abierta.

No cumple los umbrales congelados: 85% general, 100% crítico y cero
interpretaciones no respaldadas. V01-V03 no se enviaron porque la autorización
condicionaba esas ejecuciones a que V04 aprobara. Se utilizó una de las cuatro
invocaciones máximas autorizadas. H01-H02 continúan reservados.

| Control | Estado | Evidencia de revisión |
|---|---|---|
| E01 — reparaciones entre páginas | Completo | Locador, conservación y aptitud para uso; fuente íntegra en páginas 1 y 2. |
| E02 — gastos y alcance ambiguo | Parcial | Reconoce ambigüedad y no asigna pagador, pero resumen y condiciones todavía incluyen gastos comunes como excepción definida. |
| E03 — conservación y devolución | Completo | Deterioros, excepción por buen uso y tiempo, acta e inventario; estos últimos quedan como contexto separado. |
| E04 — seguridad | Completo | Seguridad y normas municipales con fuente íntegra. |
| E05 — modificaciones | Completo | Conformidad previa y tratamiento particular de devolución, sin inventar restauración. |

## Mejora y límite respecto de v7

V8 ya no genera la regla de pago del locatario deducida de la eximición del
locador. SEXTA queda con `responsable: no_especificado`, `uso_clasificador:
contexto` y confianza 0.6. Tampoco genera renovación contractual como regla
operativa ajena al alcance. Las citas y páginas siguen completas.

El problema restante está en la consistencia de la interpretación. El resumen
reconoce una redacción parcialmente ambigua, pero presenta consumos y gastos
comunes como excepciones. El campo `condiciones` vuelve a poner ambos dentro
de la excepción sin describir las dos lecturas posibles. Esos indicadores de
prudencia no vuelven correcto el contenido de los demás campos. Por eso E02
no se cuenta como completo ni se retira del denominador.

Esta revisión es de fidelidad documental. No determina validez jurídica de la
cláusula ni confirma reglas de Oikos. Los seis resultados originales se
conservan sin sustituirlos por los resultados esperados.

## Continuidad propuesta

El siguiente ajuste debería comprobar coherencia **entre todos los campos**:
si el alcance queda incierto, tanto resumen como condiciones deben describir
la incertidumbre y no presentar una de las lecturas como la regla. No alcanza
con bajar la confianza o marcar contexto. Mantener la evidencia local y los
controles actuales; usar ejemplos artificiales ajenos al corpus. Una nueva
versión deberá congelarse y validarse separadamente, sin repetir v8 ni activar
sus resultados en la aplicación.

## Comprobaciones y estado

Antes de la llamada: suite local `pytest -q --tb=no`, **376 aprobadas y 23
omitidas**, y preflight de V01-V04 aprobado. Después: revisión de los cinco
controles y cálculo local con `evaluate_contract_clause_corpus.py
--document V04 --manifest ../docs/evaluaciones/hu30/corpus_v8_manifest.json
--score-review ../docs/evaluaciones/hu30/resultados_v8/revision_v04_v8.json`.
Este cálculo no llama a Gemini. No se cambió código tras la congelación.

V8 permanece experimental. No se escribió en Supabase ni se hizo commit,
push, PR, cierre de Jira o actualización de producción. La documentación queda
en el repositorio mientras Notion esté limitado.
