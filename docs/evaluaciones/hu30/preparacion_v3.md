# HU30 - Preparación local del prompt y extractor v3

**Fecha:** 24/09/2026. **Estado:** implementación y regresión externa completas.

## Problemas que aborda

La evaluación v2 localizó 22/23 contenidos, pero sólo 13/23 quedaron completos
con evidencia aceptable. Nueve resultados fueron parciales porque Gemini corrigió
o recortó citas del PDF y uno interpretó una cláusula ambigua de gastos comunes.

V3 conserva la extracción semántica y cambia dos comportamientos:

1. Las citas se anclan localmente al texto exacto de la página.
2. Una sintaxis con más de una interpretación no debe resolverse automáticamente.

## Anclaje conservador

El backend compara los caracteres alfanuméricos de la cita y de la página,
ignorando únicamente formato: espacios, saltos, puntuación, guiones de corte y
diferencias de mayúsculas. La coincidencia debe:

- estar en la página declarada;
- tener una longitud mínima de 24 caracteres alfanuméricos;
- aparecer una sola vez;
- conservar todas las letras y números en el mismo orden.

Cuando cumple esas condiciones, el backend descarta el texto generado por el
modelo y guarda el fragmento exacto del PDF. Una palabra cambiada, una paráfrasis,
una cita breve, una coincidencia repetida o una página incorrecta se rechazan.

Ejemplo aceptado: la cita `reembolso alguno` puede anclarse al original
`reembolso a lguno`; el registro conserva `a lguno`. Ejemplo rechazado: cambiar
`conservar` por `reparar` no es una diferencia de formato.

El validador v2 permanece disponible para reproducir las evaluaciones históricas.
El servicio de HU30 usa el nuevo anclaje únicamente a partir de la versión v3.

## Prompt v3

El prompt exige fragmentos breves, continuos y literales, sin `...` ni
correcciones de OCR. Para una redacción ambigua ordena:

- no elegir una interpretación;
- usar `responsable: no_especificado`;
- describir la ambigüedad en `condiciones`;
- proponer `uso_clasificador: contexto` hasta la revisión humana.

No se añadieron columnas ni migraciones. Todas las propuestas ya requieren
revisión y el esquema existente admite `no_especificado`, `condiciones` y
`contexto`.

## Reprocesamiento local de descartes v2

Se reprocesaron las 10 propuestas rechazadas de V01-V04 sin llamar a Gemini:

| Resultado | Cantidad |
|---|---:|
| Recuperadas por diferencia exclusiva de formato | 2 |
| Correctamente rechazadas todavía | 8 |

Siete rechazos de V01 usaban `...` para omitir texto intermedio; no son citas
continuas y v3 no debe aceptarlas. El rechazo de V02 cambiaba caracteres y
contenía incluso la palabra inglesa `during`; también debe seguir bloqueado. La
evidencia completa está en `reanclaje_v3_sobre_descartes_v2.json`.

Este resultado bajo no invalida el anclaje: confirma que es conservador. La
mejora restante depende de que el prompt v3 produzca citas continuas y sin
correcciones, lo que requiere una nueva ejecución externa para medirse.

## Congelación y pruebas

`corpus_v3_manifest.json` congela por SHA-256 el prompt, el adaptador y el
anclaje. V01-V04 pasan a ser regresión conocida; H01-H02 siguen reservados.

Resultados locales:

- Pruebas específicas de cláusulas, corpus y anclaje: **18 aprobadas, 1 OCR opcional omitida**.
- Suite completa del backend: **317 aprobadas, 23 omitidas**.
- Preflight V01-V04: hashes, documentos y 23 resultados esperados aprobados.
- Reprocesamiento de descartes: **0 llamadas externas**.

## Regresión externa

Con autorización explícita se ejecutó una llamada v3 por V01-V04, sin reintentos
ni cambios intermedios. V3 obtuvo 19/23 controles completos (82,6%), 12/15
críticos completos (80%) y cero alucinaciones aceptadas. Mejoró de forma material
frente a v2, pero no alcanzó los umbrales de 85% general y 100% crítico.

La evaluación detallada está en `evaluacion_corpus_v3.md`. H01-H02 permanecen
reservados porque la regresión conocida todavía no cumple.
