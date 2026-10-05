# HU30 / AARI-319 — flujo asistido y respaldo literal

Fecha: 05/10/2026. Rama: `feat/AARI-319-extraccion-clausulas`.
Estado: implementación validada y entrega para revisión; Talía autorizó el
commit/push y registrar dos horas adicionales el 05/10. Pendiente de crear el
PR, revisión de Tobías y merge. No se cerró la HU ni se modificaron sus estimaciones.

## Decisión y alcance aprobado

Después de los errores externos y las interpretaciones incompletas, Talía aprobó
finalizar el flujo como **extracción asistida con revisión humana obligatoria**.
También autorizó aplicar la migración aditiva 25 y probarla aisladamente con
rollback. La finalidad es avanzar con una funcionalidad utilizable sin hacer
depender cada revisión de que Gemini responda correctamente.

Alternativas consideradas:

- Seguir encadenando modelos/prompts: los resultados observados no garantizan
  precisión y repetir solicitudes consume cuota sin asegurar un diagnóstico.
- Cargar todo manualmente: viable como contingencia, pero no conserva el beneficio
  de recuperar y organizar el texto de origen automáticamente.
- Flujo asistido con respaldo literal: elegido; conserva procedencia y auditoría,
  permite proponer interpretaciones y exige revisión antes del uso operativo.

No se afirma haber cumplido los umbrales automáticos de 85% general, 100% de
controles críticos y cero propuestas no respaldadas. Se mantienen intactos los
controles, manifiestos y resultados históricos. El cierre funcional del alcance
asistido debe distinguirse de la validación pendiente del modelo autónomo.

## Qué se implementó

1. Lectura local del PDF digital/OCR por página; segmentación que conserva
   continuaciones, preámbulos y bloques sin encabezado reconocible. Los tramos
   grandes se dividen explícitamente sin truncar palabras.
2. Ruta `v10-asistida` con Gemini 3.5 Flash-Lite y SDK oficial, MIME JSON sin
   esquema nativo impuesto al proveedor. La salida se valida localmente con
   esquema estricto y sólo puede referenciar tramos existentes. Una llamada
   realiza como máximo una petición HTTP, sin herramientas ni retries del SDK.
3. Propuestas de IA acompañadas por evidencia local íntegra. Los bloques sin
   interpretación quedan literales, con responsable no especificado y confianza
   cero. La confianza del modelo nunca habilita una regla por sí sola.
4. Acción explícita **Extraer sin IA**: cero llamadas externas; sólo organiza el
   texto para revisión. Si hay páginas sin lectura confiable se informa análisis
   incompleto, no se une contenido a través de esos huecos y no se presenta como
   lectura íntegra. Gemini no recibe una lectura parcial.
5. Preservación de cláusulas revisadas, eventos y propuestas originales. El
   historial de intentos guarda estados/resultados y usa un UUID de ejecución
   para rechazar actualizaciones tardías. Los fallos externos terminan el intento;
   el usuario decide solicitar otro. La recuperación por caída de un worker
   permanece acotada y auditada, no equivale a reintentos ocultos del proveedor.
6. Todas las filas nuevas se guardan como `contexto`, incluso si el modelo sugiere
   `operativa`. Confirmar no activa. Sólo editar y elegir expresamente uso operativo
   produce el evento necesario para que una cláusula aporte al clasificador.
   Una extracción literal pendiente necesita completar su interpretación primero.
7. Editor y mensajes alineados con la skill visual de AARI: componentes/tokens
   compartidos, etiquetas visibles, validación de resumen y teclado. Historial y
   propuestas rechazadas accesibles sin permitir su activación.

Componentes principales: `contract_clause_assisted.py`,
`contract_clause_service.py`, repositorio `clausulas_contrato.py`, esquema nuevo
`analisis_asistido.py`, API de contratos y `ContractClausesPanel`.
Los helpers congelados de segmentación/materialización se reutilizan sin cambiar
sus hashes. Se preservó el esquema congelado de evaluaciones anteriores y se
extendió el API por separado.

## Supabase y privacidad

La migración **25** quedó aplicada el 05/10/2026 sobre las 23/24 ya existentes.
Agrega modo/origen e historial privado; no elimina contratos ni cláusulas.
RLS y ausencia de lectura pública se comprobaron. La prueba de PostgreSQL usa
un esquema aislado y rollback: no dejó datos de prueba instalados.

`CONTRACT_ANALYSIS_EXTERNAL_ENABLED` sigue deshabilitado por defecto; no se
activó permanentemente en el `.env`. Se configuró localmente OCR español y el
modelo elegido, sin versionar claves ni el binario del idioma. El ensayo externo
usó sólo **V04 público**, un repositorio simulado y ningún contrato privado.
No escribió sus propuestas en la base compartida ni activó facturación.

Notion rechazó el nuevo ADR por límite de bloques gratuitos. Esta página conserva
contexto, alternativas, decisión y consecuencias para trasladarlas cuando exista
capacidad. No se borró documentación previa ni se cambió el plan.

## Resultados de las pruebas

