# HU30 - Corpus de generalización para el prompt v2

**Preparado:** 24/09/2026. **Estado:** evaluación ejecutada y revisada. Se
realizaron cuatro llamadas autorizadas, una por V01-V04, sin reintentos ni
cambios del prompt. Ver [resultados consolidados](evaluacion_corpus_v2.md).

## Objetivo

Comprobar que la extracción no funciona solamente con el contrato usado para
ajustar las versiones v1 y v2. El ejemplo 01 sigue siendo una regresión conocida
y no cuenta como evidencia de generalización. Esta evaluación agrega cuatro
modelos públicos de estructura diferente y reserva dos documentos independientes
para una prueba final custodiada por Tobías/Oikos.

No se entrena ningún modelo. El riesgo que se controla es ajustar el prompt o la
interpretación de los resultados a documentos ya conocidos. Por eso el prompt
v2 y su adaptador quedaron congelados por SHA-256 en
`corpus_v2_manifest.json`. Si alguno cambia, el ejecutor se detiene.

## Separación del corpus

| Grupo | Documentos | Uso |
|---|---|---|
| Regresión conocida | Ejemplo 01 anonimizado | Detectar que un cambio futuro no pierda comportamientos ya logrados. No mide generalización. |
| Validación | V01, V02, V03 y V04 | Medir v2 sin modificarlo a partir de los errores de estos documentos. |
| Holdout final | H01 y H02 | Los eligen y conservan Tobías/Oikos fuera del repositorio hasta la evaluación final. |

Los documentos de validación son modelos públicos, sin una contraparte privada
completada. Algunos conservan autoridades, firmas, domicilios o sellos
institucionales públicos. Eso no autoriza su transmisión automática: cada
llamada externa requiere aprobación explícita y debe registrarse por separado.

## Documentos de validación

| ID | Variante | Lectura que ejercita | Particularidad |
|---|---|---|---|
| V01 | Modelo de vivienda dentro de un proyecto público | Texto digital | El PDF incluye contenido legislativo antes y después del modelo; permite comprobar que no se convierta texto ajeno en cláusulas operativas. |
| V02 | Modelo oficial de Mendoza, páginas contractuales 4-6 de la fuente | OCR local | Incluye procedimiento para reparaciones urgentes y responsabilidades estructurales/no estructurales. |
| V03 | Modelo institucional de UNIPE | Texto digital | Usa referencias cruzadas y una excepción para adecuaciones funcionales no estructurales. |
| V04 | Modelo oficial de DGN, páginas contractuales 8-9 de la fuente | Capa digital sobre documento escaneado | Una obligación de reparación comienza al final de la primera página y continúa en la segunda. |

Fuentes públicas:

