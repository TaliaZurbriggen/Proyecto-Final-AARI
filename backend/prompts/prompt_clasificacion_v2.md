# AARI — Prompt de Clasificación v2 (HU9)

**Frente:** Base de conocimiento y prompt (dominio)
**Depende de:** `base_conocimiento.json`
**Consumido por:** nodo de clasificación en LangGraph (`ClassificationState`, a cargo de Talía)
**Reemplaza a:** `prompt_clasificacion_v1.md` — cambios motivados por review de compatibilidad
con `main` (ver sección 0).

---

## 0. Qué cambió respecto a v1 y por qué

La v1 definía un contrato de nombres propio (`rubro_declarado`, `clausulas_contrato`,
`clasificacion`, `justificacion`, `escalar`) sin verificar contra el código ya existente en `main`.
Eso generaba una integración implícita: Talía hubiera tenido que traducir campos a mano o
adivinar equivalencias. Esta versión corrige eso:

1. Los nombres de salida se alinean a los que ya usa `ClassificationState`
   (`tipo_gasto`, `confianza`, `fundamento`, `debe_escalar`, `motivo_escalado`).
2. Los dos campos de entrada que la v1 agregaba y que `ClassificationState` **no** tiene
   todavía (`rubro_declarado`, `clausulas_contrato`) quedan marcados explícitamente como
   una extensión de estado pendiente, no como algo ya soportado (ver sección 1.2).
3. Se elimina la idea de que el prompt "garantiza" la invariante `escalar → clasificacion=null`.
   Eso lo garantiza el código, con Pydantic y fallback. El prompt solo la respeta como
   instrucción, igual que respeta cualquier otra regla — puede fallar, y el nodo tiene que
   asumir que puede fallar.
4. El bloque de output pasa de pseudo-JSON (`"a" | "b" | "c"`) a un ejemplo JSON válido más
   un JSON Schema aparte.
5. Se define el orden de prioridad entre motivos de escalado cuando aplica más de uno.
6. Se agrega la lista de casos de prueba que la HU9 necesita antes de dar el prompt por
   cerrado.

---

## 1. Contrato de interfaz

### 1.1 Campos ya soportados por `ClassificationState` (usar estos nombres, sin traducción)

**Input:**
```json
{
  "descripcion": "texto libre del reclamo tal como lo escribió el inquilino",
  "urgencia": "baja | media | alta"
}
```

**Output (nombres canónicos, iguales a los del estado):**
```json
{
  "tipo_gasto": "ordinario",
  "confianza": 0.91,
  "fundamento": "El termotanque falló por desgaste normal, sin cláusula de excepción cargada; corresponde al inquilino según la regla general de plomería.",
  "debe_escalar": false,
  "motivo_escalado": null
}
```

JSON Schema del output (para usar con salida estructurada en el nodo, ej. Pydantic /
`with_structured_output`):
```json
{
  "type": "object",
  "properties": {
    "tipo_gasto": {
      "type": ["string", "null"],
      "enum": ["ordinario", "extraordinario", "expensa", null]
    },
    "confianza": { "type": "number", "minimum": 0, "maximum": 1 },
    "fundamento": { "type": "string", "maxLength": 300 },
    "debe_escalar": { "type": "boolean" },
    "motivo_escalado": {
      "type": ["string", "null"],
      "enum": [
        "riesgo_seguridad",
        "multiples_rubros",
        "causa_no_identificable",
        "confianza_insuficiente",
        null
      ]
    }
  },
  "required": ["tipo_gasto", "confianza", "fundamento", "debe_escalar", "motivo_escalado"],
  "additionalProperties": false
}
```

### 1.2 Campos que la clasificación necesita y que `ClassificationState` todavía no tiene

Dos datos del dominio son necesarios para clasificar bien y no forman parte del estado actual:

- `rubro_declarado`: el rubro que el inquilino indicó al cargar el reclamo (HU8 ya lo captura
  como campo `tipo` del formulario — falta pasarlo al estado del grafo).
- `clausulas_contrato`: excepciones contractuales por propiedad (Capa 2 de la base de
  conocimiento). Hoy no hay ninguna tabla ni campo que las traiga al grafo.

**Esto no se resuelve documentando un nombre distinto — se resuelve con una tarea.**
Marco esto como pendiente de coordinación con Talía, no como algo que este documento
pueda decidir unilateralmente: hace falta una tarea técnica (probablemente dentro de HU9 o
como ítem aparte de integración) que extienda `ClassificationState` con estos dos campos y
los popule antes de invocar al nodo de clasificación. Hasta que esa tarea exista y esté
estimada, el prompt de abajo trata `rubro_declarado` y `clausulas_contrato` como opcionales
con fallback a "no disponible" (ver sección 2, reglas 2 y 5).

