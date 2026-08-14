# AARI-112 — Informe final de la evaluación del prompt v5

**Fecha:** 14/08/2026
**Prompt evaluado:** v5, congelado durante las cuatro corridas
**Responsables:** Talía Zurbriggen y Tobías Gasparotto — trabajo conjunto
**Conjunto:** 80 casos validados con Oikos (`baseline_61` + `holdout_19`)

## Objetivo

Medir si el prompt v5 alcanza el criterio de aceptación de HU9: una precisión
global de al menos 85 % sobre los 80 casos, contabilizando las respuestas
inválidas como errores. La evaluación separa la línea base del conjunto holdout
para observar si la mejora se sostiene ante casos no utilizados para diseñar el
prompt.

El prompt permaneció sin cambios desde la primera hasta la última corrida. Las
etiquetas esperadas tampoco se modificaron después de observar las respuestas.

## Último lote — casos 41–60

Comando ejecutado desde `backend/`:

```powershell
.\venv\Scripts\python.exe -m tests.data.measure_precision_v5 --lote 40:60
```

La tanda finalizó correctamente en aproximadamente 3 minutos y 28 segundos. El
checkpoint atómico incorporó las 20 respuestas nuevas y completó los **80/80
casos** sin repetir llamadas anteriores.

### Resultado del lote

- Precisión: **16/20 (80,00 %)**.
- Respuestas inválidas: **0**.
- Ordinario: **3/3**.
- Extraordinario: **2/2**.
- Expensa: **3/3**.
- Escalar: **8/12**.

### Errores del lote

| Caso | Esperado | Obtenido | Tipo de error |
|---|---|---|---|
| 41 | Escalar: `causa_no_identificable` | `ordinario` | Escalamiento omitido |
| 48 | Escalar: `confianza_insuficiente` | Escalar: `causa_no_identificable` | Motivo incorrecto |
| 55 | Escalar: `confianza_insuficiente` | Escalar: `causa_no_identificable` | Motivo incorrecto |
| 56 | Escalar: `confianza_insuficiente` | `extraordinario` | Escalamiento omitido |

Los casos 48 y 55 tuvieron una decisión operativa segura porque fueron enviados
a revisión humana, aunque el motivo no coincidió con el criterio validado. Los
casos 41 y 56 son más relevantes para una mejora futura porque el agente tomó
una decisión automática cuando correspondía escalar.

## Resultado final de v5

El reporte se generó sin llamadas externas a partir de los 80 checkpoints:

```powershell
.\venv\Scripts\python.exe -m tests.data.measure_precision_v5 --reporte-final
```

| Métrica | Resultado |
|---|---:|
| Precisión global | **70/80 (87,50 %)** |
| Precisión macro | **88,08 %** |
| Respuestas inválidas | **0/80** |
| Línea base | **53/61 (86,89 %)** |
| Holdout | **17/19 (89,47 %)** |
| Umbral requerido por HU9 | **85,00 %** |
| Cumplimiento de HU9 | **Sí** |

### Precisión por resultado esperado

| Categoría | Correctos | Total | Precisión |
|---|---:|---:|---:|
| Ordinario | 21 | 23 | **91,30 %** |
| Extraordinario | 21 | 22 | **95,45 %** |
| Expensa | 11 | 12 | **91,67 %** |
| Escalar | 17 | 23 | **73,91 %** |

## Análisis de las diez regresiones

- **4 sobre-escalados:** casos 12, 13, 29 y 73. La conducta fue conservadora y
  derivó los reclamos a revisión humana, pero redujo la automatización.
- **2 escalamientos omitidos:** casos 41 y 56. Son los errores de mayor impacto
  funcional porque el agente clasificó automáticamente un caso ambiguo.
- **4 motivos de escalado incorrectos:** casos 36, 48, 55 y 80. Los cuatro casos
  fueron escalados de todos modos, pero no se distinguió correctamente entre
  `causa_no_identificable` y `confianza_insuficiente`.
- **0 respuestas inválidas:** el contrato de salida se respetó en las 80
  invocaciones.

La precisión de las tres categorías de gasto supera el 91 %. La principal
debilidad remanente es la decisión de cuándo escalar y cómo expresar su motivo,
especialmente ante información contractual no verificable o una única regla
candidata con encaje débil.

## Conclusión

El prompt v5 **cumple el criterio de aceptación global de HU9**, con 87,50 %
sobre los 80 casos validados. También supera el umbral tanto en la línea base
como en el holdout. El 89,47 % del holdout aporta evidencia favorable de
generalización y reduce la sospecha de que la mejora provenga únicamente de
adaptar el prompt a los casos originales.

No se recomienda crear una v6 dentro de AARI-112: modificar el prompt después de
observar todo el conjunto impediría usar estos mismos 80 casos como evaluación
independiente. Las diez regresiones deben conservarse como evidencia y, si el
producto requiere mejorar especialmente el escalado, tratarse en una iteración
futura con nuevos casos inéditos definidos antes del ajuste.

## Próximos pasos

1. Ejecutar la suite automática y revisar el diff de los artefactos finales.
2. Publicar la evidencia cuando exista autorización de commit y push.
3. Mantener AARI-112 en curso hasta que el Pull Request sea revisado y fusionado.
4. Continuar con AARI-113 para las pruebas de integración y el cierre del Sprint.
