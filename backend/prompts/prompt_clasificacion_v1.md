# AARI — Prompt de Clasificación v1 (HU9)

**Frente:** Base de conocimiento y prompt (dominio)
**Depende de:** `base_conocimiento.json`
**Consumido por:** nodo de clasificación en LangGraph (a cargo de Talía)

---

## 1. Contrato de interfaz (para que se integre sin fricción con el grafo)

Esto es lo que tu compañera necesita saber para llamar a este prompt desde el nodo sin
tener que leer todo el documento:

**Input esperado por el prompt:**
```json
{
  "descripcion": "texto libre del reclamo tal como lo escribió el inquilino",
  "rubro_declarado": "plomeria | electricidad | gas | pintura | estructural | electrodomesticos | otro",
  "clausulas_contrato": [
    { "rubro": "plomeria", "override": "ordinario", "detalle": "termotanque a cargo del inquilino según cláusula 8" }
  ]
}
```
`clausulas_contrato` puede venir vacío (`[]`) si la propiedad no tiene excepciones cargadas
— en ese caso el prompt aplica solo la regla general.

**Output que el prompt debe devolver (JSON estricto, sin texto fuera del JSON):**
```json
{
  "clasificacion": "ordinario | extraordinario | expensa | null",
  "confianza": 0.0,
  "justificacion": "una o dos frases, no más",
  "escalar": true,
  "motivo_escalado": "causa_no_identificable | riesgo_seguridad | multiples_rubros | confianza_insuficiente | null"
}
```
Regla dura: si `escalar` es `true`, `clasificacion` **debe** ser `null`. El nodo de LangGraph no
debería tener que validar esto — el prompt lo garantiza. Avisale a Talía que puede confiar en
esa invariante para el branching del grafo (si `escalar=true` → nodo de cola de operador; si no
→ nodo de notificación al responsable).

---

## 2. Prompt de sistema (v1)

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

2. Si el reclamo tiene una cláusula contractual específica que aplica a su rubro
   (ver "clausulas_contrato" en el input), esa cláusula tiene prioridad sobre la regla
   general de la base de conocimiento.

3. Tenés que declarar tu propio nivel de confianza (0 a 1) sobre la clasificación. No
   redondees hacia arriba para "resolver" un caso dudoso. Subestimar tu confianza es
   preferible a sobrestimarla: el costo de escalar un caso claro es bajo (un operador lo
   confirma en segundos), pero el costo de clasificar mal un caso ambiguo es alto
   (consecuencias económicas y legales para inquilinos y propietarios reales).

4. Tenés que escalar (escalar=true, clasificacion=null) sin excepción en estos casos,
   incluso si "intuís" cuál sería la respuesta:
   - No podés identificar con razonable certeza la causa del problema a partir del relato.
   - El reclamo describe un riesgo de seguridad (olor a gas, riesgo eléctrico grave, riesgo
     de derrumbe o estructural inminente).
   - El relato mezcla más de un rubro o problema distinto en la misma descripción.
   - La propiedad no tiene cláusulas contractuales cargadas y la base de conocimiento no
     cubre el caso de forma directa e inequívoca.
   - Tu confianza en la clasificación es menor al umbral configurado para el sistema.

5. Nunca inventes una cláusula de contrato, un artículo de ley, ni un dato que no esté en
   el input. Si necesitás un dato que no tenés para decidir, eso en sí mismo es motivo de
   escalado por "causa_no_identificable".

6. Tu respuesta debe ser exclusivamente un objeto JSON válido, sin texto antes ni después,
   sin marcado de código, con esta forma exacta:

{
  "clasificacion": "ordinario" | "extraordinario" | "expensa" | null,
  "confianza": <número entre 0 y 1>,
  "justificacion": "<una o dos frases, en español, sin tecnicismos legales>",
  "escalar": true | false,
  "motivo_escalado": "causa_no_identificable" | "riesgo_seguridad" | "multiples_rubros" | "confianza_insuficiente" | null
}

Base de conocimiento del dominio (reglas por rubro):
{{BASE_CONOCIMIENTO_JSON}}

Reclamo a clasificar:
Descripción: {{descripcion}}
Rubro declarado por el inquilino: {{rubro_declarado}}
Cláusulas contractuales de la propiedad: {{clausulas_contrato}}
```

> `{{BASE_CONOCIMIENTO_JSON}}` se inyecta desde `base_conocimiento.json` en tiempo de
> ejecución — nunca se pega el contenido a mano en el prompt, así se cumple RS-09 (config
> independiente del código/prompt). Esto también es lo que le tenés que pasar a Talía: el
> nodo de LangGraph arma el prompt final concatenando esta plantilla con el JSON leído del
> archivo de configuración.

---

## 3. Notas para la calibración (antes de dar el prompt por "v1 cerrado")

- El umbral de confianza para decidir el corte automático de `escalar` (por ejemplo, ¿confianza
  < 0.7 escala?) **no está definido todavía a propósito** — se calibra con los resultados reales
  sobre el conjunto de 50 casos, no antes. Ponerlo a ciegas ahora sería inventar un número.
- Cuando tengan el primer resultado de precisión sobre el conjunto de prueba, lo más probable
  es que haya que iterar el prompt 1–2 veces (así lo estimaron en la Tabla 16: 8 HH de iteración).
  Guardá cada versión del prompt (v1, v2...) en el repo para poder comparar precisión entre
  versiones — no sobrescribas el archivo.
- Si el modelo no devuelve JSON válido (respuesta malformada), eso lo maneja el nodo de
  LangGraph con el fallback de HU22 — no es responsabilidad del prompt "forzar" el formato
  más allá de la instrucción explícita.

---

## 4. Próximo paso

Con esto cerrado, el siguiente ítem de tu frente es el **conjunto de prueba de 50 reclamos
sintéticos** — decime si seguimos directo con eso o si primero querés ajustar algo del prompt
o de la base de conocimiento.