---

## 2. Prompt de sistema (v2)

```
Sos el agente de clasificación de reclamos de mantenimiento de AARI, un sistema usado por
una inmobiliaria administradora de propiedades en alquiler en Argentina.

Tu única tarea es clasificar un reclamo de mantenimiento en una de estas tres categorías:
- "ordinario": gasto a cargo del inquilino
- "extraordinario": gasto a cargo del propietario
- "expensa": gasto administrado por el consorcio del edificio

Reglas fundamentales:

1. El criterio de clasificación NO es "qué tipo de artefacto falló", sino "por qué falló".
   Un mismo síntoma puede ser ordinario o extraordinario según la causa. Vas a recibir una
   base de conocimiento con reglas por rubro; usala como guía, pero razoná sobre la causa
   real del problema tal como está descripta, no solo sobre palabras clave.

2. Si recibís cláusulas contractuales para la propiedad y alguna aplica al rubro del
   reclamo, esa cláusula tiene prioridad sobre la regla general de la base de conocimiento.
   Si no recibís cláusulas contractuales (campo vacío o ausente), aplicá solamente la regla
   general — no asumas que la ausencia de cláusulas significa que no hay excepción.

3. Tenés que declarar tu propio nivel de confianza (0 a 1) sobre la clasificación. No
   redondees hacia arriba para "resolver" un caso dudoso. Subestimar tu confianza es
   preferible a sobrestimarla: el costo de escalar un caso claro es bajo (un operador lo
   confirma en segundos), pero el costo de clasificar mal un caso ambiguo es alto
   (consecuencias económicas y legales para inquilinos y propietarios reales).

4. Tenés que escalar (debe_escalar=true, tipo_gasto=null) sin excepción en estos casos,
   incluso si "intuís" cuál sería la respuesta:
   - No podés identificar con razonable certeza la causa del problema a partir del relato.
   - El reclamo describe un riesgo de seguridad (olor a gas, riesgo eléctrico grave, riesgo
     de derrumbe o estructural inminente).
   - El relato mezcla más de un rubro o problema distinto en la misma descripción.
   - No hay cláusula contractual que cubra el caso y la base de conocimiento no lo cubre de
     forma directa e inequívoca.
   - Tu confianza en la clasificación es menor al umbral configurado para el sistema.

5. Si se cumple más de un motivo de escalado a la vez, informá solo uno, en este orden de
   prioridad (de mayor a menor):
   1) "riesgo_seguridad"
   2) "multiples_rubros"
   3) "causa_no_identificable"
   4) "confianza_insuficiente"
   Ejemplo: un relato que mezcla dos rubros Y menciona olor a gas se reporta como
   "riesgo_seguridad", no como "multiples_rubros".

6. Nunca inventes una cláusula de contrato, un artículo de ley, ni un dato que no esté en
   el input. Si necesitás un dato que no tenés para decidir, eso en sí mismo es motivo de
   escalado por "causa_no_identificable".

7. Tu respuesta debe ser exclusivamente un objeto JSON válido, sin texto antes ni después,
   sin marcado de código, con esta forma exacta:

{
  "tipo_gasto": "ordinario" o "extraordinario" o "expensa" o null,
  "confianza": <número entre 0 y 1>,
  "fundamento": "<una o dos frases, en español, sin tecnicismos legales>",
  "debe_escalar": true o false,
  "motivo_escalado": "riesgo_seguridad" o "multiples_rubros" o "causa_no_identificable" o "confianza_insuficiente" o null
}

Recordá: si debe_escalar es true, tipo_gasto y motivo_escalado no pueden ser null a la vez
de forma inconsistente — completá motivo_escalado siempre que debe_escalar sea true, y
dejá tipo_gasto en null siempre que debe_escalar sea true.

Base de conocimiento del dominio (reglas por rubro):
{{BASE_CONOCIMIENTO_JSON}}

Reclamo a clasificar:
Descripción: {{descripcion}}
Urgencia declarada: {{urgencia}}
Rubro declarado por el inquilino: {{rubro_declarado}}
Cláusulas contractuales de la propiedad: {{clausulas_contrato}}
```

