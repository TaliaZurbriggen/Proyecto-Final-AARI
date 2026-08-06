# AARI — Prompt de Clasificación v3 (AARI-112)

**Depende de:** `base_conocimiento.json`
**Consumido por:** `backend/app/agents/classification/llm.py` (`build_classification_prompt`),
nodo `clasificar_reclamo` del grafo (`nodes.py`)
**Reemplaza a:** `prompt_clasificacion_v2.md` — línea base medida en AARI-111: 35/61 (57,38%)
sobre `conjunto_prueba_61_casos.json`. v2 se conserva como evidencia, no se sobrescribe.

---

## 0. Qué cambió respecto a v2 y por qué

La medición de AARI-111 mostró que el problema no era la cobertura de expensas (8/9), sino
sobreescalado generalizado: **18 casos sobreescalados**, **1 escalamiento omitido** y
**7 casos con motivo de escalado incorrecto** (de estos 7, **5 correspondían a respuestas
inválidas del proveedor** — un problema de disponibilidad/salida del LLM ajeno a la redacción
del prompt, ver sección 4.3 — y solo 2 eran errores genuinos de motivo). En total, 21 casos
son atribuibles a la calidad de decisión del prompt v2; 5 son un problema de infraestructura
aparte.

La causa de fondo en v2 era la combinación de "subestimar confianza es preferible" +
"escalar sin excepción si no podés identificar la causa con razonable certeza": el agente
escalaba reclamos que ya encajaban con claridad en una regla de la base de conocimiento,
solo por no conocer el diagnóstico técnico exacto (ej. una canilla que gotea, una cerradura
gastada).

v3 corrige esto sin tocar las protecciones de seguridad, y agrega algo que faltaba en el
borrador inicial: **leer explícitamente los campos especiales de cada regla de la base de
conocimiento**, en vez de depender de ejemplos de texto libre. Esto es necesario porque
`base_conocimiento.json` ya define, por regla, condiciones que fuerzan el escalado o
limitan cuándo una regla aplica:

- `"accion": "escalar_urgente"` (ej. `gas-01`) → nunca clasificar, escalar siempre por
  `riesgo_seguridad`, sin excepción contractual posible.
- `"escalar_si_falta_contexto": true` (ej. `plomeria-05`) → el default de la regla NO se
  aplica si el relato no aporta el dato que distingue la causa; hay que escalar.
- `"requiere_causa_explicita": true` (ej. `plomeria-04`, `pintura-02`) → la regla solo aplica
  si el relato menciona explícitamente la causa atribuible al inquilino; si no la menciona,
  no se puede asumir.
- `"admite_override_contractual": false` (ej. `expensas-02`) → ninguna cláusula contractual
  puede sobrescribir esta regla, aunque exista y sea válida para el rubro.
- `"requiere_clausula_contractual": true` (ej. `expensas-01`) → la regla solo puede usar
  una excepción contractual si la cláusula está cargada, es válida y aplica al rubro. Una
  cláusula solamente mencionada en el relato no está verificada y debe escalarse.

Si el prompt no lee estos campos, el modelo puede clasificar casos que la propia base de
conocimiento marca como "no clasificar automáticamente" — que es exactamente el tipo de
error que v3 busca eliminar sin reintroducir sobreescalado.

Cambios de contrato respecto a v2:

1. Los campos `rubro_declarado` y `clausulas_contrato` ya no son "pendientes de extensión
   de estado": `ClassificationState` (`state.py`) y `build_classification_prompt`
   (`llm.py`) ya los soportan e inyectan. Se elimina esa sección de v2 como resuelta.
2. La sección de validación por código se corrige para reflejar el comportamiento real:
   `schemas.py` valida la invariante `debe_escalar ⇄ tipo_gasto/motivo_escalado` con un
   `model_validator` de Pydantic que **lanza excepción** ante una salida contradictoria;
   `nodes.py` captura esa excepción (junto con cualquier otro fallo del proveedor) y
   asigna `motivo_escalado="respuesta_modelo_invalida"` — no `"causa_no_identificable"`
   como decía v2. `"respuesta_modelo_invalida"` es un motivo que solo asigna el código
   ante fallos de parseo/validación; el modelo nunca debe intentar producirlo.
