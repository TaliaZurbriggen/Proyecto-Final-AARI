# HU30 — ensayo v9/V04 con Gemini 3.8 Flash (02/10/2026)

## Autorización y constantes

La persona responsable aprobó preparar un registro separado y ejecutar una
única invocación del adaptador a `gemini-3.8-flash`, sin reintentos manuales.
Se conservan exactamente el contrato público V04, prompt v9, esquema de salida,
function calling, adaptador, materialización local y cinco controles del ensayo
Flash-Lite. No se transmitió un contrato privado ni se enviaron V01-V03.

El preflight comprobó:

- 4.709 caracteres de fuente y 11.167 de prompt.
- Prompt SHA-256: `cd1329993efe6187698281426454095cf4bf499755b6b7998e7469f9f707341e`.
- Texto extraído SHA-256: `18f6fd085061b0f0979ce4025971664a40c3e446c920ca3ef7a17b9c03ba2385`.
- Referencia Lite SHA-256: `b39a2f6343fcc75a1bdc0c613717a86ce0b37551f266c2cbb017d0a5d0058f1d`.
- Umbrales sin cambios: 85% general completo, 100% crítico y cero
  interpretaciones no respaldadas aceptadas.

## Implementación y pruebas locales

`backend/scripts/evaluate_contract_clause_v9_flash38.py` y
`corpus_v9_flash38_manifest.json` son independientes de los ejecutores y
resultados anteriores. El manifiesto conserva los hashes anteriores y congela
el nuevo ejecutor con SHA-256
`f0cc97055988a6cb6f33de14d2863e14d014de387f6f2232e2299fe1b7dc4e13`.
Se usa el mismo evaluador v9, sin modificar su prompt ni la interpretación en
el backend. Sólo admite V04 y no repite un checkpoint existente.

Las pruebas comparativas existentes se parametrizaron para los ensayos 3.5 y
3.8, más una comprobación de separación de registros e igualdad de entradas.
No se editaron los ejecutores congelados anteriores. Desde `backend`, con
base en memoria y sin servicios externos:

```text
python -m pytest -q --tb=no tests/test_contract_clause_v9_comparison.py tests/test_contract_clause_v9.py
44 passed

python -m pytest -q --tb=no
420 passed, 23 skipped, 2 warnings

python scripts/evaluate_contract_clause_v9_flash38.py --document V04
external_calls: 0; entrada idéntica a la referencia Lite
```

Las advertencias locales son de Starlette/httpx y datetime/SQLite. Las pruebas
con dobles confirman selección de modelo, configuración del adaptador, hashes,
rechazo de cambios de entrada y protección de registros, no precisión de Gemini.

## Resultado externo

La única invocación terminó en `ServerError`, HTTP **503**. El
[checkpoint seguro](resultados_v9_flash38/resultado_v04_v9_flash38.json)
registra `state: failed`, modelo, hashes y código del error, sin mensajes
privados ni credenciales. No generó cláusulas ni propuestas evaluables. No hubo
reintento manual; `max_retries=1` está configurado, pero no se verifica de forma
independiente el número de intentos HTTP internos.

El hash de la referencia Lite se volvió a comprobar después del intento y
permanece intacto. No se sobreescribió el intento fallido de Flash 3.5.

| Ensayo v9/V04 | Resultado | Qué permite concluir |
|---|---|---|
| Flash-Lite 3.5 | Respuesta: 3/5 completos, 1/3 críticos, dos propuestas no respaldadas | Hay errores documentales de interpretación. |
| Flash 3.5 | HTTP 503, sin cláusulas | No permite evaluar precisión. |
| Flash 3.8 | HTTP 503, sin cláusulas | No permite evaluar precisión. |

No se reporta 0% de precisión para los modelos sin respuesta ni se alteran las
métricas Lite. El 503 no demuestra agotamiento de cuota, ni una clave inválida,
ni permite decidir entre indisponibilidad del servicio y un problema asociado
a la petición actual. No conocemos la causa interna. La [guía oficial](https://ai.google.dev/gemini-api/docs/troubleshooting)
identifica 503 como `UNAVAILABLE`.

## Diagnóstico posterior autorizado y ejecutado

Después se aprobaron dos invocaciones mínimas sin contratos: texto simple y,
sólo tras su respuesta, el mismo mensaje con un esquema de un campo. Ambas
respondieron `OK`. Ver [diagnóstico y evidencia](diagnostico_flash38_minimo_2026-10-02.md).
Esto confirma el funcionamiento de esas peticiones pequeñas, no del esquema
completo ni de la extracción. No se sobrescribió el 503 de este ensayo y su
causa sigue sin demostrarse. Luego se autorizó el diagnóstico con texto
sintético breve, prompt v9 y esquema completo; también recibió 503, sin
propuestas. Ver [resultado separado](diagnostico_flash38_esquema_completo_2026-10-02.md).

La generalización V01-V03 y los holdouts H01-H02 siguen pendientes. La HU no
se da por terminada. No se modificó producción, reclamos, Supabase ni la
activación humana; tampoco se hizo commit/push/PR ni cambios de estado de Jira.
La documentación queda en el repositorio mientras Notion esté limitado.
