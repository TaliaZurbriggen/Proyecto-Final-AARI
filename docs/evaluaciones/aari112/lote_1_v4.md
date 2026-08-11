# AARI-112 — Prompt v4 — Lote 1

**Fecha:** 10/08/2026
**Rama:** `feat/AARI-112-iteracion-prompt`
**Prompt:** v4 (`4665b81`)
**Dataset:** v2.0 de 80 casos (`976d902`)
**Validación de dominio:** Talía confirmó que los 80 casos fueron validados con Oikos.

## Alcance de la ejecución

Se ejecutaron con Gemini los casos `caso-01` a `caso-20`, todos pertenecientes al
subconjunto `baseline_61`. La autorización cubrió exclusivamente estos 20 casos sintéticos.
El evaluador guardó un checkpoint atómico después de cada respuesta en
[`resultados_v4_parciales.json`](resultados_v4_parciales.json).

Comando ejecutado desde `backend/`:

```powershell
.\venv\Scripts\python.exe -m tests.data.measure_precision_v4 --lote 0:20
```

## Resultado preliminar

| Métrica | Resultado |
| --- | ---: |
| Casos ejecutados | 20/80 |
| Aciertos | 12/20 |
| Precisión del lote | 60,00 % |
| Ordinario | 9/15 (60,00 %) |
| Extraordinario | 3/5 (60,00 %) |
| Respuestas inválidas | 0 |

Este resultado es preliminar y no permite calcular todavía la precisión global sobre los
80 casos ni concluir el cumplimiento de HU9.

## Casos incorrectos

| Caso | Esperado | Obtenido | Confianza | Observación |
| --- | --- | --- | ---: | --- |
| `caso-04` | ordinario | escalar: causa no identificable | 0,70 | El relato aporta una sobrecarga repetible, pero v4 exigió más contexto. |
| `caso-09` | ordinario | escalar: causa no identificable | 0,60 | La cerradura se describe explícitamente como gastada. |
| `caso-12` | ordinario | escalar: causa no identificable | 0,90 | La hipótesis de recalentamiento está acompañada por uso continuo de una estufa. |
| `caso-13` | ordinario | escalar: causa no identificable | 0,60 | La regla de vidrio contempla expresamente la ausencia de causa externa. |
| `caso-14` | ordinario | escalar: causa no identificable | 0,85 | Se relata falta concreta de descongelamiento como mantenimiento omitido. |
| `caso-15` | ordinario | escalar: causa no identificable | 0,60 | El desgaste previo de la cerradura está expresamente informado. |
| `caso-17` | extraordinario | escalar: causa no identificable | 0,90 | La antigüedad de 15 años aporta el dato discriminante. |
| `caso-20` | extraordinario | escalar: confianza insuficiente | 0,70 | El paso de los años sin pintar aporta evidencia de vetustez. |

## Comparación con v3

Sobre estos mismos 20 casos, v3 había obtenido 16/20 (80,00 %). V4 no recuperó ninguno de
los cuatro errores previos y agregó cuatro regresiones nuevas: `caso-04`, `caso-09`,
`caso-13` y `caso-15`.

La evidencia indica que la formulación de condiciones materiales de v4 quedó demasiado
restrictiva. Aunque el prompt reconoce hechos explícitos y excepciones definidas por la
base, el modelo siguió priorizando el escalado por falta de causa. No se deben modificar
los resultados ni repetir llamadas para mejorar esta medición.

## Validaciones previas a la ejecución

- Pruebas específicas del evaluador, prompt y grafo: `26 passed`.
- Suite completa del backend: `44 passed`.
- Una advertencia conocida de deprecación Starlette/httpx, sin relación con la medición.
- Sin llamadas externas durante las pruebas locales.

## Próximo paso recomendado

Detener las siguientes tandas hasta analizar si corresponde simplificar v4 o crear v5. La
prioridad es hacer explícita la precedencia de evidencia positiva sobre el escalado genérico,
sin agregar ejemplos copiados de la suite. Los 60 casos restantes conservan su condición de
no ejecutados.
