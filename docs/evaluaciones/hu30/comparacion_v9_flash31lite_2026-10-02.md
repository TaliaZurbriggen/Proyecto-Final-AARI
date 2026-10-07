# HU30 — V04 con Gemini 3.1 Flash-Lite (02/10/2026)

## Autorización y alcance

Se recibió autorización explícita: «Sí, probar V04 con 3.1 Flash-Lite».
El alcance fue una única extracción del modelo público DGN V04, enviando su
texto a Google con el prompt v9 y el esquema existentes. No se envió el
contrato personal, no se activó facturación y no se cambió producción ni `.env`.

El ensayo anterior con Flash 3.6 también recibió 503. Esta comparación no
autoriza nuevos intentos, rotación automática ni otros documentos.

## Entrada y ejecución

- Modelo: `gemini-3.1-flash-lite`.
- Fuente: V04, dos páginas digitales legibles, 4.709 caracteres.
- Procedencia: [corpus público v2](corpus_v2.md).
- SHA-256 del PDF: `a921c2a9db516211b82398c52ad937e7a881d0ec6d248334fdf6d483bd303d1c`.
- Prompt: v9 experimental, 11.167 caracteres; SHA-256
  `cd1329993efe6187698281426454095cf4bf499755b6b7998e7469f9f707341e`.
- Esquema: `SourceClauseBatch`, método `function_calling`, sin cambios.
- Se comprobó la igualdad de entrada frente al ensayo v9/Lite mediante
  `validate_same_input`, y se verificaron los archivos congelados.
- Biblioteca: `langchain-google-genai` 4.3.2 y `google-genai` 2.14.0.
- Checkpoint independiente, escrito antes de invocar para impedir repeticiones.

## Resultado

La invocación terminó en `ServerError`, HTTP **503**, sin propuestas.
La evidencia está en [resultado original](resultados_v9_flash31lite/resultado_v04_v9_flash31lite.json).

| Dato | Registro |
|---|---|
| Inicio UTC | 2026-10-02 18:00:06.122986 |
| Fin UTC | 2026-10-02 18:00:37.027469 |
| Duración entre marcas | 30,90 segundos |
| Invocaciones del adaptador | 1 autorizada / 1 ejecutada |
| Reintentos manuales | 0 |
| Configuración del SDK | `max_retries=1`; intentos HTTP internos no verificados independientemente |
| Contratos privados enviados | 0 |

No corresponde calcular precisión semántica sin una respuesta evaluable.
El 503 no demuestra falta de cuota, clave inválida o que el prompt o esquema
sean la causa. Los diagnósticos mínimos anteriores respondieron, pero con
entradas diferentes y en otros momentos. No se generaliza su resultado.

No hubo nuevas pruebas unitarias ni una nueva ejecución de la suite: para
estos ensayos se utilizó exclusivamente código existente. La última suite
registrada permanece en 450 aprobadas, 23 omitidas y dos advertencias conocidas.
No se hizo commit, push, PR, actualización de Jira ni consulta a Supabase.

## Comprobación local posterior, sin Gemini

Se inspeccionó la preparación local de la misma fuente V04:

- Las dos páginas son legibles y la lectura se considera completa.
- La reconstrucción por tramos conserva los 4.709 caracteres originales.
- Se reconocen 12 cláusulas consecutivas, de PRIMERA a DUODÉCIMA.
- QUINTA conserva su continuación entre páginas 1 y 2.
- Esta inspección no envió datos ni consumió cuota.

| Cláusula | Páginas | Caracteres del tramo |
|---|---|---:|
| 1 | 1 | 314 |
| 2 | 1 | 227 |
| 3 | 1 | 582 |
| 4 | 1 | 123 |
| 5 | 1–2 | 379 |
| 6 | 2 | 327 |
| 7 | 2 | 490 |
| 8 | 2 | 194 |
| 9 | 2 | 402 |
| 10 | 2 | 271 |
| 11 | 2 | 431 |
| 12 | 2 | 365 |

