# AARI-113 — Pruebas automatizadas e integración del clasificador

**Fecha:** 14/08/2026

**Responsables:** Talía Zurbriggen y Tobías Gasparotto — trabajo conjunto

**Rama:** `feat/AARI-113-classifier-tests`

## Objetivo

Comprobar de forma automática y reproducible que los componentes del
clasificador funcionan correctamente al conectarse entre sí, y que la evidencia
real obtenida con el prompt v5 conserva el cumplimiento del criterio de
aceptación de HU9.

Las pruebas automatizadas no vuelven a invocar Gemini ni escriben en Supabase.
La calidad de la clasificación del modelo ya fue medida con 80 invocaciones
reales en AARI-112; AARI-113 verifica la integración del código y protege esa
evidencia frente a cambios accidentales.

## Alcance implementado

### Integración de las capas de la aplicación

Se incorporaron cuatro escenarios que recorren:

```text
Endpoint FastAPI
    → ClassificationService
    → grafo real de LangGraph
    → proveedor controlado
    → validación del resultado
    → repositorio en memoria
```

El proveedor y el repositorio son dobles de prueba. El endpoint, el servicio, el
grafo, el prompt v5, la base de conocimiento y los contratos de datos son los
componentes reales de la aplicación.

Los escenarios cubiertos son:

1. Clasificación de confianza suficiente y persistencia de `ordinario`.
2. Escalado forzado cuando la confianza es menor al umbral `0.75`.
3. Conservación de un escalado del modelo por `riesgo_seguridad`.
4. Fallback seguro `respuesta_modelo_invalida` ante una respuesta incompleta.

### Prueba de aceptación sobre la evidencia real

La prueba carga el conjunto validado
`backend/tests/data/conjunto_prueba_80_casos.json` y los checkpoints reales de
`docs/evaluaciones/aari112/resultados_v5_parciales.json`.

Comprueba que:

- Los 80 identificadores son únicos y coinciden exactamente con los 80
  checkpoints.
- La composición sigue siendo 61 casos de línea base y 19 casos holdout.
- Las etiquetas esperadas guardadas en los checkpoints coinciden con el dataset
  validado con Oikos.
- El evaluador reproduce 70 aciertos sobre 80 casos, equivalente a 87,50 %.
- La línea base conserva 53/61 y el holdout 17/19.
- No existen respuestas inválidas.
- La precisión global continúa por encima del umbral de 85 % de HU9.
- El reporte versionado `resultados_v5.json` coincide con la evidencia
  recalculada.

## Validaciones ejecutadas

Desde `backend/`:

```powershell
.\venv\Scripts\python.exe -m pytest -q tests\test_classification_integration.py tests\test_classifier_acceptance.py
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall -q app
```

Resultados:

- Pruebas nuevas de AARI-113: **8 passed**.
- Suite completa del backend: **57 passed**.
- Compilación del paquete `app`: correcta.
- Llamadas a Gemini durante la suite automática: **0**.
- Escrituras en Supabase durante la suite automática: **0**.

La suite muestra una advertencia conocida de deprecación entre Starlette y
httpx. No provoca fallos ni modifica el resultado funcional; su actualización
se tratará por separado para no ampliar el alcance de esta tarea.

## Smoke test real

Con autorización explícita se ejecutó una prueba de punta a punta con un reclamo
sintético de plomería. La prueba utilizó el endpoint, el servicio, el LangGraph,
Gemini y Supabase reales.

Resultado:

- Respuesta HTTP: **200**.
- Clasificación: `ordinario`.
- Confianza: **0.95**.
- Estado persistido: `Clasificado`.
- Origen de la clasificación: `agente`.
- Historial: `Recibido → Clasificado`, con origen `agente`.
- Fundamento del modelo: persistido correctamente.
- Limpieza: reclamo, historial, inquilino, propiedad y propietario sintéticos
  eliminados al finalizar.

El smoke test consumió una llamada de Gemini. No dejó datos sintéticos en la
base y no requirió ejecutar migraciones.

## Conclusión

La integración automatizada del clasificador quedó cubierta y la evidencia del
prompt v5 se puede reproducir sin llamadas externas. Las pruebas confirman que
HU9 mantiene una precisión de **87,50 %**, superior al mínimo de **85 %**, y que
los caminos de clasificación, escalado por umbral, escalado de seguridad y
fallback seguro llegan correctamente desde LangGraph hasta la respuesta HTTP y
la persistencia definida por el servicio. El smoke test real confirmó además la
conexión completa con Gemini y Supabase y la trazabilidad del cambio de estado.
