# HU30 — Diagnóstico directo, sin herramientas (02/10/2026)

## Pregunta y autorización

Se buscó distinguir un fallo del proveedor de un problema en la integración o
en la salida estructurada. La persona responsable aprobó preparar y ejecutar
un diagnóstico aislado de hasta tres solicitudes, sólo con el contrato público
V04, sin reintentos, facturación, Supabase ni cambios en producción.

El PDF **ya se convierte a texto localmente** antes de usar Gemini. Este ensayo
tampoco envió un archivo PDF: envió el texto segmentado de sus dos páginas.
No se transmitió el contrato personal ni se inspeccionaron los holdouts.

## Diseño implementado

Se agregó `backend/scripts/diagnose_contract_direct_gemini.py`, separado del
servicio de la aplicación y de los ejecutores anteriores:

1. Biblioteca oficial `google-genai` directa, sin LangChain ni herramientas.
2. Primera etapa: texto de salida libre; el prompt pide JSON, pero la API no
   impone MIME ni esquema ni llamada a función.
3. Segunda etapa condicionada a recibir texto no vacío: MIME `application/json`,
   sin esquema. Si la primera respuesta usa Markdown, se conserva tal cual y
   no se presenta como JSON válido; la segunda etapa permite aislar el formato.
4. Tercera etapa sólo si el modo JSON produce propuestas utilizables: MIME JSON
   y esquema nativo inline, con los nueve campos de `SourceClauseProposal`.
5. Ante cualquier error de solicitud, incluida cuota, servicio o timeout,
   detener toda la secuencia. Nunca repetir una etapa ni probar otra después
   de un error.

Configuración: `gemini-3.8-flash`, Gemini Developer API `generateContent`,
`v1beta`, muestreo por defecto y timeout de 60 segundos. `HttpRetryOptions`
define `attempts=1`: incluye la solicitud original y desactiva los reintentos.
Hooks del transporte cuentan cada solicitud HTTP y su estado, sin guardar
claves, cabeceras ni mensajes de error completos. El límite total es tres.
Se escribe checkpoint exclusivo antes del cliente y se actualiza antes de
cada llamada; cualquier evidencia previa impide repetir el ensayo.

La validación Pydantic y la materialización local de texto/páginas se conservan.
El esquema nativo elimina referencias, títulos, defaults y límites de longitud
de strings del esquema transmitido; esos límites siguen obligatorios en la
validación local. Explicita todos los campos, sus enums y valores null.
Los resultados válidos de formato requieren después revisión semántica: no
se declara calidad por haber recibido JSON.

## Entrada congelada y límites de la comparación

- V04: copia pública DGN, dos páginas digitales, 4.709 caracteres originales.
- PDF SHA-256: `a921c2a9db516211b82398c52ad937e7a881d0ec6d248334fdf6d483bd303d1c`.
- Páginas extraídas SHA-256: `18f6fd085061b0f0979ce4025971664a40c3e446c920ca3ef7a17b9c03ba2385`.
- Prompt base v9 intacto: `cd1329993efe6187698281426454095cf4bf499755b6b7998e7469f9f707341e`.
- Prompt diagnóstico: 12.423 caracteres, SHA-256
  `03f669dddbab0b624e9835554da1c00eb989d7ecc9692c49dbaaf1b873164e25`.
- Esquema nativo SHA-256: `036818dcbba05888fa493e3778f59599b2bc9ba68a54127a6784df58a4906992`.
- Esquema local SHA-256: `cfafb5b9cd18763a44847df1d84a3aaec4ad2ec8c3253274e30a74be07ea9853`.

El prompt diagnóstico agrega instrucciones explícitas y el formato de salida
al v9, porque sin una herramienta el modelo necesita conocer los campos.
Ese prompt sería idéntico en las tres etapas. No contiene controles ni
respuestas esperadas. **No es una comparación de una única variable frente
a la corrida histórica con LangChain**, porque también cambia el adaptador
y la instrucción de formato. Sí permite comprobar si el error aparece aun
sin LangChain, herramientas ni formato impuesto por la API.

