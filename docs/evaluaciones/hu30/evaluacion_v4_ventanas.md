# HU30 — Evaluación v4 de V01 por ventanas superpuestas

## Decisión y alcance

El 26/09/2026 se decidió evaluar V01 en ventanas de **dos páginas consecutivas**,
con **una página de solapamiento**. V01 tiene nueve páginas y 33.048 caracteres
extraídos; las solicitudes v4 del documento completo devolvieron `503`, mientras
que V03 y una entrada sintética breve respondieron con el mismo modelo. Esto
motiva reducir la carga de cada solicitud, pero no demuestra por sí solo la causa
del `503` ni garantiza que las ventanas vayan a funcionar.

La estrategia usa ocho ventanas (páginas 1–2, 2–3, …, 8–9), conserva la numeración
original, el prompt v4 congelado, el modelo y las reglas de anclaje de evidencia.
No cambia el extractor de producción ni habilita cláusulas sin revisión humana.
Las propuestas idénticas se deduplican conservando las ventanas de origen; las
interpretaciones diferentes de una misma evidencia permanecen para revisión.
Los resultados por ventana se guardan aparte de la regresión de documento
completo y cada ventana terminada es un checkpoint que no se vuelve a enviar.

**Alternativas consideradas:** volver a intentar el documento completo podría
repetir los `503` y consumir llamadas sin evidencia nueva; aumentar el timeout
o los reintentos automáticos no aclara el diagnóstico; cambiar el prompt o el
modelo impediría atribuir el resultado al tamaño de la entrada. Las ventanas
de una sola página se descartaron porque podrían cortar cláusulas entre páginas.

## Ejecución y estado al 26/09/2026

La planificación local y la consolidación no llaman a Gemini. Cada
`--run-window` invoca el modelo una vez y requiere autorización previa. Antes
de la corrección del adaptador, una invocación podía producir hasta seis intentos
HTTP por reintentos internos ante `429` o `503`. Desde la corrección
`max_retries=1`, una invocación produce un solo intento HTTP.
Desde `backend/`:

```powershell
python -m scripts.evaluate_contract_clause_windows --document V01
python -m scripts.evaluate_contract_clause_windows --document V01 --run-window 3
python -m scripts.evaluate_contract_clause_windows --document V01 --assemble
```

- Ventana 1 (páginas 1–2): completada, una propuesta con evidencia anclada.
- Ventana 2 (páginas 2–3): completada, cero propuestas; no equivale a un error.
- Ventana 3 (páginas 3–4): intento fallido con `429 RESOURCE_EXHAUSTED`; no se
  creó resultado de esa ventana. El registro del intento no identifica qué
  límite concreto disparó ese error.
- Ventanas 4–8: no ejecutadas. No existe todavía resultado consolidado, revisión
  humana ni porcentaje de precisión de V01 por ventanas.

Los checkpoints están en `resultados_corpus_v4_ventanas/v01/ventana_01.json` y
`ventana_02.json`; el incidente de la ventana 3 se conserva en el subdirectorio
`fallos/` sin clave ni texto contractual. El ejecutor posterior registra metadatos
de cuota permitidos por el proveedor cuando estén disponibles, sin copiar su
mensaje libre. Para el incidente ya ocurrido solo se conoce el código `429`.

La consulta de solo lectura al panel de **Google AI Studio del proyecto AARI**
del 26/09/2026, con período «1 día» y nivel gratuito, mostró para Gemini 3.5
Flash máximos de **22/20 solicitudes por día (RPD)**, **5/5 solicitudes por
minuto (RPM)** y **40,26 mil/250 mil tokens de entrada por minuto (TPM)**.
También mostró el aviso de límite alcanzado. Por tanto, la cuota diaria está
agotada en ese período y no conviene hacer más llamadas hoy. Como el panel
informa máximos del período y advierte que los datos pueden tardar hasta 15
minutos en actualizarse, no se atribuye con certeza el `429` de la ventana 3
a una métrica particular.

