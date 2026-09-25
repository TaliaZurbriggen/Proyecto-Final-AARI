# HU30 - Preparación local del prompt v4

**Fecha:** 24/09/2026. **Estado:** implementación local y preflight completos;
regresión externa bloqueada por cuota antes de producir resultados.

## Motivo

V3 mejoró los controles completos de 13/23 a 19/23 y los críticos de 7/15 a
12/15, sin aceptar alucinaciones. Persistieron dos problemas generales:

1. tres reglas de V01 fueron comprendidas, pero propuestas con citas modificadas
   quedaron correctamente bloqueadas;
2. una coordinación sintáctica de V04 fue resuelta por el modelo cuando debía
   conservarse como ambigua.

V4 busca resolver esos patrones sin relajar el anclaje y sin enumerar las
respuestas esperadas de V01-V04.

## Cambios del prompt

- Una sola regla verificable por propuesta. Las responsabilidades independientes
  se separan aunque pertenezcan al mismo inciso.
- Evidencias breves, continuas y literales; se prefieren varios fragmentos
  pequeños antes que una transcripción extensa.
- Cada cita conserva un mínimo de 24 caracteres alfanuméricos, igual al umbral
  de seguridad del anclaje local.
- Una lista explícita obliga a revisar sujeto, verbo, conceptos y alcance de
  `salvo`, `excepto`, comas y conjunciones antes de asignar responsable.
- Una coordinación con dos agrupaciones razonables debe quedar con responsable
  `no_especificado`, uso `contexto`, explicación y confianza máxima de 0,6.
- Los dos ejemplos son sintéticos y no reproducen cláusulas ni valores de los
  documentos de regresión.

## Decisiones de seguridad

El anclaje no se flexibiliza. Una palabra cambiada, paráfrasis, página incorrecta,
cita repetida o fragmento demasiado corto continúa rechazándose. Tampoco se
agregan reglas jurídicas ni se automatiza la revisión humana.

V2 y V3, sus resultados y sus revisiones permanecen inmutables. V01-V04 son
regresión conocida; H01-H02 siguen reservados por Tobías/Oikos.

## Validaciones realizadas

- Pruebas específicas de cláusulas, evidencia y corpus: **20 aprobadas y 1 OCR
  opcional omitida**.
- Suite completa del backend: **319 aprobadas y 23 omitidas**. Las omitidas son
  integraciones opcionales y no se habilitaron servicios externos.
- Simulación de coordinación ambigua: conservada como `contexto`, responsable
  `no_especificado` y confianza 0,6.
- Preflight V01-V04: hashes, documentos y 23 controles esperados aprobados.
- Directorio de resultados v4 ausente: **0 llamadas externas**.

## Criterio para la siguiente etapa

Sólo con autorización explícita se podrá ejecutar una llamada v4 por cada uno de
V01-V04, sin reintentos ni cambios intermedios. Se mantendrán los umbrales de 85%
general, 100% crítico y cero alucinaciones aceptadas. Los holdouts no se revelan
hasta que la regresión conocida cumpla.

## Intento externo del 24/09/2026

Se autorizó la regresión v4 y se invocó V01 una vez. Gemini respondió `429
RESOURCE_EXHAUSTED`: el proyecto había alcanzado el límite gratuito de 20
solicitudes diarias por proyecto y modelo. No se creó resultado ni plantilla de
revisión. El ejecutor no reintentó V01 y no envió V02-V04 para evitar repetir el
mismo fallo.

El detalle seguro está en `intento_v4_2026-09-24.json`. El prompt permanece
congelado y el directorio `resultados_corpus_v4` continúa ausente. Después del
restablecimiento de cuota hará falta una nueva autorización para iniciar la
regresión desde V01.

## Intento externo del 25/09/2026

Con nueva autorización se invocaron V01 y V02 una vez cada uno. El proveedor
respondió `503 UNAVAILABLE` por alta demanda en ambos casos. No se obtuvieron
respuestas evaluables ni se crearon archivos de resultados. V03 y V04 no fueron
enviados. El ejecutor no relanzó las llamadas fallidas.

El incidente está registrado en `intento_v4_2026-09-25.json`. El prompt sigue
congelado y la evaluación de regresión v4 continúa pendiente de disponibilidad
del modelo.