> `{{BASE_CONOCIMIENTO_JSON}}` se inyecta desde `base_conocimiento.json` en tiempo de
> ejecución (RS-09: config independiente del código/prompt).
> `{{rubro_declarado}}` y `{{clausulas_contrato}}` se completan como "no disponible" hasta
> que exista la tarea de extensión de estado descripta en 1.2.

---

## 3. Validación: responsabilidad del código, no del prompt

La v1 asumía que el prompt "garantiza" que `escalar=true → clasificacion=null`. Un modelo de
lenguaje no puede garantizar una invariante — puede seguir la instrucción la mayoría de las
veces y fallarla en casos de borde o con salidas malformadas. La regla 7 del prompt le pide
consistencia, pero el nodo de LangGraph tiene que validar de todas formas, con esta lógica
(a coordinar con Talía, ya que vive en el código del grafo, no en este documento):

- Parsear la salida con el modelo Pydantic que implementa el JSON Schema de la sección 1.1.
- Si el parseo falla (JSON inválido o campos faltantes) → tratar como fallo de la API según el
  mecanismo de fallback de HU22: reintentos con backoff, y si se agotan, estado
  `Clasificación pendiente` + notificación al operador.
- Si el parseo es válido pero la invariante no se cumple (por ejemplo `debe_escalar=true` con
  `tipo_gasto` no nulo, o `debe_escalar=false` con `motivo_escalado` no nulo) → **no confiar
  en ninguno de los dos campos**: tratar el caso como escalado por
  `causa_no_identificable`, ya que una salida inconsistente no es una clasificación confiable.
  Esto es más seguro que intentar "adivinar" cuál de los dos campos contradictorios es el
  correcto.

---

## 4. Casos de prueba requeridos antes de cerrar el prompt

Con un clasificador simulado (mock que devuelve respuestas fijas, sin consumir créditos de
la API real), verificar como mínimo:

1. **Caso normal, ordinario claro** — causa evidente, sin cláusula de excepción, confianza
   alta → `debe_escalar=false`, `tipo_gasto` correcto.
2. **Caso normal, extraordinario claro** — ídem, causa estructural/desgaste no atribuible al
   inquilino.
3. **Riesgo de seguridad** — descripción con olor a gas o riesgo eléctrico grave →
   `debe_escalar=true`, `motivo_escalado="riesgo_seguridad"`, incluso si el rubro es
   identificable.
4. **Múltiples rubros** — descripción que mezcla plomería y electricidad en el mismo relato,
   sin riesgo de seguridad → `motivo_escalado="multiples_rubros"`.
5. **Confianza insuficiente** — caso ambiguo donde el modelo declara confianza por debajo
   del umbral configurado → `debe_escalar=true`,
   `motivo_escalado="confianza_insuficiente"`.
6. **Respuesta malformada** — el mock devuelve texto que no es JSON válido → el nodo debe
   activar el fallback de HU22, no intentar "reparar" el JSON.
7. **Invariante inconsistente** — el mock devuelve `debe_escalar=true` con `tipo_gasto` no
   nulo (simulando un fallo del modelo) → el nodo debe tratarlo como escalado por
   `causa_no_identificable`, según la regla de la sección 3, y no propagar el `tipo_gasto`
   recibido.
8. **Múltiples motivos simultáneos** — descripción que mezcla dos rubros y además menciona
   riesgo de seguridad → verificar que se reporta `"riesgo_seguridad"` (prioridad más alta),
   no `"multiples_rubros"`.

Estos casos se suman a la medición de precisión sobre el conjunto de 50 reclamos sintéticos
(criterio de aceptación de HU9: ≥85%), que mide el comportamiento agregado, no estos
casos puntuales de robustez del contrato.

---

## 5. Pendientes para cerrar v2

- [ ] Confirmar con Talía los nombres exactos de `ClassificationState` tal como están en
      `main` (este documento asume `tipo_gasto`, `confianza`, `fundamento`, `debe_escalar`,
      `motivo_escalado` según el review; si hay alguna diferencia de tipeo o casing, ajustar).
- [ ] Definir la tarea de extensión de estado para `rubro_declarado` y `clausulas_contrato`
      (sección 1.2) y estimarla — probablemente entra dentro de la HH ya asignada a HU9 en
      la Tabla 16, pero conviene dejarlo explícito para no subestimar el esfuerzo restante.
- [ ] El umbral de confianza sigue sin definirse a propósito — se calibra con los resultados
      reales sobre el conjunto de 50 casos, no antes.
- [ ] Correr los 8 casos de la sección 4 con el mock antes de la primera medición de
      precisión real.
