# HU30 - Resultados esperados del ejemplo 01

**Fecha:** 14/09/2026. **Estado:** referencia comparada con una ejecución real el
21/09/2026; ver [evaluación observada](evaluacion_gemini_ejemplo_01.md).

## Procedencia y uso

Fuente de trabajo: [copia anonimizada de prueba](../../../output/pdf/hu30_contrato_anonimizado.pdf), 13 páginas, con texto digital. Proviene de un contrato aportado por la persona responsable del proyecto; **no es un contrato de Oikos**. Las expectativas se construyeron por lectura del documento: no representan reglas validadas por Oikos, un dictamen jurídico ni resultados observados del modelo.

La numeración de páginas se conserva respecto del documento original. Este último permanece fuera del repositorio. El preparador local no contiene nombres, identificadores ni rutas del original y no es un anonimizador de propósito general.

La copia mantiene títulos, apartados, negaciones, condiciones, referencias internas, plazos relativos y porcentajes. Sustituye identidades, domicilios, contactos, administración identificable, fechas concretas y montos particulares por etiquetas. Los espacios grises indican información retirada; no son campos a completar ni cláusulas nuevas. Se mantiene el texto restante, incluidas sus imprecisiones. No usar la copia para celebrar un contrato.

## Cómo leer las expectativas

Los siguientes **17 controles** cubren unidades de significado, no una cantidad obligatoria de objetos JSON. Un resultado puede agrupar dos obligaciones si conserva sus referencias y condiciones; no se exige copiar literalmente estos resúmenes ni este orden. Se debe preservar el fragmento literal, la página o páginas y el apartado que respalda cada resultado.

"Responsable según el texto" describe lo que el documento atribuye. No equivale a fijar `tipo_gasto`, a comprobar validez jurídica ni a habilitar automáticamente una excepción para el clasificador. Todas las sugerencias quedan pendientes de revisión humana.

## Controles de contenido

| ID | Referencia | Contenido esperado y condiciones indispensables | Responsable según el texto / control |
|---|---|---|---|
| E01 | Primera, pp. 1-2 | Inventario y estado declarado de artefactos y accesorios, incluyendo calefón y portero eléctrico. Distinguir inventario de obligación de reparar. | No asignar un pagador de reparaciones a partir de la mera presencia de un artefacto. Contexto secundario. |
| E02 | Primera y Segunda, p. 2 | Restituir al finalizar la locación el inmueble desocupado, limpio y con artefactos y accesorios en buen estado; conservar el contexto de devolución. | Locatario. No convertir una obligación al final del alquiler en un diagnóstico durante la ocupación. |
| E03 | Octava, pp. 4-5 | Las alteraciones o innovaciones requieren consentimiento expreso previo del locador. Conservar los efectos descriptos sobre mejoras, eventual demolición/reconstrucción y gastos. | Locatario respecto de las actuaciones y costos descriptos; locador respecto de autorización. No resumir como prohibición absoluta de toda reparación. |
| E04 | Novena a), p. 5 | Registrar la atribución amplia de mantenimiento y reparación de elementos enumerados y reposición, incluido su alcance literal amplio. | El texto atribuye al locatario. Debe mostrarse junto con E05/E07 como posible tensión de alcance; no resolverla automáticamente ni convertirla en regla universal. **Crítico.** |
| E05 | Novena b), p. 5 | Responsabilidad por hechos dañosos originados en el accionar culposo o negligente de moradores o terceros presentes. | Locatario, preservando la condición causal y los sujetos mencionados. **Crítico.** |
| E06 | Novena c), p. 5 | Pintura al finalizar el contrato, por vencimiento o rescisión; pintor designado por la administración y gastos de materiales y mano de obra. | Locatario como pagador indicado. No extenderlo a cualquier deterioro de pintura durante la vigencia. La administración designa; no es el pagador. **Crítico.** |
| E07 | Novena d), pp. 5-6 | Reparación por cuenta del locatario de desperfectos o roturas cuando su causa sea imputable a este por motivos culposos. La oración comienza en p. 5 y la condición aparece en p. 6. | Locatario condicionado a esa causa. Debe conservarse la condición aunque se procese por páginas. **Crítico.** |
| E08 | Novena e), p. 6 | Consecuencia económica durante las reparaciones de desperfectos de los que el locatario sea responsable, detectados al devolver el inmueble. | Locatario; conservar el momento de devolución y la condición de responsabilidad. No confundir el alquiler devengado con presupuesto de reparación. |
| E09 | Décima 1), p. 6 | Permitir ingreso del locador, administrador o autorizado para inspección/trabajo con aviso previo de 24 horas. | Locatario permite; locador/representante realiza visita. El plazo se refiere al aviso previo de ingreso. |
| E10 | Décima 2), p. 6 | Gastos de reparación por los supuestos enumerados: incendio, explosión, referencia a motivos culposos, robo o tentativa. | El texto los atribuye al locatario. Conservar la enumeración y su redacción para revisión; no inventar una condición común ni resolver ambigüedades. |
| E11 | Décima 6)-8), pp. 6-7 | Conservación durante la ocupación y entrega en el estado recibido, con remisión a la Primera. Separar obligación continua de obligación de entrega. | Locatario. Preservar el vínculo con la descripción inicial; evitar duplicados con E02. |
| E12 | Décima 9), p. 7 | Comunicar daños o deterioros al locador o representante dentro de las 24 horas de producidos, cualquiera sea el motivo. | Locatario comunica; locador/representante recibe. No confundir con el aviso de visita E09 ni asignar por ello quién paga. **Crítico.** |
| E13 | Décima Primera, p. 7 | Impuestos municipales/provinciales, tasas, servicios y expensas atribuidos por el texto al locatario, vinculados a períodos ocupados. | Preservar rubros diferentes y condición temporal. No inventar distinción ordinaria/extraordinaria de expensas que el párrafo no expresa ni traducir todos los conceptos a `ordinario`. **Crítico.** |
| E14 | Décimo Segunda, pp. 7-8 | Abonar conceptos dentro de vencimientos y entregar comprobantes a la administración. | Locatario paga y entrega; administración recibe. Separar la obligación documental de una decisión sobre la causa del gasto. |
| E15 | Décimo Cuarta, p. 8 | Registrar que el documento expresa una eximición del locador frente a los daños/supuestos enumerados. | Locador es el sujeto eximido en el texto. **No se expresa por ello que el inquilino sea automáticamente el pagador de toda reparación.** Señalar para revisión antes de cualquier uso. **Crítico.** |
| E16 | Décimo Octava, p. 10 | Entrega de llaves con constancia escrita, restitución del inmueble y comprobación de pagos referidos a Décima Primera/Décimo Segunda. | Locatario en la restitución; locador/representante en la recepción. Conservar referencias y no duplicar E02/E14. |
| E17 | Vigésimo, p. 12 | Identificar el rol de la administración designada y diferenciarlo de locador y locatario. | La administración interviene en gestión; no se infiere que deba solventar las reparaciones. Contexto secundario. |

