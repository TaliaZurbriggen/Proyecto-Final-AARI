# AARI-112 — Cierre anticipado de la medición del prompt v3

**Fecha de decisión:** 08/08/2026
**Estado:** iteración v3 cerrada como no satisfactoria; AARI-112 continúa para la iteración v4.

## Resultado observado

Se ejecutaron 60 de los 61 casos del conjunto de prueba v1.1 con Gemini y el prompt v3.
La evidencia recuperable está en
[`resultados_v3_parciales.json`](resultados_v3_parciales.json).

| Métrica | Resultado |
| --- | --- |
| Casos ejecutados | 60/61 |
| Aciertos observados | 48/60 |
| Precisión observada | 80,00 % |
| Precisión macro observada sobre las categorías ya medidas | 82,52 % |
| Caso no ejecutado | `caso-61` |
| Objetivo de HU9 | ≥85 % |

## Regla de corte

Para alcanzar 85 % sobre 61 casos se requieren al menos 52 aciertos. Con 48 aciertos
acumulados y un único caso pendiente, el mejor resultado posible era 49/61 (80,33 %).
Por lo tanto, ejecutar `caso-61` no podía modificar la conclusión de aceptación de v3.

Se decidió no consumir la llamada restante de la cuota gratuita de Gemini. Esta decisión
evita una llamada sin valor para la decisión del Sprint y deja explícito que **no existe un
resultado final observado sobre 61 casos**: 49/61 es un máximo teórico, no una medición.

## Conclusión de v3

El prompt v3 mejoró respecto de la línea base v2 (35/61, 57,38 %), pero no alcanza el
criterio de aceptación de ≥85 %. La principal oportunidad que permanece es distinguir mejor
la ambigüedad real de los reclamos que cuentan con una regla directa, sin dejar de escalar
casos cuya causa o responsabilidad no puede determinarse.

## Siguientes pasos

1. Congelar v3 y preservar sus 60 resultados como evidencia de esta iteración.
2. Diseñar y aprobar el prompt v4 a partir de patrones de error, sin incorporar textos ni
   identificadores de casos como ejemplos del prompt.
3. Evaluar la ampliación de la suite de 61 a 80 casos: mantener los 61 como regresión y
   agregar 19 casos nuevos de generalización, con criterios esperados definidos antes de
   ejecutar v4.
4. Medir v4 con una política de evaluación documentada antes de consumir nuevas llamadas.
