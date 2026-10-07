# HU30 — refinamiento semántico v8 (02/10/2026)

## Motivo y alcance

La instrucción de continuar refinando permite preparar el siguiente ajuste de
interpretación. V7 resolvió la procedencia de citas y páginas, pero V04 volvió
a fallar en la coordinación ambigua y en la atribución inversa de un pago.
Los resultados de V7 permanecen registrados y no se cambian sus controles.

V8 conserva exactamente el esquema de salida por `tramo_id`, el modelo
Flash-Lite y la materialización de fuentes locales de v7. Cambia el prompt:

- exige distinguir acciones expresamente atribuidas de responsabilidades
  inferidas sólo porque otra persona está eximida;
- ilustra la diferencia con un ejemplo artificial de financiación de viajes,
  sin nombres, números ni respuestas de los contratos del corpus;
- explicita las dos posibles coordinaciones de una lista con excepción
  mediante variables X/Y/Z, y mantiene ese alcance como contexto si no se
  resuelve en la fuente;
- limita la salida a reglas y contexto de conservación/reclamos, omitiendo
  propuestas separadas de precio, duración, renovación y jurisdicción.

No se añade una regla basada en la palabra `salvo` ni se fuerza que toda
excepción sea ambigua. Las atribuciones claramente condicionales siguen siendo
válidas. No se altera el texto fuente ni se sustituye una interpretación errónea
por la respuesta esperada. El administrador continúa revisando las propuestas.

## Implementación y comprobaciones locales

`contract_clause_v8.py` prepara el nuevo prompt y reutiliza la salida y las
fuentes locales v7. `contract_clause_reference_trial.py` conserva un checkpoint
previo a la invocación, errores seguros y protección contra repetición. El
ejecutor `evaluate_contract_clause_reference.py` comprueba el manifiesto v8,
incluido el idioma OCR de V02. No modifica archivos congelados de versiones
anteriores. El manifiesto registra el prompt con SHA-256
`6ed32b3336ae88c0bee41f13bbd63a2dbcf09c686ba7d9399db47d0ced10562d`.

La suite completa local aprobó **376 pruebas**, con 23 omitidas y dos
advertencias de dependencias (`pytest -q --tb=no`, base en memoria). Las nuevas
pruebas con doble verifican que el prompt v8 se utiliza realmente y que se
mantienen las fuentes y la protección de checkpoints. No prueban que Gemini
obedezca las nuevas instrucciones.

Los cuatro preflights aprobaron. Los hashes del texto extraído coinciden con
v7; V02 utiliza OCR español y el mismo archivo de idioma verificado. Por eso
una comparación v7/v8 no cambia el texto leído, los controles ni la evidencia.

| Documento | Caracteres de fuente | Caracteres del prompt | Invocaciones externas v8 |
|---|---:|---:|---:|
| V01 | 33.048 | 38.399 | 0 |
| V02 | 12.338 | 16.850 | 0 |
| V03 | 6.451 | 10.944 | 0 |
| V04 | 4.709 | 9.131 | 0 |

## Autorización y ejecución externa

Al preparar esta versión, la autorización anterior nombraba v7/V04 y permitía
V01-V03 sólo si V04 cumplía. Como no cumplió, no se gastaron las otras llamadas.
Después la persona responsable autorizó v8 con «proba», en respuesta a la
propuesta de una invocación sobre V04 y, sólo si supera los mismos umbrales,
una por V01-V03, máximo cuatro.

Se ejecutó V04 una vez. Gemini respondió con seis propuestas; la revisión dio
4/5 controles completos, uno parcial, 2/3 críticos completos y una interpretación
no respaldada aceptada. Se detuvo la tanda sin enviar V01-V03. Ver el
[informe del ensayo](evaluacion_v8_v04_2026-10-02.md). La tabla anterior describe
el preflight previo a la autorización; la ejecución efectiva consumió una
invocación del adaptador en V04. No hubo reintentos manuales ni acceso a H01/H02.

La v8 sigue aislada de producción. No se escribió en Supabase ni se hizo commit,
push, PR o actualización de Jira. La documentación permanece en el repositorio
mientras Notion no permita nuevos bloques. El ensayo muestra una mejora parcial
de prudencia respecto de v7, pero no cumple los criterios de aceptación.