## Temas que no deben alimentar por defecto al clasificador de reclamos

El PDF se conserva completo. Sin embargo, el análisis enfocado en mantenimiento/reparaciones no necesita transformar todas sus disposiciones en reglas de gasto:

- Precio e índice de ajuste (Tercera), forma de pago (Cuarta), mora y sanciones (Quinta/Décimo Tercera): no son causa técnica ni clasificación de una reparación.
- Destino (Sexta), cesión/subalquiler (Séptima), garantías personales (Décimo Quinta/Sexta), rescisión (Décimo Séptima), jurisdicción/domicilios (Décimo Novena) y sellado (Vigésimo Primero): pueden quedar fuera del resultado relevante de HU30.
- Aviso de desocupación con 30 días (Novena f): no confundir con aviso de desperfecto de 24 horas.
- Etiquetas de anonimización y pie de página: no son datos faltantes que Gemini deba reconstruir ni obligaciones contractuales.

Si se devuelven como información complementaria, debe quedar separada del contexto que recibe el clasificador; no contarlos como falsos positivos por el mero hecho de detectarlos. Sí es un error tratarlos como reglas operativas de reparación sin relación con el reclamo.

## Matriz de errores a detectar

1. Cortar E07 antes de su condición en la página siguiente.
2. Resumir E04-E07 como "el inquilino paga cualquier rotura".
3. Aplicar E06 a un reclamo de pintura sin conservar que se refiere a la finalización.
4. Mezclar los dos plazos de 24 horas (E09/E12) o con el de 30 días de desocupación.
5. Inventar un pagador a partir de una eximición (E15).
6. Inventar una división de expensas ausente del texto (E13).
7. Tratar al administrador que designa un pintor como responsable de pagarle (E06).
8. Omitir apartados, duplicarlos por solapamiento de fragmentos o perder sus referencias.
9. Resolver automáticamente la posible tensión E04/E07 o modificar las reglas generales de Oikos a partir de este ejemplo.
10. Citar texto inexistente, incluir etiquetas como cláusulas o inventar identidades/fechas retiradas.

## Registro de evaluación propuesto

Una revisión futura registrará para cada E01-E17: `completo`, `parcial`, `omitido` o `incorrecto`, junto con las cláusulas generadas que lo respaldan. Se admiten equivalencias semánticas de resumen/categoría; el texto de evidencia debe coincidir con la fuente tras normalizar únicamente espacios/saltos y ligaduras equivalentes.

- **Cobertura:** controles completos / 17. Un error o respuesta inválida no reduce el denominador. Reportar aparte los dos controles de contexto (E01/E17).
- **Fidelidad:** revisar cada afirmación y su evidencia; registrar afirmaciones inventadas y condiciones perdidas por separado. No usar el número de objetos JSON como medida de calidad.
- **Controles críticos:** E04, E05, E06, E07, E12, E13 y E15 deben conservar sus condiciones y atribuciones para aceptar este ejemplo.
- **Trazabilidad:** páginas/apartados correctos, versión de PDF, hash de la copia, modelo y versión del prompt.
- **Datos observados:** 18 propuestas, 14 con evidencia aceptada y cobertura de
  11/17 controles. Los detalles y limitaciones están en la evaluación enlazada.

Este archivo es una referencia de desarrollo ya conocida al diseñar el prompt, **no un conjunto de evaluación reservado**. Un segundo contrato con otra estructura deberá conservarse sin usar para ajustar el prompt y evaluarse después de fijar esa versión. Variantes del mismo documento sirven para regresión, no cuentan como documentos independientes.

## Pruebas adicionales que no cubre este PDF

- PDF escaneado y mixto (lectura local + OCR por página).
- Texto rotado, mala resolución, negaciones o números mal reconocidos.
- Contrato sin cláusulas relevantes, ambiguo, ilegible o con análisis incompleto.
- Instrucciones incrustadas que intentan modificar la tarea del modelo.
- Fallas de Gemini, timeout, JSON malformado, referencias inexistentes, duplicación y pérdida de condiciones al unir fragmentos.
- Versionado, permisos, revisión humana y selección temporal del contrato en el grafo.