La preparación verificó todos los archivos congelados y la conservación
total del texto. Los antecedentes de JSON nativo que recibieron HTTP 400
se mantienen: no fueron reemplazados ni reinterpretados como éxitos.

## Resultado real

| Etapa | Resultado | Solicitudes HTTP |
|---|---|---:|
| Texto libre, sin herramientas | `ServerError`, HTTP 503 | 1 |
| MIME JSON | No ejecutada: se detuvo ante el 503 | 0 |
| Esquema JSON nativo | No ejecutada: se detuvo ante el 503 | 0 |

La solicitud comenzó a las **15:44:26 ART / 18:44:26 UTC** y finalizó a las
**15:44:40 ART / 18:44:40 UTC**, el 02/10/2026. Duración registrada:
**14,555 segundos**. Hubo una invocación del SDK, una solicitud HTTP verificada
y cero reintentos. No hubo respuesta de cláusulas ni revisión de los cinco
controles de V04. No corresponde calcular precisión o cobertura semántica.

Evidencia original: [checkpoint del diagnóstico](diagnostico_directo_flash38/resultado.json).

## Conclusiones y próximo paso, sin implementar

- La lectura del PDF no era una etapa ausente: la fuente ya llega como texto.
- El 503 también ocurrió sin LangChain ni `function_calling`; éstos **no son
  necesarios para reproducir este fallo**. Eso no demuestra que todas las
  configuraciones anteriores estén correctas.
- Este intento no demuestra falta de cuota, ni una caída global del servicio,
  ni que el contenido o la longitud del prompt sean la causa. Las respuestas
  mínimas anteriores se obtuvieron con entradas distintas y en otro momento.
- Los modos JSON quedan **preparados y probados con mocks, no validados
  externamente**. No deben activarse en producción basándose en este ensayo.
- No repetir el diagnóstico ni gastar las dos solicitudes no usadas con
  otro prompt/documento sin una autorización nueva: cambian el experimento.

Si se continúa la investigación, el siguiente ensayo útil sería una sola
cláusula pública y una instrucción breve, usando este transporte sin herramientas,
en lugar de repetir la extracción completa o rotar modelos sin aislar variables.
Debe mantener evidencia literal y validación local; no es una solución probada
ni autoriza cambiar el pipeline productivo. La propuesta previa de extracción
literal con revisión humana también sigue pendiente de aprobación.

## Pruebas y alcance de los cambios

Se agregaron 19 pruebas en `backend/tests/test_contract_direct_diagnostic.py`.
Usan el SDK oficial y `httpx.MockTransport`: no hacen red ni consumen cuota.
Cubren igualdad del prompt, ausencia de herramientas, nueve campos del esquema,
validación local estricta, evidencia literal, rechazos conservados, checkpoint,
máximo de solicitudes, 400/429/500/503, timeout, JSON inválido, respuestas vacías,
Markdown en modo libre y preparación sin API.

Comandos ejecutados desde `backend` con `DATABASE_URL=sqlite+pysqlite:///:memory:`:

- `python -m pytest -q tests/test_contract_direct_diagnostic.py`: **19 aprobadas**.
- `python scripts/diagnose_contract_direct_gemini.py`: preflight aprobado,
  hashes y texto verificados, **0 llamadas externas**.
- `python -m pytest -q`: **469 aprobadas, 23 omitidas, 2 advertencias conocidas**
  (Starlette/httpx y adaptador datetime de SQLite).
- `python scripts/diagnose_contract_direct_gemini.py --run --env-file <env local>`:
  **1 HTTP 503**, sin reintento; terminó detenido como estaba previsto.
- `git diff --check`: sin errores de formato.

Sólo se agregaron el ejecutor aislado, sus pruebas y la documentación/evidencia.
No se modificaron producción, prompts congelados, controles, umbrales, datos
de Supabase ni resultados anteriores. No hubo commit, push, PR o cambios en
Jira. HU30 continúa en validación; la suite local no permite declararla finalizada.
La documentación queda en el repositorio conforme al acuerdo vigente mientras
Notion está limitado.