3. Se reemplaza la lista plana de motivos de escalado por un **orden de decisión
   obligatorio de cuatro pasos** (sección 2), evaluado secuencialmente, que lee los
   campos especiales de la KB en cada paso.
4. La guía de confianza deja de incentivar subestimarla por defecto; mide encaje con una
   regla o cláusula, no conocimiento de la causa técnica exacta.

---

## 1. Contrato de interfaz

### 1.1 Campos soportados por `ClassificationState` (`state.py`)

**Input** (ya inyectado por `build_classification_prompt` en `llm.py`):
```json
{
  "descripcion": "texto libre del reclamo",
  "urgencia": "baja | media | alta",
  "rubro_declarado": "plomeria | electricidad | ... | null si no disponible",
  "clausulas_contrato": [ { "...": "estructura definida en excepciones_contractuales de la KB" } ]
}
```

**Output que el modelo debe producir** (`ModelClassification` en `schemas.py`):
```json
{
  "tipo_gasto": "ordinario",
  "confianza": 0.91,
  "fundamento": "El termotanque falló por desgaste normal, sin cláusula de excepción cargada; corresponde al inquilino según la regla general de plomería.",
  "debe_escalar": false,
  "motivo_escalado": null
}
```

El `MotivoEscalado` de `state.py` tiene 5 valores posibles: `riesgo_seguridad`,
`multiples_rubros`, `causa_no_identificable`, `confianza_insuficiente` y
`respuesta_modelo_invalida`. **El modelo solo debe producir los primeros 4** — el quinto lo
asigna exclusivamente el código cuando el parseo o la validación de Pydantic fallan (ver
sección 3). El prompt de abajo no le pide al modelo ese valor.

### 1.2 Umbral de confianza

`{{umbral_confianza}}` se inyecta desde `umbral_confianza_escalado.valor` en la base de
conocimiento (0.75 actualmente). Sin cambios en v3.

---

## 2. Prompt de sistema (v3)

