# HU30 — esquema completo con texto sintético (02/10/2026)

## Alcance aprobado

Se autorizó una única invocación a `gemini-3.8-flash`, con el esquema completo
`SourceClauseBatch` y un texto contractual breve inventado. Se conservaron
el prompt v9 completo, el adaptador, `function_calling`, `max_retries=1` y la
materialización de evidencia local. La diferencia respecto del ensayo v9/V04
es la fuente: dos reglas sintéticas en lugar del contrato público completo.

No se transmitió ningún PDF, contrato real ni dato personal. No se modificó
producción ni se cambió el esquema para evitar advertencias. El ejemplo no
forma parte del corpus, no cambia los controles y no cuenta para sus métricas.

## Entrada y trazabilidad

La fuente contiene 140 caracteres y una página sintética:

> PRIMERA: El locador debe reparar las filtraciones del techo.
> SEGUNDA: El locatario debe reparar los daños que haya causado por uso indebido.

La primera atribuye la reparación del techo al propietario; la segunda atribuye
al inquilino los daños que él haya causado por uso indebido. Estas son lecturas
del texto inventado, no reglas jurídicas aplicables a contratos reales.

- Prompt construido: 6.251 caracteres, incluidos los dos tramos de fuente.
- Esquema: `SourceClauseBatch`, sin simplificar sus nueve campos por propuesta.
- Fuente SHA-256: `f5f64fe476c1697d50e08e2e2f2713668a4307b54a8159c9447b9aad252a0831`.
- Prompt construido SHA-256: `ba0ce1b0b4b86b0f8993dcac2068ae97c94e68f8eb9be03db905b825fce8d21e`.
- Esquema Pydantic SHA-256: `cfafb5b9cd18763a44847df1d84a3aaec4ad2ec8c3253274e30a74be07ea9853`.
- Script SHA-256: `c1513da2f5f69ed5d7c632ecb09adfb8135b59ef727f5085c4b41e47c0ef8cf9`.
- Paquetes: `langchain-google-genai` 4.3.2 y `google-genai` 2.14.0.

El ejecutor `backend/scripts/diagnose_contract_schema_flash38.py` verifica el
manifiesto congelado antes de usar el modelo. Reutiliza el evaluador v9 y el
registro existente, que guarda el checkpoint antes de invocar. Impide repetir
cualquier resultado existente, incluso si está iniciado o fallido.

## Resultado externo

La única invocación terminó en `ServerError`, HTTP **503**, sin cláusulas ni
propuestas evaluables. El [checkpoint separado](diagnostico_flash38_esquema_completo/resultado.json)
conserva los hashes, entrada sintética, versiones, tiempos y código seguro del
error. No guarda el mensaje completo de la excepción ni credenciales.

Comenzó a las 16:44:13 UTC y finalizó a las 16:44:41 UTC: aproximadamente
27,54 segundos entre ambas marcas. `adapter_invocations: 1`; no hubo reintento
manual. El número de intentos HTTP internos no se comprobó independientemente.

| Solicitud a Flash 3.8 | Entrada / esquema | Resultado |
|---|---|---|
| Diagnóstico mínimo de texto | Mensaje `OK`, sin esquema | Respondió `OK` |
| Diagnóstico mínimo estructurado | Mensaje `OK`, un campo | Respondió `OK` |
| Ensayo v9/V04 | Prompt completo, contrato público, esquema completo | HTTP 503 |
| Este diagnóstico | Prompt completo, dos reglas sintéticas, esquema completo | HTTP 503 |

El error también ocurre sin un contrato largo: reducir únicamente la fuente
no produjo una respuesta en este intento. Esto **no demuestra** que el esquema
sea inválido, que el prompt cause el fallo o que se haya agotado la cuota.
Las solicitudes se ejecutaron en momentos diferentes; no podemos descartar
indisponibilidad transitoria. Las respuestas mínimas anteriores continúan
válidas, pero no acreditan que la extracción completa funcione.

Las advertencias locales de `$defs` y `additionalProperties` volvieron a
aparecer. La [inspección previa](diagnostico_flash38_minimo_2026-10-02.md)
confirmó la presencia de los nueve campos después de convertir el esquema;
no se presenta esa inspección como aceptación por el proveedor.

## Pruebas locales

Desde `backend`, con base SQLite en memoria y sin APIs externas:

```text
python -m pytest -q --tb=short tests/test_contract_schema_diagnostic.py tests/test_contract_model_diagnostic.py
18 passed

python -m pytest -q --tb=no
438 passed, 23 skipped, 2 warnings

python scripts/diagnose_contract_schema_flash38.py
external_calls: 0
```

Las nueve pruebas nuevas cubren conservación del pipeline y fuente, esquema
completo, checkpoint anterior al modelo, una única invocación, protección de
los tres estados de registro, errores seguros, respuesta malformada y rechazo
de un modelo distinto en la preparación. Las dos advertencias conocidas de
la suite son Starlette/httpx y datetime/SQLite. `git diff --check` no reportó
problemas; la búsqueda de patrones de credenciales en los archivos nuevos
no encontró coincidencias.

## Diagnóstico posterior autorizado y ejecutado

Se aprobó separar el prompt del esquema: conservar el esquema completo,
modelo y texto sintético, pero probar instrucciones mínimas en un registro
distinto. La única invocación también recibió HTTP 503, sin cláusulas.
Ver [resultado del prompt breve](diagnostico_flash38_prompt_breve_2026-10-02.md).
No usó el prompt v9 ni midió su precisión; tampoco demuestra causalidad.

No se repitió este intento ni el de V04. La regresión V01–V03, los holdouts
H01–H02 y la precisión de extracción siguen pendientes. La HU no está lista
para cerrar. No se utilizó Supabase, ni se hizo commit/push, PR o cambios de
Jira. Se mantiene la documentación local mientras Notion esté limitado.