| Comprobación | Resultado |
|---|---|
| Backend completo, APIs simuladas | `pytest -q`: 520 aprobadas, 23 omitidas, 2 advertencias de dependencias |
| Frontend completo | `npm test -- --run`: 112 aprobadas, 25 archivos |
| Estilo y compilación | `npm run lint` y `npm run build`: aprobados |
| Supabase aislado | `check_contract_clauses_postgres.py --mode test`: 1 aprobada, rollback |
| Lectura V01 | 9 páginas digitales, 34 registros literales; texto por página conservado |
| Lectura V02 | 3 páginas OCR reales en español, 16 registros; texto extraído conservado |
| Lectura V03 | 3 páginas digitales, 13 registros; texto por página conservado |
| Lectura V04 | 2 páginas digitales, 13 registros; texto por página conservado |
| Interfaz con API simulada | 320/390/768/1440 px: vacío, fallo, literal y editor; sin desbordamiento horizontal ni errores JS |
| Teclado y continuidad | Resumen → Categoría; fallo IA → literal → edición como contexto: aprobados |
| Formato del diff preparado | `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --cached --check`: sin errores; conserva los finales CRLF de la evidencia original |

Las 23 omisiones de la suite local corresponden a pruebas externas/opt-in; no
se cuentan como aprobadas. La prueba PostgreSQL autorizada se ejecutó por separado.
Las dos advertencias son deprecaciones conocidas de Starlette/httpx y del adaptador
datetime de SQLite; no son fallos de extracción.

La conservación local compara en orden el texto extraído por página **ignorando
espacios**. No demuestra OCR perfecto frente a la imagen, validez jurídica ni
que el modelo comprendió esas páginas. Un registro literal tampoco equivale a
una obligación interpretada correctamente.

## Una llamada real autorizada y su revisión

[Respuesta original](asistida_2026-10-05.json): una solicitud HTTP, **200**,
7 propuestas de IA y 7 bloques literales. Sin reintentos ni envíos privados.
Esto valida que la ruta integrada puede responder; no explica todos los 503
anteriores ni acredita disponibilidad sostenida.

La [revisión documental separada](revision_asistida_2026-10-05.json) conserva los
cinco controles congelados de V04:

| Control | Resultado | Observación |
|---|---|---|
| E01, reparaciones entre páginas | Parcial | Evidencia completa; interpretación omite aptitud para el uso destinado |
| E02, alcance de gastos comunes | Incorrecto | Una propuesta resuelve la coordinación ambigua; otra neutral no elimina ese error |
| E03, conservación/devolución | Completo | Conserva obligaciones y excepciones, acta e inventario |
| E04, seguridad | Completo | Conserva seguridad y normas municipales; taxonomía a revisar aparte |
| E05, modificaciones | Completo | Conserva conformidad previa y tratamiento de devolución |

Resultado: **3/5 completos (60%), 1/3 críticos completos (33,3%) y una
propuesta con afirmación no respaldada**. No supera los umbrales automáticos.
Los bloques literales no mejoran artificialmente ese denominador. La revisión
es documental, no una aprobación jurídica o de Oikos. No se reescribió la
respuesta original ni se insertaron controles esperados como salida de Gemini.

El cálculo se verificó sin API con el evaluador existente y los controles del
manifiesto v9, sin modificar sus hashes:

```bash
python scripts/evaluate_contract_clause_corpus.py --document V04 --manifest ../docs/evaluaciones/hu30/corpus_v9_manifest.json --score-review ../docs/evaluaciones/hu30/revision_asistida_2026-10-05.json
```

Ese comando reutiliza controles y denominadores; su cabecera conserva el nombre
v9 del manifiesto, **no significa que el ensayo nuevo haya ejecutado v9**.
El resultado externo vigente utilizó el prompt `v10-asistida` y vive separado.

## Reproducir sin gastar cuota

Desde `backend/` del worktree:

```bash
../../../backend/venv/Scripts/python.exe scripts/evaluate_contract_assisted.py --env-file ../../../backend/.env
```

Este comando sólo verifica lectura local V01–V04. El indicador
`--run-public-v04` sí consume API y requiere una autorización nueva. Su checkpoint
impide repetir el ensayo ya registrado del 05/10: no borrarlo para forzar otro.
Las fuentes públicas descargadas y Tesseract/español deben estar disponibles
localmente. H01–H02 no se inspeccionaron ni consumieron.

La prueba de navegador se ejecuta desde `frontend/`, con un servidor Vite local
de prueba y `AARI_BROWSER_MODULES` apuntando al runtime de Playwright:

```text
node scripts/qa-contract-clauses.mjs
```

Usa API sintética, no credenciales reales. Capturas y resultado quedan en
`backend/artifacts/hu30-asistida-ui/`, ignorado por Git.

## Qué queda antes de cerrar

- Revisión visual/funcional de Talía y revisión de código/PR de Tobías.
- Aceptar explícitamente el cierre como flujo **asistido**, no como modelo
  autónomo que ya cumple los indicadores congelados.
- Decidir en seguimiento la evaluación semántica de V01–V03 y holdouts, cuando
  exista autorización y cupo. No se envían automáticamente al aprobar este flujo.