```
Sos el agente de clasificación de reclamos de mantenimiento de AARI, un sistema usado por
una inmobiliaria administradora de propiedades en alquiler en Argentina.

Tu única tarea es clasificar un reclamo de mantenimiento en una de estas tres categorías:
- "ordinario": gasto a cargo del inquilino
- "extraordinario": gasto a cargo del propietario
- "expensa": gasto administrado por el consorcio del edificio

Vas a recibir una base de conocimiento en JSON con reglas por rubro. Cada regla puede traer
campos especiales que modifican cómo se aplica. Antes de decidir, revisá si la regla que
mejor encaja con el reclamo tiene alguno de estos campos:

- "accion": "escalar_urgente" → esta regla NUNCA se clasifica de forma automática, sin
  importar cláusulas contractuales ni ningún otro dato. Escalá siempre con
  motivo_escalado="riesgo_seguridad".
- "escalar_si_falta_contexto": true → el valor de "clasificacion_default" de esta regla
  NO se aplica si el relato no incluye el dato que permite determinar la causa real
  (por ejemplo, si el problema es atribuible a una falla propia del artefacto o a otra
  causa). Sin ese dato, escalá por "causa_no_identificable" en vez de usar el default.
- "requiere_causa_explicita": true → esta regla solo aplica si el relato menciona de
  forma explícita la causa atribuible al inquilino (por ejemplo, un hecho concreto que
  la persona relata haber hecho o presenciado). Si el relato no la menciona explícitamente,
  no asumas esa causa: evaluá si otra regla del mismo rubro aplica sin ese requisito, o
  escalá si ninguna aplica.
- "admite_override_contractual": false → ninguna cláusula contractual puede modificar la
  clasificación de esta regla, aunque exista una cláusula cargada y válida para ese rubro.
  Si una cláusula pretende contradecir una norma imperativa, no apliques ni el override ni
  el default de forma automática: escalá por "confianza_insuficiente" para validación humana.
- "requiere_clausula_contractual": true → solo usá la regla junto con una cláusula
  cargada, válida y claramente aplicable al rubro. Si falta esa cláusula, buscá otra regla
  directa aplicable; si no existe, escalá por "causa_no_identificable".

Para decidir, seguí este orden obligatorio. Evaluá cada paso en secuencia y aplicá el
primero que corresponda — no sigas evaluando pasos posteriores una vez que uno aplica.

PASO 1 — Seguridad y complejidad (prioridad máxima):
Escalá (debe_escalar=true, motivo_escalado="riesgo_seguridad") si el relato describe olor a
gas, riesgo eléctrico grave, riesgo de derrumbe o estructural inminente, o cualquier
situación de peligro inmediato para las personas — o si la regla de la base de conocimiento
que mejor encaja tiene "accion": "escalar_urgente".
Escalá (motivo_escalado="multiples_rubros") si el relato mezcla más de un rubro o problema
distinto en la misma descripción, y no hay riesgo de seguridad.

PASO 2 — Cláusula contractual:
Si recibís cláusulas contractuales para la propiedad, alguna es válida y aplica de forma
clara al rubro del reclamo, Y la regla de la base de conocimiento correspondiente a ese
rubro NO tiene "admite_override_contractual": false, esa cláusula tiene prioridad sobre la
regla general; clasificá según ella.
Si la cláusula es dudosa, ambigua o no aplica claramente al rubro, ignorala y seguí al paso 3
aplicando la regla general. Si la cláusula pretende contradecir una regla con
"admite_override_contractual": false, escalá por "confianza_insuficiente" en vez de aplicar
cualquiera de las dos de forma automática.
Si el relato afirma que existe una cláusula, pero no recibís una cláusula cargada y
verificable para la propiedad, tratala como dudosa y escalá por "confianza_insuficiente".
Si no recibís cláusulas contractuales (campo vacío o ausente) y el relato tampoco menciona
una excepción contractual, pasá al paso 3 aplicando solo la regla general.

PASO 3 — Regla directa de la base de conocimiento:
Si la descripción encaja de forma clara con una regla que tiene "clasificacion_default", y
esa regla no tiene "escalar_si_falta_contexto": true sin el dato requerido, ni
"requiere_causa_explicita": true sin que el relato la mencione explícitamente, clasificá
según esa regla.
Conocer el síntoma relatado alcanza para aplicar una regla directa. NO hace falta conocer
la causa técnica exacta ni el diagnóstico preciso del problema para clasificar en este paso,
salvo que la regla misma lo exija mediante los campos especiales de arriba.

PASO 4 — Escalado por ambigüedad real:
Escalá solo si, después de los pasos 1 a 3, ninguna regla de la base de conocimiento cubre
el caso de forma directa e inequívoca, hay información contradictoria en el relato, o falta
un dato indispensable para distinguir entre dos reglas posibles (motivo_escalado
correspondiente: "causa_no_identificable" si falta un dato clave o si una regla con
"escalar_si_falta_contexto"/"requiere_causa_explicita" no puede aplicarse sin ese dato,
"confianza_insuficiente" si el dato está pero el encaje con la regla es débil).

Confianza:

- La confianza (0 a 1) mide qué tan bien encaja el relato con una regla de la base de
  conocimiento o con una cláusula contractual — no si conocés la reparación técnica exacta
  ni la causa interna del problema.
- Si el paso 2 o el paso 3 aplican con claridad y no hay contradicción en el relato, no
  reduzcas la confianza únicamente porque se desconoce la causa técnica interna del
  problema.
- Reservá "confianza_insuficiente" para cuando el relato es compatible con más de una regla
  a la vez sin un dato que permita distinguir cuál aplica, o cuando el encaje con la única
  regla candidata es débil o forzado.
- Tu confianza declarada debe ser honesta: ni la subestimes por defecto ni la sobrestimes
  para "resolver" un caso dudoso. Confianza baja debe ocurrir solo ante ambigüedad real, no
  como respuesta por defecto ante la falta de un diagnóstico técnico.

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
  cerradura gastada por uso, o una térmica que salta por sobrecarga de consumo: ordinario
  (paso 3, regla directa — no requiere diagnóstico técnico exacto).
- Pintura deteriorada por antigüedad, o un termotanque u otro artefacto provisto por el
  propietario que falla por desgaste sin que el relato aclare la causa: revisá si la regla
  tiene "escalar_si_falta_contexto" antes de asumir el default — puede corresponder escalar
  en vez de clasificar directo como extraordinario.
- Un daño puntual (mancha, rotura localizada) que el relato atribuye explícitamente a un
  hecho del inquilino o su familia: ordinario, solo si la causa está mencionada de forma
  explícita (paso 3, regla con "requiere_causa_explicita").
- Ascensor, bomba de agua, portón automático o iluminación de espacios comunes del
  edificio: expensa (paso 3, regla directa).
- Un gasto no habitual de consorcio (obra estructural, fondo de reserva extraordinario) con
  una cláusula contractual que dice lo contrario: la cláusula no aplica
  ("admite_override_contractual": false); clasificá igual como expensa.
- Olor a gas, dos problemas de rubros distintos relatados juntos, o una cláusula
  contractual dudosa que contradice una norma imperativa: escalar (pasos 1 o 2).

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
null siempre que debe_escalar sea true. No uses ningún otro valor de motivo_escalado más
allá de los cuatro listados arriba.

Base de conocimiento del dominio (reglas por rubro):
{{BASE_CONOCIMIENTO_JSON}}

Reclamo a clasificar:
Descripción: {{descripcion}}
Urgencia declarada: {{urgencia}}
Rubro declarado por el inquilino: {{rubro_declarado}}
Cláusulas contractuales de la propiedad: {{clausulas_contrato}}
```

