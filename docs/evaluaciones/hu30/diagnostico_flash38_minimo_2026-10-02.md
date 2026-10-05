# HU30 — diagnóstico mínimo de Gemini 3.8 Flash (02/10/2026)

## Objetivo y autorización

Tras el HTTP 503 del ensayo v9/V04, se aprobó un máximo de dos invocaciones
pequeñas: texto simple y, sólo si respondía, el mismo mensaje con salida
estructurada. Se enviaron únicamente las palabras `Responde solamente OK.`.
No se transmitieron contratos, PDFs, datos personales ni contenido del proyecto.

Las dos invocaciones autorizadas se consumieron. No hubo reintentos manuales.
El adaptador usa `max_retries=1`; el número de intentos HTTP internos no se
verificó de manera independiente. No se ejecutará otra prueba externa sin una
nueva aprobación.

## Implementación aislada

`backend/scripts/diagnose_contract_model_flash38.py` conserva el modelo
`gemini-3.8-flash` y la configuración del adaptador en ambas pruebas. Sólo la
segunda añade `with_structured_output(..., method="function_calling")`, con
un esquema mínimo que contiene un campo de texto, `respuesta`. **No es el
esquema completo de extracción de cláusulas.**

El ejecutor escribe un checkpoint antes de invocar, impide repetir archivos
existentes y omite la segunda prueba si la primera falla o no devuelve texto.
Los registros guardan únicamente metadatos y la respuesta segura `OK`;
cualquier texto inesperado o mensaje completo de error queda fuera del archivo.

- Script SHA-256: `6edd1aabfc59d8e92e5aecc1d9671d776faa234b73f24468d0c7af8909eed90c`.
- `langchain-google-genai`: 4.3.2.
- `google-genai`: 2.14.0.

## Resultados externos

| Prueba | Resultado | Duración registrada | Evidencia |
|---|---|---|---|
| Texto simple | Respondió `OK` | 3,519 s | [plain.json](diagnostico_flash38_minimo/plain.json) |
| Salida estructurada mínima | Respondió `OK` en el campo esperado | 13,394 s | [structured.json](diagnostico_flash38_minimo/structured.json) |

Ambos checkpoints tienen `state: completed`, `expected_ok: true` y una
invocación del adaptador. Se ejecutaron entre las 15:16:09 y 15:16:26 UTC.

Esto confirma que la clave, el acceso al modelo y el adaptador **funcionaron
en estas dos solicitudes mínimas**. El ensayo con V04 permanece fallido e
intacto; estas respuestas no generan cláusulas ni métricas de precisión.

No prueba disponibilidad sostenida, cuota futura, aceptación del esquema
completo ni calidad de extracción. Tampoco permite atribuir el 503 anterior
al tamaño del contrato o al esquema: una indisponibilidad transitoria sigue
siendo una explicación posible.

## Inspección local del esquema de cláusulas

Sin cliente, clave ni llamada externa, se convirtió `SourceClauseBatch` con
`convert_to_genai_function_declarations` del adaptador instalado.

- Conserva el campo raíz `clausulas` y los nueve campos de cada propuesta:
  `tramo_id`, `titulo`, `resumen`, `categoria`, `responsable`,
  `uso_clasificador`, `condiciones`, `referencias` y `confianza`.
- Conserva los seis campos requeridos y los valores enumerados de categoría,
  responsable y uso.
- No quedan referencias `$ref` ni definiciones `$defs` en el esquema convertido.
- Las advertencias sobre `$defs` y `additionalProperties` no prueban pérdida de
  los campos anidados: el adaptador resuelve las referencias antes de convertir.
  La prohibición de campos adicionales sigue validándose localmente con Pydantic;
  esa restricción no se transmite como `additionalProperties` en este esquema.

Esta inspección no acredita equivalencia de todas las restricciones del esquema
ni aceptación real por Gemini. No se cambió el esquema para ocultar advertencias.

## Validación local

Desde `backend`, con `DATABASE_URL=sqlite+pysqlite:///:memory:` y sin servicios
externos:

```text
python -m pytest -q --tb=no tests/test_contract_model_diagnostic.py
9 passed

python -m pytest -q --tb=no
429 passed, 23 skipped, 2 warnings

python scripts/diagnose_contract_model_flash38.py
external_calls: 0
```

Las nueve pruebas específicas verifican el orden condicionado, omisión tras
fallo o respuesta vacía, ausencia de reintentos manuales, protección de
checkpoints, configuración común, checkpoint previo y registros seguros.
Las dos advertencias de la suite corresponden a Starlette/httpx y datetime/SQLite.
Las pruebas con dobles no miden precisión del modelo.

## Paso posterior autorizado y ejecutado

Se aprobó una única solicitud con el **esquema completo** de cláusulas, prompt
v9 y texto contractual sintético breve, manteniendo el adaptador y modelo.
Terminó en HTTP 503, sin propuestas evaluables. Ver
[registro separado y límites del diagnóstico](diagnostico_flash38_esquema_completo_2026-10-02.md).
No cambia las dos respuestas `OK` anteriores ni permite establecer la causa
del fallo o la calidad generalizable de extracción.

No se modificó producción, el prompt v9, los controles ni los resultados
anteriores. Supabase no se utilizó. La regresión V01–V03 y los holdouts
H01–H02 siguen pendientes; la HU no se da por terminada. No se hizo commit,
push, PR ni cambio de Jira. El registro queda en el repositorio mientras
Notion continúe limitado, conforme al acuerdo del Sprint 3.
