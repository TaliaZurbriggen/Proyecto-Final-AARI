# HU30 — comparación v9/V04: Flash frente a Flash-Lite (02/10/2026)

## Objetivo y autorización

Después del ensayo v9/Flash-Lite se aprobó comparar el mismo contrato público
V04 y el mismo prompt v9 con `gemini-3.5-flash`. Se autoriza una única
invocación del adaptador, sin reintentos manuales ni continuidad automática
con otros contratos. El resultado se conserva separado; no se sustituye la
evidencia de Flash-Lite.

Se elige Flash porque la integración existente ya lo contempla y admite el
mismo adaptador de salida estructurada. La [documentación del modelo](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash)
incluye soporte de function calling. Los [precios oficiales](https://ai.google.dev/gemini-api/docs/pricing)
publican un nivel gratuito, pero eso no demuestra disponibilidad de cuota de
esta cuenta. El intento previo v5/Flash recibió 503; no se confunde con un
fallo semántico ni se reutiliza aquel checkpoint.

## Variable que cambia y constantes

Cambia sólo el modelo configurado: de `gemini-3.5-flash-lite` a
`gemini-3.5-flash`. No se modifican el prompt, el texto, el esquema,
function calling, el adaptador, las fuentes locales ni los controles. El
registro y su ubicación son diferentes para conservar ambos ensayos.
Los modelos pueden tener comportamientos internos distintos por defecto;
esta prueba no iguala ni observa esos procesos internos.

- Fuente V04: 4.709 caracteres; prompt enviado: 11.167 caracteres.
- Prompt v9 SHA-256: `cd1329993efe6187698281426454095cf4bf499755b6b7998e7469f9f707341e`.
- Texto extraído SHA-256: `18f6fd085061b0f0979ce4025971664a40c3e446c920ca3ef7a17b9c03ba2385`.
- Resultado Lite de referencia SHA-256: `b39a2f6343fcc75a1bdc0c613717a86ce0b37551f266c2cbb017d0a5d0058f1d`.
- Umbrales: 85% general completo, 100% crítico completo y cero propuestas
  con interpretación no respaldada aceptadas.

## Implementación y comprobaciones locales

`backend/scripts/evaluate_contract_clause_v9_comparison.py` usa un manifiesto
y directorio separados. Sólo admite V04. Antes de llamar exige coincidencia
con el ensayo Lite en documento, texto extraído, caracteres de entrada,
versión del prompt, idioma OCR y hashes de los archivos congelados. Exige
una referencia Lite completada con fuente preservada y un resultado nuevo.
El checkpoint previo evita repetir una ejecución ya iniciada, fallida o
terminada. Las credenciales se leen de un `.env` local y nunca se registran.

`corpus_v9_flash_manifest.json` conserva todos los hashes del manifiesto v9
y congela además el ejecutor comparativo. Los originales no se editaron.
`backend/tests/test_contract_clause_v9_comparison.py` agrega 17 pruebas con
dobles: control de la única variable, rechazo de entradas y manifiestos
distintos, protección del registro Lite y configuración idéntica del adaptador.

Validaciones desde `backend`, sin API externa:

```text
python -m pytest -q --tb=no tests/test_contract_clause_v9_comparison.py tests/test_contract_clause_v9.py
26 passed

python -m pytest -q --tb=no
402 passed, 23 skipped, 2 warnings

python scripts/evaluate_contract_clause_v9_comparison.py --document V04
external_calls: 0; entrada idéntica a la referencia Lite
```

Los avisos son de dependencias Starlette/httpx y datetime/SQLite. `git diff
--check` y la revisión de formato de archivos nuevos no detectaron problemas.
El chequeo de patrones de credenciales no encontró coincidencias en los
archivos creados. Los dobles no prueban precisión del modelo.

## Resultado externo

La única invocación autorizada terminó en `ServerError`, HTTP **503**, sin
propuestas ni cláusulas evaluables. El [checkpoint seguro](resultados_v9_flash/resultado_v04_v9_flash.json)
conserva estado `failed`, modelo, hashes, horarios y tipo/código del error,
sin mensaje privado ni credenciales. No hubo reintento manual. Se configuró
`max_retries=1`, pero el registro no verifica de forma independiente el número
de intentos HTTP internos de la biblioteca.

No puede calcularse precisión ni determinarse si Flash mejora la interpretación
de v9. El 503 no cuenta como un fallo de clasificación ni altera las métricas
Lite anteriores: 3/5 completos, 1/3 críticos y dos propuestas no respaldadas.
Google identifica 503 como `UNAVAILABLE` en su [guía de errores](https://ai.google.dev/gemini-api/docs/troubleshooting);
este registro no demuestra agotamiento de cuota ni determina la causa interna
de la indisponibilidad.

El hash del resultado Lite se comprobó de nuevo tras el intento y sigue siendo
`b39a2f6343fcc75a1bdc0c613717a86ce0b37551f266c2cbb017d0a5d0058f1d`:
la evidencia de referencia permanece intacta. No se enviaron V01-V03.

## Alternativa pendiente de aprobación

No relanzar el checkpoint fallido ni cambiar producción. Una opción es otra
comparación aislada con `gemini-3.8-flash`, conservando v9 y V04 y registrando
un intento independiente. Google lo [incluye en su catálogo](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
y [publica nivel gratuito](https://ai.google.dev/gemini-api/docs/pricing), pero
no se comprobó el acceso ni la cuota real de la cuenta para ese modelo.
Requiere aprobación antes de preparar su ejecutor/manifiesto y consumir una
nueva invocación. No se llamó a 3.8 ni se implementó ese cambio en esta tanda.

## Alcance y límites

Una ejecución por modelo no permite medir variabilidad, garantizar mejora
estable ni demostrar generalización. Incluso si V04 supera los criterios,
V01-V03 y los holdouts H01-H02 continúan pendientes y requerirán el acuerdo
correspondiente. H01-H02 no se inspeccionan ni se transmiten en esta prueba.

No se cambió producción, el modelo de reclamos, Supabase ni la política de
activación humana. No se hizo commit/push/PR o cierre de Jira. La documentación
permanece en el repositorio mientras Notion esté limitado.