> `{{BASE_CONOCIMIENTO_JSON}}`, `{{descripcion}}`, `{{urgencia}}`, `{{rubro_declarado}}`,
> `{{clausulas_contrato}}` y `{{umbral_confianza}}` se inyectan en `llm.py`, sin cambios de
> nombres respecto a v2.

---

## 3. Validación: responsabilidad del código, no del prompt

Comportamiento real (`schemas.py` + `nodes.py`), no el descripto en v2:

- `ModelClassification` valida con Pydantic la invariante `debe_escalar ⇄ tipo_gasto /
  motivo_escalado`. Si la salida es contradictoria, el `model_validator` lanza `ValueError`.
- `classify_claim` (en `nodes.py`) envuelve la invocación al modelo, el parseo y esta
  validación en un único `try/except Exception`. Cualquier falla en esa cadena — JSON
  inválido, invariante contradictoria, error del proveedor — cae en
  `_invalid_model_response()`, que fija `motivo_escalado="respuesta_modelo_invalida"` y
  `estado_clasificacion="escalado"`, sin exponer detalles internos del error.
- Esto es distinto y más simple de lo que describía v2 (que proponía tratar la invariante
  inconsistente como `"causa_no_identificable"`): en el código real, cualquier fallo de
  contrato se trata igual que un fallo del proveedor, con su propio motivo dedicado. El
  prompt no necesita "saber" esto — es responsabilidad exclusiva del código — pero esta
  sección documenta el comportamiento real para que quien lea el prompt no asuma el
  comportamiento viejo de v2.
- El umbral de confianza se aplica aparte, en `_apply_confidence_threshold`: si
  `debe_escalar=false` pero `confianza < umbral`, el código fuerza el escalado con
  `motivo_escalado="confianza_insuficiente"`, independientemente de lo que haya declarado
  el modelo. El prompt le pide al modelo que declare una confianza honesta, pero la
  decisión final de escalar por umbral la toma el código, no el modelo.

---

## 4. Medición

### 4.1 Conjunto de prueba

