# Diagnóstico de conexión de HU30 - 28/09/2026

## Alcance y autorización

Se autorizaron dos consultas mínimas, una por prueba, y posteriormente una
extracción del documento público V04 mediante Interactions. No se enviaron
contratos privados ni los controles esperados a Gemini. No se modificaron
el prompt v4, el adaptador de producción, el modelo de reclamos ni el archivo
`.env`. No se hicieron reintentos automáticos.

## Evidencia de acceso

La consulta de catálogo autenticada respondió en 0,77 segundos y enumeró
`gemini-3.5-flash`, `gemini-3.8-flash` y `gemini-3.5-flash-lite` con
`generateContent` disponible. El destino fue
`generativelanguage.googleapis.com`, API `v1beta`, sin endpoints personalizados
ni variables de proxy configuradas. Esto confirma acceso al catálogo, no
disponibilidad garantizada de generación.

El panel oficial mostraba todos los sistemas operativos también en el filtro
gratuito. Ese estado agregado no descarta problemas de un proyecto, modelo o
ruta concreta. Fuentes: [estado oficial](https://aistudio.google.com/status?tier=free)
y [guía de Interactions](https://ai.google.dev/gemini-api/docs/interactions-overview).

## Consultas mínimas

| Prueba | Resultado | Duración | Peticiones HTTP |
|---|---|---:|---:|
| 3.5 Flash por Interactions | HTTP 200, completada, respondió OK | 42,43 s | 1 |
| 3.5 Flash-Lite por generateContent | HTTP 200, finalización STOP, respondió OK | 1,33 s | 1 |

Se utilizó el mensaje sintético "Responde solamente OK.". La prueba de
Interactions incluyó `store: false`. Ambas peticiones fueron directas, con
reintentos de transporte deshabilitados. Estos resultados no demuestran que
Flash-Lite sea preciso con cláusulas ni que Interactions resuelva toda la
extracción. Tampoco prueban que generateContent esté roto: no se comparó
simultáneamente 3.5 Flash por ambas rutas.

## Única extracción autorizada de V04

Registro: [resultado V04](resultados_interactions_v4/resultado_v04_2026-09-28.json).

- PDF público: modelo contractual DGN, dos páginas contractuales.
- SHA-256: verificado contra el manifiesto congelado.
- Lectura local: completa, dos páginas digitales, 4.709 caracteres.
- Revisión visual: ambas páginas originales inspeccionadas; se conserva la
  continuación de la cláusula quinta y la redacción de la cláusula sexta.
- Prompt: v4, hash sin modificaciones.
- Modelo: `gemini-3.5-flash`.
- API: Interactions, `store: false`, una petición y cero reintentos.
- Formato experimental: salida JSON nativa con el esquema Pydantic completo,
  según la [guía oficial de salida estructurada](https://ai.google.dev/gemini-api/docs/structured-output).
- Resultado: HTTP 400, `invalid_request`, en 14,374 segundos.
- Mensaje del proveedor: "Request contains an invalid argument.".
- Cláusulas obtenidas: ninguna. No hay cobertura, precisión ni revisión de
  controles calculables para este intento.

La prueba cambió la codificación de salida: el adaptador actual usa
`function_calling`, mientras este ensayo usó `response_format` JSON nativo.
Por ese motivo se guardó separado de los resultados v4 previos y no se
considera una repetición idéntica de la evaluación congelada.

El mensaje 400 no identifica el parámetro rechazado. El esquema de salida
es una hipótesis relevante por el rechazo de JSON nativo observado previamente,
pero no está demostrado que sea el único origen del error. No se atribuye este
resultado a cuota, falta de acceso, prompt incorrecto o disponibilidad del
modelo sin evidencia adicional.

## Validaciones locales posteriores

La primera ejecución de pruebas no pudo recolectarlas porque este worktree no
tiene `.env` y faltaba `DATABASE_URL`. Se repitió con una URL SQLite en memoria
sólo para el proceso, sin conectarse a la base compartida:

```powershell
$env:DATABASE_URL='sqlite:///:memory:'
python -m pytest backend/tests/test_contract_clauses.py backend/tests/test_contract_clause_corpus.py backend/tests/test_contract_clause_windows.py -q
```

Resultado: **23 aprobadas, 1 omitida**. La omitida es la prueba OCR real, no
habilitada en esta ejecución. Estas pruebas validan la implementación existente
con dobles; no prueban compatibilidad real del formato Interactions.

## Próximo paso propuesto, no ejecutado

Antes de modificar producción, realizar una única nueva prueba autorizada de
V04 por Interactions manteniendo `function_calling`, con los mismos campos,
prompt, modelo y validación final Pydantic/anclaje de evidencia. Usar un esquema
de herramienta compatible y no enviar los controles esperados.

Si responde, revisar los cinco controles de V04, incluido el tratamiento
neutral de la coordinación ambigua de impuestos/consumos/gastos comunes.
Una respuesta técnica válida no habilita cerrar HU30: faltan la regresión
restante, los controles críticos y los holdouts reservados. Cualquier adopción
del nuevo transporte requiere propuesta, aprobación y pruebas específicas.

No se hicieron commits, push, cambios de estado ni carga de horas. Esta nota
es evidencia de diagnóstico, no una decisión de migración de la aplicación.

## Prueba posterior autorizada con function_calling

Con autorización explícita se realizó un único intento adicional de V04 por
Interactions con `function_calling`, sin salida JSON nativa. Se conservaron
`gemini-3.5-flash`, el prompt v4 congelado, el documento verificado, la lectura
local completa y la validación final Pydantic/anclaje de evidencia.

El esquema de herramienta se envió inline, sin referencias `$defs/$ref`,
con campos, tipos, listas, categorías y obligatoriedad. Los campos de texto
opcionales podían omitirse en vez de enviarse como null. Las restricciones
de longitud/rango y la prohibición de campos desconocidos permanecieron en
la validación local, no se eliminaron del modelo de AARI. Se forzó el uso de
la herramienta `ExtractedClauseBatch`, con `store: false` y sin reintentos.

Registro:
[resultado de function_calling](resultados_interactions_v4/resultado_v04_function_calling_2026-09-28.json).

Resultado: **HTTP 503 en 4,479 segundos**, una petición. El proveedor indicó:
"gemini-3.5-flash is currently experiencing high demand, spikes in demand are
usually temporary. Please try again later.".

No se recibió una llamada de herramienta ni cláusulas evaluables. No hay
métricas de cobertura/precisión para este intento. El 503 tampoco demuestra
que el servidor haya validado completamente el esquema: no se declara la
compatibilidad de function_calling por Interactions como comprobada.

La respuesta mínima exitosa de 3.5 Flash por Interactions no garantizó la
disponibilidad de la extracción posterior. Por tanto, no se adopta el
transporte ni se declara resuelto el problema.

### Próximo ensayo sugerido, pendiente de autorización

Probar una única extracción del mismo V04 con `gemini-3.5-flash-lite`, que
respondió la consulta mínima. Conservar prompt v4 y controles, registrar
modelo/transporte/esquema en un experimento separado y revisar todos los
resultados antes de proponer un cambio de producción. Una extracción exitosa
de V04 por sí sola no demuestra generalización ni habilita cerrar HU30.

No se realizó esa llamada, ni se cambiaron código, dependencias, `.env`,
modelo de reclamos o decisiones de producción.
