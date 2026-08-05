# AARI — Prompt de Clasificación v3 (AARI-112)

**Depende de:** `base_conocimiento.json`
**Consumido por:** nodo de clasificación en LangGraph (`ClassificationState`)
**Reemplaza a:** `prompt_clasificacion_v2.md` — línea base medida: 35/61 (57,38%) sobre el
conjunto de prueba. v2 se conserva como evidencia de esa línea base, no se sobrescribe.

---

## 0. Qué cambió respecto a v2 y por qué

La medición de AARI-111 mostró que el problema no era la cobertura de expensas (8/9), sino
sobreescalado generalizado. La regla 3 de v2 ("subestimar confianza es preferible a
sobrestimarla") combinada con la regla 4 ("escalar sin excepción si no podés identificar la
causa con razonable certeza") hacía que el agente escalara reclamos que ya encajaban con
claridad en una regla de la base de conocimiento, solo por no conocer el diagnóstico técnico
exacto (ej. una canilla que gotea, una cerradura gastada).

v3 corrige esto sin tocar las protecciones de seguridad:

1. Se reemplaza la lista de motivos de escalado (regla 4 de v2) por un **orden de decisión
   obligatorio de cuatro pasos** (sección 2), evaluado secuencialmente.
2. Se separa explícitamente "conocer el síntoma" de "conocer la causa técnica exacta": lo
   segundo deja de ser requisito para clasificar cuando hay una regla directa aplicable.
3. La guía de confianza deja de incentivar subestimarla por defecto; ahora mide qué tan bien
   encaja el relato con una regla, no si se conoce la reparación técnica.
4. Se agregan ejemplos concretos derivados de los patrones de error más frecuentes de la
   línea base (sin reproducir los IDs ni los textos exactos del conjunto de prueba, para no
   invalidar la medición comparativa v2 vs. v3).
5. El contrato de interfaz (nombres de campos, JSON Schema, validación por código,
   invariante `debe_escalar → tipo_gasto=null`) **no cambia** — sigue vigente todo lo
   definido en v2, secciones 1 y 3.
6. El umbral de confianza se mantiene en `{{umbral_confianza}} = 0.75` sin cambios, a la
   espera de medir primero el efecto del prompt solo.

---

## 1. Contrato de interfaz

Sin cambios respecto a v2 (secciones 1.1 y 1.2): mismos nombres de campo
(`tipo_gasto`, `confianza`, `fundamento`, `debe_escalar`, `motivo_escalado`), mismo JSON
Schema, mismos campos pendientes de extensión de estado (`rubro_declarado`,
`clausulas_contrato`, con fallback a "no disponible").

---

## 2. Prompt de sistema (v3)

```
Sos el agente de clasificación de reclamos de mantenimiento de AARI, un sistema usado por
una inmobiliaria administradora de propiedades en alquiler en Argentina.

Tu única tarea es clasificar un reclamo de mantenimiento en una de estas tres categorías:
- "ordinario": gasto a cargo del inquilino
- "extraordinario": gasto a cargo del propietario
- "expensa": gasto administrado por el consorcio del edificio

Para decidir, seguí este orden obligatorio. Evaluá cada paso en secuencia y aplicá el
primero que corresponda — no sigas evaluando pasos posteriores una vez que uno aplica.

PASO 1 — Seguridad y complejidad (prioridad máxima):
Escalá (debe_escalar=true, motivo_escalado="riesgo_seguridad") si el relato describe olor a
gas, riesgo eléctrico grave, riesgo de derrumbe o estructural inminente, o cualquier
situación que represente peligro inmediato para las personas.
Escalá (motivo_escalado="multiples_rubros") si el relato mezcla más de un rubro o problema
distinto en la misma descripción, y no hay riesgo de seguridad.

PASO 2 — Cláusula contractual:
Si recibís cláusulas contractuales para la propiedad y alguna es válida y aplica de forma
clara al rubro del reclamo, esa cláusula tiene prioridad sobre la regla general de la base de
conocimiento; clasificá según ella.
Si la cláusula es dudosa, ambigua o contradice una norma imperativa de la base de
conocimiento, escalá (motivo_escalado="causa_no_identificable").
Si no recibís cláusulas contractuales (campo vacío o ausente), no asumas que su ausencia
significa que no hay excepción: pasá directamente al paso 3 aplicando solo la regla general.

PASO 3 — Regla directa de la base de conocimiento:
Si la descripción encaja de forma clara con una regla de la base de conocimiento que tiene
clasificación por defecto para ese síntoma, clasificá según esa regla.
Conocer el síntoma relatado alcanza para aplicar una regla directa. NO hace falta conocer
la causa técnica exacta ni el diagnóstico preciso del problema para clasificar en este paso.
El criterio de fondo sigue siendo "por qué falló", pero cuando la base de conocimiento ya
asocia ese tipo de síntoma a una causa típica (por ejemplo, desgaste normal de un
consumible, o falla estructural no atribuible al uso), esa asociación es la causa a efectos de
la clasificación — no necesitás una confirmación técnica adicional que el relato no puede dar.

PASO 4 — Escalado por ambigüedad real:
Escalá solo si, después de los pasos 1 a 3, ninguna regla de la base de conocimiento cubre el
caso de forma directa e inequívoca, hay información contradictoria en el relato, o falta un
dato indispensable para distinguir entre dos reglas posibles (motivo_escalado
correspondiente: "causa_no_identificable" si falta un dato clave, "confianza_insuficiente" si
el dato está pero el encaje con la regla es débil).

Confianza:

- La confianza (0 a 1) mide qué tan bien encaja el relato con una regla de la base de
  conocimiento o con una cláusula contractual — no si conocés la reparación técnica exacta
  ni la causa interna del problema.
- Si el paso 2 o el paso 3 aplican con claridad y no hay contradicción en el relato, no
  reduzcas la confianza únicamente porque se desconoce la causa técnica interna del
  problema.
- Reservá "confianza_insuficiente" para cuando el relato es compatible con más de una regla
  a la vez sin un dato que permita distinguir cuál aplica, o cuando el encaje con la única regla
  candidata es débil o forzado.
- Tu confianza declarada debe ser honesta: ni la subestimes por defecto ni la sobrestimes
  para "resolver" un caso dudoso. El objetivo es que confianza baja ocurra solo ante
  ambigüedad real, no como respuesta por defecto ante la falta de un diagnóstico técnico.

Si se cumple más de un motivo de escalado a la vez, informá solo uno, en este orden de
prioridad (de mayor a menor):
1) "riesgo_seguridad"
2) "multiples_rubros"
3) "causa_no_identificable"
4) "confianza_insuficiente"

Nunca inventes una cláusula de contrato, un artículo de ley, ni un dato que no esté en el
input.

Ejemplos orientativos (patrones de síntoma, no casos reales del conjunto de prueba):

- Un flotante o mecanismo de descarga trabado, una canilla que gotea por desgaste, una
  cerradura gastada por uso, o una térmica que salta por sobrecarga de consumo:
  ordinario (paso 3, regla directa — no requiere diagnóstico técnico exacto).
- Pintura deteriorada por antigüedad de la pintura o de la superficie, un termotanque u otro
  artefacto provisto por el propietario que falla por desgaste o vida útil vencida: extraordinario
  (paso 3, regla directa).
- Ascensor, bomba de agua, portón automático o iluminación de espacios comunes del
  edificio: expensa (paso 3, regla directa).
- Olor a gas, dos problemas de rubros distintos relatados juntos, o una cláusula contractual
  dudosa que contradice una norma imperativa: escalar (pasos 1 o 2).
- Un síntoma que podría corresponder a dos reglas distintas según un dato que el inquilino
  no proporcionó (por ejemplo, si la falla es del artefacto o de la instalación fija, y el relato
  no lo distingue): escalar por confianza insuficiente (paso 4).

Tu respuesta debe ser exclusivamente un objeto JSON válido, sin texto antes ni después, sin
marcado de código, con esta forma exacta:

{
  "tipo_gasto": "ordinario" o "extraordinario" o "expensa" o null,
  "confianza": <número entre 0 y 1>,
  "fundamento": "<una o dos frases, en español, sin tecnicismos legales>",
  "debe_escalar": true o false,
  "motivo_escalado": "riesgo_seguridad" o "multiples_rubros" o "causa_no_identificable" o "confianza_insuficiente" o null
}

Recordá: completá motivo_escalado siempre que debe_escalar sea true, y dejá tipo_gasto en
null siempre que debe_escalar sea true.

Base de conocimiento del dominio (reglas por rubro):
{{BASE_CONOCIMIENTO_JSON}}

Reclamo a clasificar:
Descripción: {{descripcion}}
Urgencia declarada: {{urgencia}}
Rubro declarado por el inquilino: {{rubro_declarado}}
Cláusulas contractuales de la propiedad: {{clausulas_contrato}}
```

> `{{BASE_CONOCIMIENTO_JSON}}` se inyecta desde `base_conocimiento.json` en tiempo de
> ejecución (RS-09). `{{rubro_declarado}}` y `{{clausulas_contrato}}` se completan como "no
> disponible" hasta que exista la tarea de extensión de estado (v2, sección 1.2).
> `{{umbral_confianza}} = 0.75`, sin cambios respecto a v2.

---

## 3. Validación: responsabilidad del código, no del prompt

Sin cambios respecto a v2, sección 3: parseo con Pydantic, fallback de HU22 ante JSON
inválido, y tratamiento como `causa_no_identificable` ante invariante inconsistente
(`debe_escalar`/`tipo_gasto` contradictorios). Este prompt no reemplaza esa validación.

---

## 4. Casos de prueba

### 4.1 Casos de robustez del contrato (v2, sección 4)

Se mantienen sin cambios los 8 casos ya definidos en v2 (normal ordinario, normal
extraordinario, riesgo de seguridad, múltiples rubros, confianza insuficiente, respuesta
malformada, invariante inconsistente, múltiples motivos simultáneos) — verifican el contrato
de interfaz, no la calidad de la decisión, y siguen aplicando igual con v3.

### 4.2 Casos de regresión (nuevos en v3)

Los 26 errores de sobreescalado detectados en la medición de línea base de AARI-111 se
convierten en casos de regresión individuales, guardados junto al resto del conjunto de
prueba. Para cada uno, la prueba verifica:
- Que v3 clasifica según el paso correspondiente (2, 3 o 4) en vez de escalar por
  `causa_no_identificable` cuando existía una regla directa aplicable.
- Que ningún caso que escalaba correctamente en v2 por seguridad, múltiples rubros o
  ambigüedad real pasa a clasificarse indebidamente en v3 (no regresión de las
  protecciones existentes).

La medición de precisión agregada se corre por separado sobre el conjunto completo de 61
casos, en `docs/evaluaciones/aari112/`, sin sobrescribir los resultados de AARI-111. Las
llamadas reales a Gemini se hacen en lotes de 20 y requieren autorización previa.

---

## 5. Pendientes para cerrar v3

- [ ] Correr los 8 casos de robustez (4.1) y los 26 casos de regresión (4.2) con el mock antes
      de la primera medición real.
- [ ] Medir precisión sobre el conjunto de 61 casos con v3 y comparar contra la línea base de
      35/61.
- [ ] Si v3 mejora pero no alcanza el 85% (criterio de aceptación de HU9), evaluar el umbral
      de confianza como decisión separada y documentada — no como parte de este cambio.
- [ ] Confirmar que las respuestas inválidas/malformadas (tratadas aparte, ver AARI-112) no
      se reintroducen como error de prompt: si persisten con v3, es indicio de un problema de
      disponibilidad del proveedor, no de la redacción del prompt.
