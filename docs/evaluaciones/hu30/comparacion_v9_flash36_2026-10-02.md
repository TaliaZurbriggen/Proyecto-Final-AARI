# HU30 — extracción V04 con Gemini 3.6 Flash (02/10/2026)

## Pedido y alcance

Ante el cierre del Sprint 3 previsto para el 07/10 y los fallos de Flash 3.8,
la persona responsable pidió probar otro modelo para obtener cláusulas.
Se eligió `gemini-3.6-flash`: la [ficha oficial](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash)
documenta salida estructurada y la [tabla de precios](https://ai.google.dev/gemini-api/docs/pricing)
incluye modalidad gratuita. Eso no garantiza cuota disponible ni generación
exitosa para este proyecto. No se activó facturación ni se modificó `.env`.

Se realizó una única invocación del contrato público V04 con el pipeline v9
existente. No se creó ni editó código de aplicación, se cambió el prompt o
se adoptó otro modelo en producción. Se mantuvo `function_calling`; no se
ejecutó la alternativa JSON nativa propuesta anteriormente.

## Documento y privacidad

V04 es el modelo contractual de las páginas 8–9 de una resolución pública
de DGN, no el contrato personal proporcionado al inicio de HU30. Su procedencia
está documentada en [corpus_v2.md](corpus_v2.md) y el manifiesto identifica
`output/pdf/hu30_corpus/validation/V04_modelo_inmueble_dgn_paginas_8_9.pdf`.

Se verificó SHA-256 `a921c2a9db516211b82398c52ad937e7a881d0ec6d248334fdf6d483bd303d1c`
contra el manifiesto y la referencia previa. La consulta nueva a la fuente
pública no respondió dentro del plazo de la herramienta; se utilizó la copia
local previamente preparada y verificada, sin sustituirla por otra descarga.

La primera solicitud de ejecutar el proceso fue bloqueada por la revisión de
permisos antes de enviar datos. Después de comprobar procedencia, hash y
ausencia de un resultado, se volvió a solicitar la misma operación por el
mismo mecanismo, describiendo expresamente documento público y destino.
La revisión permitió ejecutarla. El bloqueo previo no consumió Gemini.

## Comparación controlada

La preparación comprobó los archivos congelados y reutilizó
`validate_same_input` frente al ensayo Flash-Lite v9/V04. Sólo cambió el modelo.

- Fuente: dos páginas digitales completas, 4.709 caracteres.
- Prompt: v9 experimental, 11.167 caracteres, sin cambios de instrucciones.
- Adaptador y esquema: los existentes, `SourceClauseBatch` / `function_calling`.
- Evidencia: materialización desde fragmentos locales completos.
- Controles: los cinco de V04, sin retirarlos ni modificar umbrales.
- Paquetes: `langchain-google-genai` 4.3.2 y `google-genai` 2.14.0.
- Resultado en directorio nuevo, protegido por checkpoint previo a invocar.

## Resultado externo

La única invocación terminó en `ServerError`, HTTP **503**; no produjo
cláusulas ni propuestas que puedan revisarse. Ver
[checkpoint separado](resultados_v9_flash36/resultado_v04_v9_flash36.json).

Inicio: 17:56:13 UTC; final: 17:56:18 UTC, aproximadamente 4,02 segundos entre
las marcas. `adapter_invocations: 1`. No hubo reintento manual ni se repitió
el intento con Flash 3.8. `max_retries=1`; no se verifica independientemente
el número de intentos HTTP internos del SDK.

No se reporta 0% de precisión: sin propuestas no es posible aplicar la revisión
semántica. El 503 no demuestra clave inválida, cuota agotada ni fallo causal
del prompt o esquema. Tampoco permite afirmar que otro modelo siempre esté
indisponible. Los resultados anteriores permanecen intactos.

## Comprobaciones y continuidad

Se usaron exclusivamente funciones del pipeline existente. La preparación y
los hashes aprobaron antes de llamar. La suite vigente sin servicios externos
es `python -m pytest -q --tb=no`: 450 aprobadas, 23 omitidas y dos advertencias
conocidas (Starlette/httpx y datetime/SQLite). No se atribuyen a esta prueba
pruebas nuevas ni una nueva ejecución de la suite.

Después se recibió autorización específica para una única extracción de V04
con `gemini-3.1-flash-lite`. Se ejecutó y también recibió HTTP 503 sin
propuestas. Ver [registro 3.1 y propuesta de continuidad](comparacion_v9_flash31lite_2026-10-02.md).
No se programó rotación automática ni quedan llamadas adicionales autorizadas.

La inspección posterior sin Gemini reconoce las 12 cláusulas de V04 y conserva
la continuación de QUINTA entre páginas. Se propone habilitar la extracción
literal y revisión humana como un modo explícito independiente de la IA.
Ese cambio de arquitectura o producto sigue pendiente de aprobación; no
autoriza bajar umbrales, declarar aprobada la interpretación semántica ni
cerrar la HU por la proximidad del Sprint.

No se utilizó Supabase ni se hizo commit, push, PR, carga de horas o cambios
de Jira. La evidencia continúa en el repositorio conforme al acuerdo de
documentación del Sprint 3.