- Trasladar el ADR a Notion cuando el espacio permita agregar contenido.
- Commit/push/PR y cambios de estado/horas de Jira únicamente por indicación.

La funcionalidad implementada permite extraer y revisar sin depender de Gemini.
El riesgo residual es la interpretación humana: se debe contrastar el contenido
con el documento, especialmente obligaciones y excepciones ambiguas.

## Ajuste del editor y demostración grabada

Talía aprobó corregir la alineación del formulario y pidió dos videos para
compartir con Tobías. La fila de categoría, responsable y uso en reclamos ahora
alinea sus campos al inicio de la grilla: la ayuda más extensa de «Uso en
reclamos» no estira ni desplaza los controles vecinos. Se mantiene el componente
compartido y la estética de la skill de frontend de AARI.

La comprobación de geometría se incorporó al script de QA y se reprodujo en el
navegador: los tres selectores miden 44 px y comparten la misma posición vertical
en escritorio y a 768 px. A 390 px se apilan, conservan su altura y no hay
desbordamiento horizontal. La suite frontend se volvió a ejecutar: 112 pruebas
aprobadas; lint y build aprobados.

Los dos recorridos se grabaron sobre el mismo PDF público V04, con participantes
sintéticos y persistencia en memoria. La interfaz, validación del PDF, lectura
local y servicio de extracción son reales; el repositorio de demostración no
es Supabase. No se cargaron contratos privados ni se alteró la base compartida.
Marcar «firmado» en esta demostración sólo identifica una versión de prueba:
no firma un contrato ni acredita la validez jurídica del modelo público.

1. **Camino con IA:** adjuntar PDF → Proponer con IA → revisión como contexto.
   Una nueva llamada expresamente autorizada respondió HTTP 200, sin reintentos:
   5 propuestas de IA y 8 bloques literales recuperados localmente. Confirmar como
   contexto no habilitó la cláusula para reclamos.
2. **Camino sin IA:** adjuntar PDF → Extraer sin IA → 13 bloques literales →
   completar la interpretación de QUINTA → elegir uso operativo → Guardar y
   habilitar. Cero solicitudes externas. La cláusula revisada quedó habilitada
   sólo después de esa edición explícita.

La segunda respuesta de Gemini es evidencia de funcionamiento de la ruta,
**no una nueva evaluación semántica aprobada**. No reemplaza ni modifica la
respuesta histórica de 7 propuestas y 7 bloques literales ni sus puntuaciones.
Tampoco permite afirmar que el modelo cumpla los umbrales automáticos.

Grabaciones y evidencia diagnóstica: `backend/artifacts/hu30-videos/`, ignorado
por Git. Capturan la interfaz del navegador a aproximadamente dos cuadros por
segundo, sin audio ni escritorio, conservando la duración del recorrido sin
recortar la espera. El PDF público y las respuestas no contienen claves.
Estos archivos son entregables locales; no se incluyen videos pesados en el
repositorio. Al grabarlos todavía no se había autorizado commit/push ni cambios
de Jira; la autorización posterior de entrega figura en el estado de esta página.

### Corrección de la presentación de los videos

Talía señaló que parecían congelados. La comprobación identificó un intervalo
inicial de 171,128 segundos sin cambios de imagen en el recorrido con IA y otro
de 27,805 segundos en el local, durante la selección del archivo. No eran tiempo
de respuesta de Gemini. La validación inicial de metadatos/carga no alcanzaba
para dar por buena la presentación de la demostración.

Se aprobó crear **copias editadas**, manteniendo los originales:

- `con-ia-editado.mp4`: se omiten 167,128 segundos de esa pausa; se conservan
  cuatro segundos de su imagen inicial/final y todos los cambios de pantalla.
- `sin-ia-editado.mp4`: se omiten 23,805 segundos de esa pausa; la misma política.

Cada corte se identifica en el video con una tarjeta «Espera recortada» y su
duración. Una cabecera y una banda indican que son versiones editadas, no una
ejecución nueva ni una medición de latencia. El cierre del video sin IA usa una
captura posterior, rotulada como comprobación del resultado final; no se
presenta como una acción adicional de la grabación original. El cierre con IA
mantiene un cuadro del editor original con uso «Sólo contexto para revisión».

Los videos siguen sin audio. Las copias editadas y el informe de cortes viven
en la carpeta diagnóstica ignorada por Git. Esta edición no vuelve a ejecutar
la extracción, no consume API y no modifica los resultados registrados ni
Supabase. La revisión debe comprobar cuadros decodificados de los MP4 en
distintos momentos, no sólo que el archivo exista o que su duración avance.

Verificación de las copias editadas: **aprobada**. El navegador decodificó cinco
cuadros diferentes de cada MP4, incluidos estados del flujo y el cierre; se
inspeccionaron sus imágenes exportadas. Duraciones reales: 39,5 segundos con
Gemini y 38,5 segundos sin IA, ambos a 1226 × 660. El reporte queda en
`backend/artifacts/hu30-videos/verificacion-editados.json`. Además, una
comparación de hashes confirmó que la edición conserva todos los estados de
imagen distintos de los originales. Los MP4 originales no se sobrescribieron.
