# HU30 - Evaluación real de Gemini sobre el ejemplo 01

**Fecha:** 21/09/2026. **Modelo:** `gemini-3.5-flash`. **Prompt:** `v1`.
**Extractor:** `hu30-v1`.

La fuente fue la copia anonimizada verificada de 13 páginas, SHA-256
`3e27aa10c53c72abdeee176175420067d109456465010e5fc61a46437896b16b`.
El contrato original no fue transmitido. La ejecución exitosa utilizó salida
estructurada mediante `function_calling` y validación posterior con Pydantic.

## Resultado de ejecución

- 18 propuestas devueltas por Gemini.
- 14 propuestas aceptadas por la comprobación de evidencia.
- 4 propuestas descartadas porque el fragmento no pudo vincularse literalmente
  con las páginas declaradas.
- Tasa de aceptación de evidencia: **14/18 = 77,8%**. No equivale a precisión.
- Lectura local completa: 13/13 páginas.
- Resultado estructurado: `resultado_gemini_ejemplo_01.json`.

## Cobertura de los controles

| Control | Estado | Resultado relacionado | Observación |
|---|---|---|---|
| E01 | Omitido | — | No recuperó el inventario inicial como contexto independiente. |
| E02 | Completo | Primera; Segunda | Conservó devolución, limpieza, desocupación y funcionamiento al final. |
| E03 | Omitido | — | No recuperó la autorización previa para alteraciones/innovaciones. |
| E04 | Completo | Novena (a) | Conservó la atribución amplia y la referencia a Primera. |
| E05 | Completo | Novena (b) | Conservó la condición causal por culpa/negligencia. |
| E06 | Completo | Novena (c) | Conservó finalización, designación y pago del locatario. |
| E07 | Omitido | — | Perdió la reparación condicionada que cruza las páginas 5–6. **Crítico.** |
| E08 | Completo | Novena (e) | Conservó devolución y responsabilidad previa del locatario. |
| E09 | Completo | Décima (1) | Diferenció el aviso de ingreso de 24 horas. |
| E10 | Completo | Décima (2) | Conservó los supuestos enumerados; requiere revisión de su ambigüedad. |
| E11 | Omitido | — | No recuperó conservación continua y entrega vinculada a Primera. |
| E12 | Completo | Décima (9) | Conservó comunicación de daños dentro de 24 horas. |
| E13 | Completo | Décimo Primera | Conservó rubros y períodos; no inventó clases de expensas. |
| E14 | Omitido | — | No extrajo pago en vencimiento y entrega de comprobantes como unidad propia. |
| E15 | Completo | Décimo Cuarta | No convirtió la eximición del locador en pago automático del inquilino. |
| E16 | Completo | Décimo Octava | Conservó constancia, restitución y referencias internas. |
| E17 | Omitido | — | No recuperó el rol de administración como contexto independiente. |

Cobertura total: **11/17 = 64,7%**. Sin los dos controles de contexto secundario
E01/E17: **11/15 = 73,3%**. Controles críticos completos: **6/7 = 85,7%**;
el crítico omitido fue E07.

## Observaciones de calidad

Resultados favorables:

- Diferenció el aviso de ingreso de 24 horas, la comunicación de daños de 24
  horas y el aviso de desocupación de 30 días.
- Conservó condiciones de culpa, momento de devolución y períodos ocupados.
- No inventó una división ordinaria/extraordinaria de expensas.
- No asignó automáticamente al inquilino los daños incluidos en la eximición
  del locador.

Aspectos a corregir antes de aceptar la extracción:

- Mejorar el tratamiento de oraciones que cruzan páginas, especialmente E07.
- Recuperar E03, E11 y E14, además de los contextos E01/E17.
- Separar del contexto operativo la multa de Quinta y el aviso de desocupación
  de Novena (f); pueden mostrarse para revisión, pero no alimentar por defecto
  al clasificador de reclamos.
- Conservar en la evidencia las cuatro propuestas rechazadas y su motivo, en vez
  de registrar únicamente su número de orden, para facilitar auditoría y ajuste.

Este ejemplo era conocido al diseñar el prompt y sirve como regresión, no como
prueba independiente de generalización. La aceptación funcional exige revisión
humana y luego una evaluación con otro contrato reservado.
