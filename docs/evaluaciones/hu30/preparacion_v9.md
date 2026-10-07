# HU30 — coherencia de interpretación v9 (02/10/2026)

## Contexto y decisión aprobada

V8 recuperó evidencia íntegra y dejó SEXTA sin un pagador atribuido, como
contexto y con confianza baja. Sin embargo, sus condiciones presentaron los
gastos comunes como una excepción definida, mientras el resumen advertía una
ambigüedad. El control E02 quedó parcial: prudencia en la etiqueta no equivale
a fidelidad en todos los campos. Ver el [ensayo v8](evaluacion_v8_v04_2026-10-02.md).

La persona responsable aprobó continuar con el ajuste de coherencia entre
resumen y condiciones. V9 agrega instrucciones para que ambos describan las
lecturas abiertas en lugar de resolver el alcance de una lista en uno de los
campos. También incluye título, responsable y uso en la comprobación final.
Los ejemplos son artificiales, mediante tareas X/Y/Z, sin números de
cláusulas, nombres ni respuestas de los contratos evaluados.

Alternativas consideradas:

- Bajar confianza o marcar contexto: v8 ya lo hace y no corrige el contenido.
- Reescribir resultados en el backend con la respuesta esperada: se descarta;
  ocultaría el error y adaptaría el ejecutor al corpus.
- Agregar reglas por palabras como «salvo» o «excepto»: se descarta; hay
  excepciones claras que deben conservarse como operativas.
- Refinar la comprobación conjunta de campos en el prompt: opción seleccionada,
  limitada al problema observado, sin cambiar esquema ni evidencia.

La instrucción general exige que, si una vinculación es incierta, el resumen
mencione los conceptos sin asignar el discutido a una lista definida, y las
condiciones expliquen las lecturas posibles y por qué no se puede elegir.
Una condición inequívoca continúa siendo una regla operativa con su condición.
No se añadieron respuestas esperadas al ejecutor.

## Archivos y aislamiento

- `backend/prompts/prompt_extraccion_clausulas_v9.md`: conserva v8 y agrega la
  comprobación de coherencia y el ejemplo artificial.
- `backend/app/services/contract_clause_v9.py`: utiliza sólo el prompt v9 y
  reutiliza el esquema y las fuentes locales congeladas de v7.
- `backend/scripts/evaluate_contract_clause_v9.py`: ejecutor específico para
  preservar sin cambios el ejecutor congelado de v8; no repite un checkpoint.
- `backend/tests/test_contract_clause_v9.py`: nueve pruebas locales nuevas.
- `corpus_v9_manifest.json`: congela los tres archivos nuevos, todos los
  archivos previamente congelados en v8, el modelo Flash-Lite, los controles,
  los documentos y la configuración OCR.

El prompt tiene SHA-256
`cd1329993efe6187698281426454095cf4bf499755b6b7998e7469f9f707341e`.
V9 permanece aislada de la aplicación y no requiere dependencias nuevas.
Los resultados v7/v8 y los controles no fueron modificados.

## Validaciones locales

Desde `backend`, con base en memoria y las APIs externas deshabilitadas:

```text
python -m pytest -q --tb=no tests/test_contract_clause_v9.py tests/test_contract_clause_reference_trial.py tests/test_contract_clause_v7.py
20 passed

python -m pytest -q --tb=no
385 passed, 23 skipped, 2 warnings
```

Las nueve pruebas nuevas verifican: uso del prompt v9; marcador de inserción
único; minimización de identificadores; conservación de reglas condicionales
claras y sus evidencias entre páginas; checkpoint previo y no repetición;
conservación de una salida neutral; no reescritura de una salida inconsistente;
rechazo de entradas ilegibles o sin tramos antes del modelo; y congelación de
versiones, controles y umbrales. Los avisos son de dependencias Starlette/httpx
y del adaptador datetime de SQLite, sin errores nuevos.

**Límite de estas pruebas:** los modelos son dobles. No demuestran que Gemini
obedezca las instrucciones ni detectan automáticamente contradicciones
semánticas. Hay una prueba deliberada que conserva una respuesta inconsistente
para demostrar que el ejecutor no la sustituye silenciosamente por lo esperado.
La aceptación técnica de citas sigue requiriendo revisión documental posterior.

Los cuatro preflights locales de `evaluate_contract_clause_v9.py --document ID`
aprobaron, sin `--run`. Los hashes del texto extraído coinciden con v7/v8 y V02
usa el mismo OCR español y archivo de idioma congelado.

| Documento | Caracteres de fuente | Caracteres del prompt | Invocaciones externas v9 |
|---|---:|---:|---:|
| V01 | 33.048 | 40.435 | 0 |
| V02 | 12.338 | 18.886 | 0 |
| V03 | 6.451 | 12.980 | 0 |
| V04 | 4.709 | 11.167 | 0 |

## Autorización, resultado y pendientes

La persona responsable autorizó una invocación sobre V04 y, sólo si la revisión
cumple los mismos criterios, una por V01-V03 con la misma versión congelada:
máximo cuatro, sin reintentos manuales. Los umbrales se
mantienen: 85% general completo, 100% crítico completo y cero interpretaciones
no respaldadas aceptadas. El checkpoint impide repetir un resultado existente.

V04 se ejecutó una vez: cinco propuestas, 3/5 controles completos, 1/3 críticos
completos y dos propuestas no respaldadas. Se detuvo la tanda sin enviar
V01-V03. Ver [revisión y conclusiones](evaluacion_v9_v04_2026-10-02.md).
La tabla anterior describe el preflight previo; el ensayo efectivo utilizó una
invocación del adaptador sobre V04.

Si V04 vuelve a fallar, se registra y se detiene la tanda; no se atribuye una
mejora a la versión por haber aprobado pruebas con dobles. Superar V04 tampoco
demostraría generalización: exige la regresión completa y posteriormente los
holdouts H01-H02, que continúan reservados por Tobías/Oikos. Las iteraciones
sobre un caso conocido tienen riesgo de ajuste al corpus aun sin entrenamiento.

No se escribió en Supabase ni se activó v9 en producción. Tampoco se hizo
commit/push/PR o se cambió el estado de Jira. La documentación queda en el
repositorio según el acuerdo vigente mientras Notion esté limitado.
