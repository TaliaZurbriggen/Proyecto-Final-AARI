# AARI-112 — Corrida v5 de línea base (casos 21–40)

**Fecha:** 13/08/2026
**Prompt evaluado:** v5, sin cambios respecto de las corridas anteriores
**Responsables:** Talía Zurbriggen y Tobías Gasparotto — trabajo conjunto
**Conjunto:** casos 21–40 de `baseline_61`, validados con Oikos

## Objetivo

Continuar la medición del prompt v5 sobre la línea base, manteniendo congelado
el contenido del prompt para no adaptar sus reglas a resultados ya observados.
Este lote se ejecutó después de la prueba de generalización sobre los casos
61–80 y antes del último rango pendiente de la línea base.

## Ejecución

Comando utilizado desde `backend/`:

```powershell
.\venv\Scripts\python.exe -m tests.data.measure_precision_v5 --lote 20:40
```

El proceso finalizó correctamente en aproximadamente 4 minutos y 37 segundos.
El checkpoint atómico guardó las 20 respuestas nuevas en
`docs/evaluaciones/aari112/resultados_v5_parciales.json`, que ahora contiene
60/80 casos medidos. No se repitieron casos de corridas anteriores.

## Resultados

- Resultado del lote: **18/20 aciertos (90,00 %)**.
- Respuestas inválidas: **0**.
- Acumulado v5: **54/60 aciertos (90,00 %)**.
- Casos pendientes: **20**, correspondientes al rango `40:60`.

### Desglose del lote por resultado esperado

| Categoría | Correctos | Total | Precisión |
|---|---:|---:|---:|
| Extraordinario | 9 | 10 | 90,00 % |
| Expensa | 5 | 5 | 100,00 % |
| Escalar | 4 | 5 | 80,00 % |

El lote no contenía casos cuya categoría esperada fuera `ordinario`.

## Casos incorrectos

### Caso 29 — Sobre-escalado de un problema estructural

- Descripción: una baldosa del piso de la cocina se levantó sola, sin golpe ni
  uso anormal informado.
- Esperado: `extraordinario`.
- Obtenido: escalado por `causa_no_identificable`, confianza `0.60`.
- Lectura: la ausencia explícita de una causa atribuible al inquilino y la regla
  estructural aplicable aportaban información suficiente para clasificar. El
  agente fue más conservador de lo requerido y solicitó una causa adicional.

### Caso 36 — Motivo de escalado incorrecto

- Descripción: “No tengo agua caliente”, sin información sobre el artefacto o
  la causa.
- Esperado: escalado por `causa_no_identificable`.
- Obtenido: escalado por `confianza_insuficiente`, confianza `0.60`.
- Lectura: la decisión operativa de escalar fue segura, pero no respetó la
  distinción de dominio. Faltan datos para elegir entre responsabilidades
  posibles, por lo que correspondía `causa_no_identificable`.

## Conclusión provisional

El tercer lote medido vuelve a superar el umbral objetivo de 85 % y mantiene el
acumulado de v5 en 90 %. Además, no hubo respuestas inválidas. El patrón de error
continúa concentrado en el sobre-escalado y en la distinción entre los motivos
`causa_no_identificable` y `confianza_insuficiente`.

El resultado sigue siendo provisional: todavía no corresponde afirmar el
cumplimiento definitivo de HU9 hasta ejecutar los 20 casos restantes y generar
el reporte final sobre los 80 casos. El prompt v5 debe permanecer sin cambios
durante esa última corrida.

## Próximos pasos

1. Conservar la evidencia y no modificar el prompt v5 durante la medición.
2. Ejecutar el rango `40:60` con autorización explícita y sin repetir llamadas.
3. Generar el reporte final sobre los 80 casos, incluyendo cualquier respuesta
   inválida en el denominador.
4. Analizar los errores por patrones generales una vez cerrada la evaluación,
   sin agregar excepciones específicas para los casos 29 y 36.
