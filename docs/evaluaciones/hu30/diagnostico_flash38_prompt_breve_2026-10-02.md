# HU30 — esquema completo con instrucciones breves (02/10/2026)

## Autorización y alcance

Se aprobó una única invocación a `gemini-3.8-flash`, con el mismo esquema
`SourceClauseBatch`, adaptador, `function_calling` y fuente sintética del
[diagnóstico anterior](diagnostico_flash38_esquema_completo_2026-10-02.md).
El único cambio previsto en la petición fue sustituir el prompt v9 por
instrucciones breves. No es una versión nueva del prompt de extracción ni
una modificación de producción.

El primer intento de iniciar el proceso fue bloqueado por la revisión
automática de permisos **antes de ejecutarlo**: no consumió Gemini ni generó
checkpoint. Después de la indicación de continuar, se comprobó que no hubiera
evidencia y se solicitó de nuevo la ejecución por el mismo mecanismo de
permisos, sin eludir la revisión. Ese proceso sí hizo la única invocación.

No se enviaron PDFs, contratos reales, datos personales o controles esperados.
No se hicieron reintentos manuales. `max_retries=1`; el número de intentos HTTP
internos no se comprobó de manera independiente.

## Comparación verificada antes de llamar

| Elemento | Intento anterior | Este diagnóstico |
|---|---|---|
| Modelo | Gemini 3.8 Flash | Idéntico |
| Esquema | SourceClauseBatch completo | Idéntico |
| Adaptador / método | LangChain / function_calling | Idénticos |
| Fuente | Dos reglas sintéticas, 140 caracteres | Idéntica |
| Petición de texto completa | 6.251 caracteres, prompt v9 | 504 caracteres, instrucciones breves |

La fuente mantiene reparación de filtraciones del techo a cargo del locador
y reparación de daños por uso indebido causados por el locatario. No se agregó
contenido ni se retiró una condición para lograr una respuesta.

Las instrucciones breves piden extraer reglas, identificar su tramo, conservar
responsable y condiciones explícitos, no inventar reglas y no devolver citas
ni páginas, que siguen materializándose desde la fuente local.

- Fuente SHA-256: `f5f64fe476c1697d50e08e2e2f2713668a4307b54a8159c9447b9aad252a0831`.
- Esquema Pydantic SHA-256: `cfafb5b9cd18763a44847df1d84a3aaec4ad2ec8c3253274e30a74be07ea9853`.
- Prompt breve SHA-256: `2dfcb921eb0aa7ccfaa87fc4da063311652926879d6de1acc51ae87e1419e5e8`.
- Script SHA-256: `e3865b48f31f18e8bc40aaaf086d0f1928ec4f4b66e0fe52f177a8474dda97f4`.
- Referencia anterior SHA-256: `ad0dcfae4a36857415d1023f95e517c7c491894d182b52856aee3a1fcb92ef95`.
- Paquetes sin cambios: `langchain-google-genai` 4.3.2 y `google-genai` 2.14.0.

`backend/scripts/diagnose_contract_short_prompt_flash38.py` verifica esos
elementos de referencia, guarda evidencia previa a la invocación y rechaza
cualquier checkpoint ya existente, incluso fallido. No edita los ejecutores
anteriores ni reemplaza resultados del modelo por respuestas esperadas.

## Resultado

La única invocación terminó en `ServerError`, HTTP **503**. No produjo
cláusulas ni propuestas evaluables. Evidencia:
[checkpoint independiente](diagnostico_flash38_prompt_breve/resultado.json).

Inicio: 17:45:29 UTC; final: 17:45:35 UTC. Aproximadamente 6,36 segundos entre
las marcas registradas. `state: failed`, `adapter_invocations: 1` y
`real_contracts_sent: 0`. No se guarda el mensaje completo de la excepción
ni credenciales. Las advertencias locales del convertidor de esquema
reaparecieron; no se las presenta como causa demostrada del 503.

Acortar las instrucciones tampoco resolvió el fallo en esta ocasión. Junto
con los intentos anteriores, esto muestra que cambiar únicamente la longitud
del contrato o del prompt no bastó. **No establece causalidad**: no demuestra
esquema inválido, clave incorrecta, agotamiento de cuota ni indisponibilidad
permanente. Las pruebas mínimas que respondieron `OK` y los intentos fallidos
se ejecutaron en momentos diferentes.

No se calcula 0% de precisión por falta de respuesta ni se cambia el corpus.
Se cierra esta secuencia de comprobaciones sin repetir la solicitud ni enviar
otro contrato. La extracción sigue sin validación externa satisfactoria.

## Pruebas locales

Desde `backend`, con `DATABASE_URL=sqlite+pysqlite:///:memory:` y sin APIs:

```text
python -m pytest -q --tb=short tests/test_contract_short_prompt_diagnostic.py tests/test_contract_schema_diagnostic.py tests/test_contract_model_diagnostic.py
30 passed

python -m pytest -q --tb=no
450 passed, 23 skipped, 2 warnings

python scripts/diagnose_contract_short_prompt_flash38.py
external_calls: 0; prompt_characters: 504; baseline_prompt_characters: 6251
```

La suite completa se volvió a ejecutar después de retomar y dio el mismo
resultado. Las doce pruebas nuevas cubren constantes de comparación, fuente
conservada, instrucciones distintas, checkpoint antes de invocar, protección
de los tres estados, una invocación sin reintento, errores seguros, salida
malformada y lista vacía sin presentarla como extracción correcta. Las dos
advertencias conocidas son Starlette/httpx y datetime/SQLite. Estas pruebas
con dobles no miden precisión de Gemini.

## Alternativa estudiada, no implementada ni ejecutada

La biblioteca instalada admite otra ruta, `with_structured_output(...,
method="json_schema")`, que utiliza JSON nativo en lugar de una llamada de
herramienta. Se inspeccionó su implementación local: vincula
`response_mime_type="application/json"` y `response_json_schema`, con
validación Pydantic de la respuesta.

La [documentación oficial de salida estructurada](https://ai.google.dev/gemini-api/docs/structured-output)
distingue el formato JSON de la respuesta de las llamadas de herramientas,
limita las características de esquema compatibles y exige validación en la
aplicación. Esto justifica estudiar la alternativa, **no garantiza** que
responda ni que corrija la interpretación de cláusulas.

Hay un antecedente importante: el [ensayo del 28/09](diagnostico_interactions_2026-09-28.md)
con JSON nativo por Interactions, Flash 3.5 y esquema v4 recibió HTTP 400.
No se ignora ese resultado ni se presenta JSON nativo como una solución ya
probada. El esquema de tramos actual y la ruta del adaptador son diferentes;
se debe revisar compatibilidad antes de otra llamada.

Propuesta siguiente: un ejecutor experimental separado y pruebas locales que
conserven los nueve campos y la validación estricta del backend; sólo después,
una solicitud sintética autorizada por JSON nativo. Sin reemplazar el adaptador
de producción, cambiar modelo de reclamos ni enviar documentos reales.
Requiere nueva aprobación para implementar y consumir cuota. Si vuelve a
fallar, conservar el error y detener el ensayo, sin reintentos ni saltos
automáticos entre modelos.

La HU no se da por terminada. Regresión V01–V03, holdouts H01–H02 y los umbrales
siguen pendientes. No se usó Supabase ni se hizo commit, push, PR o cambios de
Jira. La documentación continúa en el repositorio mientras Notion esté limitado.
