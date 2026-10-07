# HU30 — v7 experimental: evidencia desde la fuente local (02/10/2026)

## Decisión aprobada

Tras el ensayo v6, la persona responsable indicó continuar el refinamiento.
Se aplica la propuesta de obtener la evidencia en el backend a partir del
tramo identificado por Gemini. V6 ya había preservado la ambigüedad de gastos,
pero seguía copiando primeras líneas y equivocando una página. Cambiar sólo
la longitud solicitada de las citas no eliminó esa dependencia de transcripción.

En v7, el modelo devuelve `tramo_id` y los campos de interpretación. No puede
enviar ni sobrescribir citas, páginas ni el número de cláusula. El backend
adjunta todos los fragmentos del tramo local en sus páginas originales,
incluidas las continuaciones, conservando el texto leído sin corregirlo.
La salida materializada utiliza el esquema de cláusulas existente. La salida
cruda y la correspondencia entre propuesta y tramo permanecen auditables.

## Alcance, alternativas y límites

Se agregaron `contract_clause_v7.py`, `contract_clause_v7_trial.py`, el prompt
v7, el ejecutor de evaluación y pruebas. La propuesta sigue aislada de la app:
no se cambian las migraciones, Supabase, el extractor de producción ni las
evaluaciones históricas. Los tramos con encabezado no reconocible se conservan
en la entrada, pero las propuestas que los usan requieren revisión y se
rechazan. Un tramo mayor que el límite de evidencia también se rechaza completo,
sin truncarlo. Se admite más de una regla independiente por el mismo tramo.

La evidencia muestra **el tramo contractual completo**, no un subrayado de la
frase exacta de cada regla. Dos reglas distintas del mismo tramo pueden mostrar
la misma fuente. Esto permite leer sus condiciones juntas, a costa de mostrar
más texto. No se eligió recortar por oraciones automáticamente: podría separar
un sujeto de su obligación o una excepción de la regla.

Una referencia local existente sólo demuestra procedencia. Gemini aún puede
elegir el tramo equivocado, omitir reglas o resumir mal; el OCR y los límites
del segmentador también pueden fallar. Por eso el resultado se revisará por
significado, condiciones y responsable contra los mismos controles congelados.
La evidencia completa no permite contabilizar como correcta una interpretación
que invente o resuelva una ambigüedad.

## Evaluación prevista

El manifiesto v7 congela prompt, adaptador, materialización, segmentador,
esquema, lector y los 23 controles históricos. Se mantienen 85% general,
100% crítico y cero interpretaciones no respaldadas aceptadas. La primera
corrida es V04 con el mismo Flash-Lite de v6; si cumple, se continúa con
V01-V03 sin editar la versión entre documentos. No se envían H01/H02.

Cada documento tiene un checkpoint previo a la invocación, resultados separados
y protección contra repetición. Se conserva `max_retries=1`; la cantidad de
invocaciones no se presenta como una medición independiente de peticiones HTTP.
No se registran mensajes crudos de errores del proveedor.

Para V02 se encontró el idioma español ya descargado en
`tmp/hu30-ocr/tessdata/spa.traineddata` (archivo local ignorado). Su hash figura
en el manifiesto. Se usará con `TESSDATA_PREFIX` explícito y `TESSERACT_LANGUAGE=spa`;
no fue necesario instalar nada ni reutilizar el OCR en inglés del preflight v6.

Las nueve pruebas específicas iniciales aprobaron. Comprueban continuaciones,
referencias inexistentes, encabezados repetidos/ilegibles, límites sin truncar,
imposibilidad de sobrescribir fuentes, checkpoint y ausencia de reintentos.
Los ensayos externos se documentarán junto con sus revisiones. La decisión queda
en el repositorio mientras Notion siga limitado; no se autoriza por esto commit,
push ni cierre de Jira.

## Comprobaciones y estado externo

La suite local completa terminó con **374 aprobadas, 23 omitidas y dos
advertencias de dependencias** (`pytest -q --tb=no`, base en memoria). No se
llamó a Supabase. El preflight verificó todos los archivos congelados y conservó
el texto local de los cuatro documentos:

| Documento | Páginas | Tramos | Caracteres leídos | Método |
|---|---:|---:|---:|---|
| V01 | 9 | 32 | 33.048 | Digital |
| V02 | 3 | 15 | 12.338 | OCR en español, con hash de idioma verificado |
| V03 | 3 | 12 | 6.451 | Digital |
| V04 | 2 | 12 | 4.709 | Digital |

La solicitud de ejecutar v7/V04 en Gemini fue rechazada **antes de iniciar el
proceso** por la revisión automática de permisos. Su motivo fue que la
autorización externa anterior identificaba v6/V04 y no esta nueva versión.
No es un fallo de Gemini ni una cuota agotada: **cero invocaciones externas de
v7**, sin checkpoint de corrida. Queda pendiente aprobación específica para
V04 y, si cumple, los otros tres documentos con Flash-Lite. No se afirma todavía
que la versión mejore la precisión ni se cambian los umbrales o controles.

## Ensayo posterior autorizado

Tras la confirmación específica se hizo una invocación de V04. La
[evaluación](evaluacion_v7_v04_2026-10-02.md) obtuvo 4/5 controles completos,
2/3 críticos y dos atribuciones no respaldadas en una misma cláusula ambigua.
V01-V03 no se enviaron porque V04 no cumplió. El registro de bloqueo anterior
describe sólo el intento previo a esa autorización; no el estado final del ensayo.
