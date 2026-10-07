# HU30 - Evaluación real de Gemini v2 sobre el ejemplo 01

**Fecha:** 21/09/2026. **Modelo:** `gemini-3.5-flash`. **Prompt:** `v2`.
**Extractor:** `hu30-v2`.

La fuente fue la misma copia anonimizada y verificada de 13 páginas, SHA-256
`3e27aa10c53c72abdeee176175420067d109456465010e5fc61a46437896b16b`.
El contrato original no fue transmitido. La ejecución usó salida estructurada
mediante `function_calling`, validación Pydantic y comprobación literal de cada
fragmento contra la página declarada.

## Resultado de ejecución

- 20 propuestas devueltas por Gemini.
- 17 propuestas aceptadas por la comprobación de evidencia.
- 3 propuestas rechazadas, conservadas completas para auditoría.
- Tasa de aceptación de evidencia: **17/20 = 85%**. No equivale a precisión.
- Lectura local completa: 13/13 páginas.
- Resultado estructurado: `resultado_gemini_ejemplo_01_v2.json`.
- Un intento anterior de v2 terminó por un corte de conexión local de Windows y
  no generó archivo parcial; el reintento autorizado produjo este resultado.

## Cobertura de los controles

| Control | Estado | Resultado relacionado | Observación |
|---|---|---|---|
| E01 | Completo | Primera | Recuperó inventario y estado, pero sugirió uso `operativa`; debe cambiarse a `contexto` en la revisión humana. |
| E02 | Completo | Primera; Segunda | Conservó devolución, limpieza, desocupación y funcionamiento al final. |
| E03 | Completo | Octava | Recuperó autorización previa, efectos y costos de alteraciones. |
| E04 | Completo | Novena (a) | Conservó atribución amplia y referencia al estado recibido. |
| E05 | Completo | Novena (b) | Conservó culpa o negligencia de moradores o terceros. |
| E06 | Rechazado | Novena (c), propuesta 7 | El contenido fue encontrado, pero atribuyó a la página 6 un fragmento que está en la 5; no se aceptó como evidencia válida. **Crítico.** |
| E07 | Completo | Novena (d) | Unió páginas 5-6 y conservó la condición de culpa imputable. **Crítico recuperado respecto de v1.** |
| E08 | Rechazado | Novena (e), propuesta 9 | Encontró el contenido, pero sustituyó la conjunción original por `and`; el fragmento dejó de ser literal. |
| E09 | Completo | Décima (1) | Diferenció el aviso de ingreso de 24 horas. |
| E10 | Completo | Décima (2) | Conservó los supuestos enumerados y la redacción ambigua para revisión. |
| E11 | Completo | Décima (6-8) | Recuperó conservación continua, devolución y remisión a Primera. |
| E12 | Completo | Décima (9) | Conservó comunicación de daños dentro de 24 horas. |
| E13 | Completo | Décimo Primera | Conservó rubros y períodos sin inventar clases de expensas. |
| E14 | Completo | Décimo Segunda | Recuperó pago en término y entrega de comprobantes. |
| E15 | Completo | Décimo Cuarta | Mantuvo la eximición del locador sin inventar un pagador. |
| E16 | Rechazado | Décimo Octava, propuesta 19 | Encontró el contenido, pero la cita parafraseó y corrigió palabras del PDF; el validador la rechazó. |
| E17 | Completo | Vigésimo | Recuperó la administración como contexto y la etiquetó `contexto`. |

Cobertura con evidencia aceptada: **14/17 = 82,4%**. Cobertura de contenido
propuesto, incluyendo las tres propuestas auditables rechazadas: **17/17**.
Controles críticos con evidencia aceptada: **6/7 = 85,7%**; E06 fue encontrado
pero no se aceptó por su página incorrecta.

## Comparación con v1

| Medida | v1 | v2 |
|---|---:|---:|
| Propuestas del modelo | 18 | 20 |
| Propuestas con evidencia válida | 14 | 17 |
| Controles con evidencia aceptada | 11/17 | 14/17 |
| Controles encontrados antes del filtro | No auditables | 17/17 |
| Críticos aceptados | 6/7, faltó E07 | 6/7, E07 recuperado; E06 rechazado |
| Descartes conservados | No | Sí, 3 completos |

## Conclusiones

La v2 resolvió el principal defecto de continuidad: E07 conserva texto y
condición causal a través del salto de página. También recuperó E03, E11, E14 y
los contextos E01/E17. La validación estricta evitó aceptar tres citas alteradas
y ahora conserva suficiente información para comprender y auditar el descarte.

La cantidad de cláusulas no reemplaza la revisión semántica. E01, la penalidad
por no restitución y el aviso de desocupación fueron sugeridos como `operativa`,
aunque no deberían alimentar por defecto un reclamo ordinario de mantenimiento.
El administrador debe revisar y puede corregir `uso_clasificador` antes de
confirmar. El repositorio solo entrega al grafo cláusulas confirmadas con uso
`operativa`.

Este ejemplo fue conocido durante el ajuste y sirve como regresión. No demuestra
generalización. Antes de habilitar contratos reales se necesita evaluar un
segundo contrato de estructura diferente que no haya sido usado para diseñar el
prompt, además de resolver el tratamiento de datos del proveedor.