`backend/tests/data/conjunto_prueba_61_casos.json` — 61 casos (18 ordinario, 17
extraordinario, 9 expensa, 17 escalar), con `prioridad_motivos_escalado.orden` ya definido
en el propio archivo (coincide con el orden de la sección 2 del prompt) y con
`cobertura_clausulas_contractuales` describiendo los 8 casos con cláusula cargada (51-58).
Nota del propio archivo: el estado es `"borrador - validación parcial con Oikos"`, con un
punto pendiente de confirmar (atención inmediata o no ante olor a gas / riesgo eléctrico) —
esto no bloquea medir v3, pero si se confirma un criterio distinto, puede requerir un ajuste
posterior del paso 1 y una remedición.

### 4.2 Corrección de referencias de AARI-111

La propuesta original de AARI-112 hablaba de "26 errores" para convertir en regresión. La
cifra correcta, según la medición de línea base, es:

- 18 casos sobreescalados (debían clasificar y escalaron).
- 1 caso con escalamiento omitido (debía escalar y clasificó).
- 7 casos con motivo de escalado incorrecto, de los cuales:
  - 5 fueron en realidad `motivo_escalado="respuesta_modelo_invalida"` — el proveedor no
    devolvió una salida parseable/válida. Esto no es un error del prompt v2; es un problema
    de disponibilidad o formato de salida de Gemini. Se registran aparte (sección 4.3) y no
    entran como casos de regresión de v3.
  - 2 fueron errores genuinos de motivo con salida válida del modelo (el modelo clasificó
    el motivo equivocado entre los 4 posibles).

Total de casos de regresión atribuibles a la calidad de decisión del prompt: **21**
(18 + 1 + 2), no 26.

### 4.3 Respuestas inválidas del proveedor — fuera de alcance de v3

Los 5 casos de `respuesta_modelo_invalida` se registran en
`docs/evaluaciones/aari112/respuestas_invalidas_v3.json` como seguimiento aparte. Si se
repiten con v3 en la misma proporción, es indicio de un problema de formato de salida o
disponibilidad del proveedor (Gemini), a investigar independientemente del contenido del
prompt — por ejemplo, revisando el uso de `with_structured_output(method="json_schema")`
en `llm.py` o el modelo configurado (`DEFAULT_GEMINI_MODEL`). No se resuelven modificando
el texto del prompt.

### 4.4 Ejecución

La medición real contra Gemini requiere `GEMINI_API_KEY` configurada en `backend/.env` y
se corre desde el entorno del proyecto (no desde este documento). Ver
`backend/tests/data/measure_precision_v3.py` — genera:
- `docs/evaluaciones/aari112/resultados_v3.json`: precisión global y por categoría
  (ordinario / extraordinario / expensa / escalar), sin sobrescribir los resultados de
  AARI-111.
- `docs/evaluaciones/aari112/casos_regresion_v3.json`: generado automáticamente a partir de
  los casos donde `categoria_esperada`/`escalar_esperado` no coincide con la salida real —
  no se hardcodean IDs de casos a mano, para que el archivo refleje la medición real y no
  una lista fabricada de antemano.

Correr en lotes de 20 casos y solo con autorización explícita antes de cada tanda, dado el
consumo de créditos de API.

---

## 5. Pendientes para cerrar v3

- [ ] Confirmar que `resources.py` carga `prompt_clasificacion_v3.md` (ver AARI-112,
      bloqueo de loader — corregido en este mismo PR, sección aparte).
- [ ] Correr `test_classification_resources.py` (loader + inyección de placeholders).
- [ ] Correr `measure_precision_v3.py` con autorización, en lotes de 20, sobre los 61 casos.
- [ ] Comparar precisión global y por categoría contra la línea base (35/61, 57,38%).
- [ ] Confirmar con Oikos el punto pendiente de `validacion_oikos.pendiente` en el conjunto
      de prueba (atención inmediata ante gas/riesgo eléctrico), y evaluar si requiere ajustar
      el paso 1 y remedir.
- [ ] Si v3 mejora pero no alcanza el 85% (criterio de aceptación de HU9), evaluar el umbral
      de confianza como decisión separada y documentada — no como parte de este cambio.
- [ ] Cerrar AARI-112 solo con la evidencia de `resultados_v3.json` y la conclusión sobre el
      objetivo de 85%, no antes.
