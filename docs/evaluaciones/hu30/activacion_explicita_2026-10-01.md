# HU30: activación explícita de cláusulas — 01/10/2026

## Contexto y decisión

El ensayo v5 sobre el contrato público V04 recuperó cinco cláusulas y el
verificador de citas las aceptó, pero una interpretación de gastos comunes
seguía siendo ambigua y fue sugerida como `operativa`. Antes de este cambio,
ninguna propuesta llegaba al clasificador sin revisión humana; sin embargo,
la acción **Confirmar** conservaba la etiqueta `operativa` sugerida por Gemini.
Una confirmación rápida podía incorporar esa interpretación sin que la persona
eligiera expresamente usarla en reclamos.

Talía aprobó una política uniforme: **todas las propuestas generadas por IA
ingresan como `contexto`**, incluso las que el modelo considere claras.
Confirmar una propuesta la mantiene como contexto. Sólo la acción **Editar**
con la elección explícita `uso_clasificador=operativa` puede habilitarla para
reclamos. La propuesta original se conserva para auditoría; un evento de
revisión deja constancia de la activación. La consulta del clasificador exige
que la cláusula esté editada, marcada como operativa y tenga ese evento.
Esto excluye también las confirmaciones o ediciones antiguas que no registraron
una habilitación explícita; pueden revisarse y activarse desde la interfaz.

No se incorporaron heurísticas de palabras como `salvo` o `excepto`: podrían
pasar por alto otra ambigüedad o bloquear reglas claras. Tampoco se añadió
una llamada a Gemini para revisar al propio Gemini. El costo de la decisión
es una edición adicional para cada regla que deba participar en reclamos.

## Alcance

- Backend: persistencia inicial como contexto sin perder `propuesta_original`,
  revisión conservadora, evento explícito y filtro de consulta para reclamos.
- Interfaz: «Confirmar como contexto» y editor con uso inicial contextual;
  sólo una selección deliberada muestra «Guardar y habilitar». Una cláusula
  confirmada sigue siendo editable. Se reutilizaron los componentes y tokens
  existentes, sin cambiar navegación ni agregar estilos especiales.
- Sin migración ni nuevas dependencias. El prompt v4 en producción y el ensayo
  experimental v5 no cambiaron. No se consultaron Gemini ni Supabase.

## Verificación y límites

Las pruebas locales cubrieron guardado inicial, preservación de la propuesta,
confirmación de filas antiguas, edición sin selección operativa, activación
explícita y exclusión en la consulta de reclamos. La prueba PostgreSQL aislada
con rollback se actualizó, pero **no se ejecutó** porque requiere autorización
para Supabase. La suite de backend, incluido OCR español, terminó con **356
aprobadas, 22 omitidas y dos advertencias de bibliotecas**. La suite completa
de frontend terminó con **106 aprobadas en 24 archivos** usando el pool de
threads y dos trabajadores. Lint y build aprobaron. Dos intentos previos de la
suite frontend con el pool predeterminado fallaron por un timeout intermitente
en pruebas ajenas a contratos y otro por arranque del trabajador; esas pruebas
pasaron aisladas y la corrida final completa aprobó.

Esta protección **no corrige** el resumen ambiguo de V04 ni convierte la
evaluación v5 en aprobada: su cobertura sigue siendo 4/5 y 2/3 críticos.
La persona administradora debe comparar cada regla con el PDF y decidir si
su interpretación puede utilizarse; la aprobación de interfaz no equivale a
validación jurídica por Oikos. V01–V03 requieren autorizaciones separadas para
evaluaciones externas. H01–H02 continúan reservados.

La decisión queda en el repositorio. Notion estaba limitado por bloques y, al
intentar acceder ahora a la página de decisiones, su API respondió dos veces
`500` (`Cross-cell memcached access is not allowed`), por lo que no se pudo
actualizar allí. No implica commit, push, PR ni cierre de Jira.