- [V01 - CELS](https://www.cels.org.ar/web/wp-content/uploads/2017/06/PROYECTODELEY-MAYO17.pdf)
- [V02 - Gobierno de Mendoza](https://www.mendoza.gov.ar/wp-content/uploads/sites/63/2024/06/DI-2024-04245942-GDEMZA-DISPOSICION-APROBACION-MODELO-DE-CONTRATO-DE-LOCACION-DE-BIENES-INMUEBLES.pdf)
- [V03 - UNIPE](https://portalcompras.unipe.edu.ar/diaguita/temp/346_MODELO_DE_CONTRATO_DE_LOCACIONBIBLIOTECA.pdf)
- [V04 - Ministerio Público de la Defensa](https://oaip.mpd.gov.ar/pdf/res%20DGN%200564_2007.PDF)

El manifiesto registra ruta, páginas, procedencia y hash de cada copia. V02 y
V04 fueron recortados a las páginas del anexo contractual para no incorporar la
resolución administrativa completa. Las cuatro copias se renderizaron y
revisaron visualmente; no se detectaron cortes, páginas vacías ni superposiciones.
La lectura local también fue completa: V01 recuperó 33.048 caracteres digitales;
V02, 11.750 mediante OCR; V03, 6.451 digitales; y V04, 4.709 desde su capa de
texto. Esta comprobación mantuvo `external_calls: 0`.

## Resultados esperados antes de ejecutar

`controles_corpus_v2.json` contiene 23 controles semánticos validados contra los
documentos fuente:

- V01: 8 controles, 5 críticos.
- V02: 5 controles, 4 críticos.
- V03: 5 controles, 3 críticos.
- V04: 5 controles, 3 críticos.

Los controles describen fidelidad al documento: sujetos, condiciones,
excepciones, plazos, referencias y continuidad entre páginas. No son una
validación jurídica ni reglas universales de Oikos. Fueron definidos y revisados
antes de observar las nuevas respuestas. Definirlos después de ver la salida del
modelo invalidaría la medición.

## Criterios de aceptación

Se informan resultados por documento y en total:

1. **Cobertura general:** controles completos / total de controles. Mínimo 85%.
2. **Recall crítico:** controles críticos completos / total de críticos. Debe ser 100%.
3. **Alucinaciones aceptadas:** afirmaciones inventadas que superaron la validación y se tomaron como válidas. Debe ser 0.

`parcial`, `omitido` e `incorrecto` permanecen en el denominador. Una respuesta
inválida, un error o una cita rechazada no pueden mejorar artificialmente el
porcentaje. La tasa de evidencia literal aceptada se registra aparte y no se
confunde con precisión semántica.

Si v2 no alcanza estos criterios, el resultado se documenta como tal. No se
edita v2 ni se vuelve a ejecutar el mismo documento para mejorar el número. Las
mejoras formarían una versión nueva y se validarían con documentos nuevos.

## Ejecutor controlado

El script `backend/scripts/evaluate_contract_clause_corpus.py` realiza primero
un preflight local: verifica hashes, versión congelada, documento y controles.
Sin `--run` no llama a Gemini. Con `--run` exige controles validados, realiza una
sola llamada, conserva propuestas aceptadas y rechazadas y crea una planilla JSON
para revisión humana. Nunca sobrescribe evidencia de una corrida anterior.

Ejemplo de preflight, sin consumo externo:

```powershell
cd backend
python scripts/evaluate_contract_clause_corpus.py --document V01
```

Para probar texto digital/OCR sin Gemini, agregar `--check-extraction`. El
resultado informa páginas, métodos y cantidad de caracteres, manteniendo
`external_calls: 0`.

La futura ejecución con `--run` sólo se hará después de la autorización explícita
para ese documento. H01 y H02 están bloqueados por diseño y no pueden ejecutarse
desde este corpus mientras continúen reservados.

Después de completar la revisión humana generada por la corrida, `--score-review
RUTA_JSON` calcula las tres métricas. Rechaza estados pendientes, controles
faltantes o repetidos y mantiene omisiones en el denominador.

## Próximo paso

La revisión concluyó que v2 localizó 22/23 contenidos, pero sólo 13/23 quedaron
completos con evidencia aceptable. Antes de usar H01-H02 corresponde acordar una
propuesta v3 para mejorar el anclaje literal y el tratamiento de ambigüedades.
Los holdouts se mantienen reservados para medir esa futura versión; sus errores
no se utilizarán para reescribirla.

## Validaciones de esta preparación

- Preflight y extracción local completa de V01-V04: aprobados.
- Cuatro llamadas externas autorizadas: completadas, una por documento y sin reintentos.
- Pruebas específicas de cláusulas y corpus: **14 aprobadas, 1 OCR opcional omitida**.
- Suite completa del backend: **313 aprobadas, 23 omitidas**.
- Frontend: **24 archivos y 105 pruebas aprobadas**; ESLint y build aprobados.
- JSON, hashes, `git diff --check` y búsqueda de patrones de secretos: aprobados.
- El intento de `--run` con expectativas en borrador fue bloqueado antes de cargar el modelo.
