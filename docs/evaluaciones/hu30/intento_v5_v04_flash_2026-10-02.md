# HU30 — intento v5/V04 con Gemini 3.5 Flash (02/10/2026)

## Objetivo y preparación

Se intentó aislar el efecto del modelo en V04: mismo PDF público, prompt v5,
segmentador y verificador del ensayo previo con Flash-Lite, cambiando solo a
`gemini-3.5-flash`. No se enviaron contratos privados ni los controles
esperados. El PDF se revisó visualmente en sus dos páginas; la cláusula SEXTA
contiene la coordinación de impuestos, consumos y gastos comunes cuyo alcance
necesita revisión humana.

El ejecutor `backend/scripts/evaluate_contract_clause_v5.py` ahora admite
`--model gemini-3.5-flash` y reserva un archivo distinto al histórico de
Flash-Lite. Se comprobó el hash de V04, del prompt y del verificador antes de
la llamada. El modo sin `--run` informó `external_calls: 0`. Cuatro pruebas
locales del checkpoint y la separación de resultados aprobaron. Tras el
intento, la suite completa de backend terminó con **356 pruebas aprobadas,
23 omitidas** por entorno o servicios opcionales y dos advertencias de
bibliotecas. `git diff --check` no detectó defectos de formato.

## Resultado externo

La única invocación autorizada del adaptador terminó en `ServerError` con
HTTP `503`; el [checkpoint seguro](resultados_v5/resultado_v04_v5_flash.json)
registra `state: failed`, modelo y hashes sin guardar texto privado ni
credenciales. No hubo reintento manual. `max_retries=1` estaba configurado,
pero el registro no verifica cuántos intentos HTTP internos efectuó la
biblioteca.

**No se generaron cláusulas evaluables.** Este 503 no cuenta como acierto ni
error de extracción y no altera el resultado anterior de Flash-Lite: 4/5
controles completos, 2/3 críticos y una interpretación no respaldada aceptada.
La v5 continúa experimental y la aplicación sigue usando v4 para extraer.

## Próximo paso sujeto a acuerdo

No volver a lanzar el mismo checkpoint ni reemplazar evidencia. Una nueva
prueba requeriría autorización y otro archivo de intento, con límite explícito
de llamadas. Si Flash llega a responder, revisar V04 control por control antes
de decidir la regresión V01–V03. Si vuelve a fallar por disponibilidad, tratar
la elección de modelo/proveedor como dependencia técnica separada de la
precisión semántica; no declarar HU30 concluida por el fallback de revisión.