La conservación total incluye también texto fuera de los encabezados de
cláusulas, como la introducción. Reconocer 12 tramos no demuestra exactitud
de sus resúmenes, responsables o condiciones, ni generalización a todos los
contratos. No sustituye los cinco controles semánticos de V04.

## Propuesta de continuidad — pendiente de aprobación

### Objetivo y alcance

Permitir recuperar y revisar cláusulas literales sin depender de Gemini.
No sustituir la interpretación automática por una supuesta interpretación local.
Mantener la rama actual de HU30 y sus resultados históricos intactos.

1. Incorporar la acción explícita **Extraer cláusulas sin IA** en la revisión
   del documento. No ejecutar este modo ni llamar a Gemini automáticamente.
2. Leer el PDF digital o aplicar el OCR local ya disponible y separar cláusulas
   con el segmentador existente. Mostrar texto literal, número y páginas.
   Preservar los bloques no reconocidos para revisión; señalar lectura parcial
   o encabezados dudosos sin ocultarlos ni inventar cláusulas.
3. Identificar el origen como **Extracción literal; interpretación pendiente**.
   No asignar automáticamente un responsable ni inventar un resumen semántico.
   Administración completaría esos campos mediante el editor existente.
4. Conservar las revisiones anteriores, evidencia, propuestas originales e
   intentos fallidos. El repositorio actual admite un análisis por documento;
   este cambio no debe crear duplicados ni reemplazar silenciosamente lo
   revisado. Registrar modo/origen e intentos de forma auditable, con una
   migración aditiva si hace falta persistir esos metadatos.
5. Mantener el uso inicial como contexto y la activación operativa explícita.
   Una cláusula extraída no llega al clasificador por estar simplemente leída
   o confirmada. Las salvaguardas actuales se conservan.

### Componentes previstos

- Backend: servicio de extracción y procesamiento, esquemas de cláusulas,
  repositorio y API de análisis/revisión; reutilizar el segmentador y el OCR.
- Persistencia: metadatos de origen/modo e historial; no borrar análisis ni
  revisiones para permitir el nuevo flujo.
- Frontend: `ContractClausesPanel`, servicio de contratos y sus pruebas.
  Reutilizar `Button`, `StatusBadge`, `AlertMessage`, `LoadingState` y las
  tarjetas/editor actuales conforme a la skill `aari-frontend`.
- Documentación de HU30 y resultados de validación. No cambiar las métricas
  históricas, controles o umbrales de interpretación automática.

En móvil, apilar evidencia y editor, conservar etiquetas y foco visible,
controles táctiles de al menos 44 px y evitar scroll horizontal de la página.
No modificar la paleta ni la navegación aprobadas.

### Validación prevista

- Pruebas sin servicios externos: PDF digital, OCR simulado, continuación
  entre páginas, texto no reconocido y lectura incompleta.
- Cero invocaciones a Gemini en modo literal, incluso ante fallos anteriores.
- Persistencia, permisos de administración, concurrencia de revisiones,
  conservación de evidencia e impedimento de activación operativa implícita.
- Regresión local con V01–V04, sin consumir cuota ni tocar H01–H02.
- Pruebas del frontend, `npm run lint`, `npm run build`, revisión visual de
  escritorio/móvil y teclado si el navegador está disponible.
- OCR real y migración/integración real en Supabase sólo con autorización
  específica para esas validaciones externas y efectos sobre la base.

### Riesgos y decisión necesaria

Este flujo requiere trabajo de revisión de la inmobiliaria; no es equivalente
a extraer correctamente interpretaciones con IA. Los encabezados y la calidad
de OCR de otros contratos pueden requerir revisión manual. No se declara la
HU terminada ni se rebajan el 85% general, 100% crítico y cero afirmaciones
no respaldadas para aceptar la interpretación automática. Cerrar con este
alcance reducido exigiría un acuerdo explícito de producto con el equipo.

La propuesta sigue **sin implementar**. Esperar aprobación antes de editar
código o aplicar una migración; no quedan llamadas adicionales autorizadas.
