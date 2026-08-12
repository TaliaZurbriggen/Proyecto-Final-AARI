# AARI-112 — Corrida v5 de generalización (casos 61–80)

**Fecha:** 12/08/2026
**Prompt evaluado:** v5
**Responsables:** Talía Zurbriggen y Tobías Gasparotto — trabajo conjunto
**Conjunto:** `caso-61` de la línea base y los 19 casos `holdout_19` validados con Oikos.

## Objetivo

Evaluar temprano si la mejora observada en el primer lote de v5 se sostiene ante
casos no utilizados para diseñar el prompt. Se priorizó el rango `60:80` en lugar
de continuar secuencialmente con `20:40` para medir la capacidad de generalización
antes de completar el resto de la línea base.

Los resultados esperados no se modificaron después de la corrida. El holdout se
utiliza como evaluación y no como una lista de ejemplos para ajustar el prompt
caso por caso.

## Ejecución y recuperación

Comando utilizado desde `backend/`:

```powershell
.\venv\Scripts\python.exe -m tests.data.measure_precision_v5 --lote 60:80
```

La primera ejecución superó el límite de cinco minutos de la consola después de
guardar 16 respuestas. El checkpoint atómico permitió verificar el avance y
reanudar el mismo rango sin repetir llamadas: el evaluador omitió los casos ya
registrados y procesó solamente los cuatro faltantes.

La evidencia acumulada quedó en
`docs/evaluaciones/aari112/resultados_v5_parciales.json`, con 40/80 casos medidos.

## Resultados

- Resultado de la tanda: **18/20 aciertos (90,00 %)**.
- Caso 61 de la línea base: **1/1 correcto** (`expensa`).
- Holdout de generalización: **17/19 aciertos (89,47 %)**.
- Respuestas inválidas: **0**.
- Acumulado v5 después de dos tandas: **36/40 aciertos (90,00 %)**.

### Desglose de la tanda por resultado esperado

| Categoría | Correctos | Total | Precisión |
|---|---:|---:|---:|
| Ordinario | 5 | 5 | 100,00 % |
| Extraordinario | 5 | 5 | 100,00 % |
| Expensa | 3 | 4 | 75,00 % |
| Escalar | 5 | 6 | 83,33 % |

## Casos incorrectos

### Caso 73 — Sobre-escalado de un problema común

- Descripción: las cámaras de seguridad de la entrada dejaron de grabar y el
  problema afecta a todo el consorcio.
- Esperado: `expensa`.
- Obtenido: escalado por `causa_no_identificable`, confianza `0.60`.
- Lectura: el alcance común del problema aportaba evidencia suficiente para
  aplicar la regla de expensa, pero el agente pidió una causa técnica adicional.

### Caso 80 — Motivo de escalado incorrecto

- Descripción: persiana rota y referencia imprecisa a una posible cláusula de
  reparaciones menores cuyo contenido no se recuerda.
- Esperado: escalado por `confianza_insuficiente`.
- Obtenido: escalado por `causa_no_identificable`, confianza `0.50`.
- Lectura: la decisión de no clasificar automáticamente fue segura, pero no
  respetó la distinción de dominio entre una única regla candidata débil y dos
  responsabilidades identificables en conflicto.

## Conclusión provisional

El holdout supera el umbral objetivo de 85 %, lo que reduce la sospecha de que el
90 % del primer lote se deba únicamente a adaptación a los casos conocidos. No
obstante, todavía no corresponde afirmar que HU9 cumple el objetivo: faltan los
casos 21–60 y el reporte final debe calcular la precisión sobre los 80 casos,
incluyendo cualquier respuesta inválida en el denominador.

## Próximos pasos

1. Conservar esta evidencia sin repetir llamadas ni modificar las etiquetas.
2. Ejecutar `20:40` y `40:60`, una tanda por día y con autorización explícita.
3. Generar el reporte final de v5 sobre 80 casos.
4. Analizar los errores por patrón, no agregar excepciones textuales para los
   casos 73 y 80.