El panel muestra uso **de todo el proyecto AARI**, no de esta evaluación. En la
hora de mayor tráfico mostró 16 solicitudes y 12,5 % de éxito. Nuestros archivos
registran invocaciones del modelo, no cada solicitud HTTP: las ventanas 1 y 2
terminaron y la 3 falló **antes** de fijar `max_retries=1`. El número exacto de
intentos HTTP de esas tres invocaciones y el origen del resto del tráfico no
pueden reconstruirse porque el historial de solicitudes está deshabilitado en
el nivel gratuito. Los `external_calls: 1` históricos significan una invocación
del ejecutor, no una prueba de un único intento HTTP.

## Avance del 27/09/2026

El panel de Google AI Studio del proyecto AARI mostró **0/20 RPD** para Gemini
3.5 Flash antes de reanudar. El primer preflight bloqueó la ejecución porque
el manifiesto conservaba la huella anterior del adaptador; se actualizó esa
huella tras el cambio operativo a `max_retries=1`, sin modificar el prompt ni
las reglas de extracción. Un segundo intento se detuvo antes de llamar a
Gemini porque este worktree no contiene `.env`; quedó un registro local de
fallo sin texto contractual. Se indicó el `.env` local del proyecto principal
sin copiar ni mostrar su clave.

Con autorización para **una ventana**, se ejecutó la ventana 3 (páginas 3–4):
**1 invocación, 3 propuestas, 3 con evidencia válida y 0 descartadas**. El
checkpoint `resultados_corpus_v4_ventanas/v01/ventana_03.json` quedó guardado.
Esto comprueba que el servicio respondió y que el validador aceptó esas citas;
todavía no establece si las propuestas son correctas frente a los controles
esperados, que requieren revisión humana.

**Plan tras la ventana 3:** con autorización para nuevas llamadas, continuar desde la
ventana 4 sin repetir las ventanas 1–3. Después de completar las ocho,
consolidar y revisar los controles antes de calcular precisión o comparar con
v3. V02 y V04 aún no tienen resultado v4; V03 sí respondió, pero sus controles
siguen sin revisión.

### Intento de ventana 4 del 27/09/2026

Con autorización para continuar de manera secuencial, se invocó una vez la
ventana 4 (páginas 4–5), ya con `max_retries=1`. Gemini respondió `503
UNAVAILABLE` tras 60,779 segundos. El ejecutor guardó únicamente el registro
seguro de fallo en `resultados_corpus_v4_ventanas/v01/fallos/`, sin texto
contractual ni clave, y **no creó** `ventana_04.json`. Los checkpoints de las
ventanas 1–3 permanecen intactos. Se detuvo la tanda según lo acordado: no se
ejecutaron las ventanas 5–8 ni V02/V04. El `503` es un fallo de disponibilidad
del servicio; este intento no proporciona una medición de precisión ni demuestra
que la cuota diaria se haya agotado.

Para retomar, habrá que decidir si conviene repetir una vez la ventana 4 cuando
el servicio esté disponible o cambiar la estrategia de evaluación. Cualquiera
de esas opciones requerirá autorización antes de otra llamada externa.

### Reintento controlado de ventana 4 del 27/09/2026

Tras esperar aproximadamente 27 minutos desde el primer `503`, se autorizó y
ejecutó **un solo reintento** de la ventana 4, sin reintentos automáticos. Gemini
respondió otra vez `503 UNAVAILABLE`, esta vez tras 13,882 segundos. Se conservó
el registro seguro del fallo y no se creó `ventana_04.json`; las ventanas 1–3
continúan guardadas. No se enviaron otras ventanas ni documentos. Dos `503` en
la misma ventana no prueban que su contenido sea la causa: únicamente confirman
que no hay resultado evaluable para las páginas 4–5 con la estrategia actual.
