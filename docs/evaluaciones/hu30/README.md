# Insumos locales de HU30

Preparación iniciada el 14/09/2026: copia anonimizada, resultados esperados y
[diseño técnico](../../hu30_extraccion_clausulas.md). Al 21/09 la funcionalidad
está implementada y validada con modelos simulados, OCR real y ejecuciones reales
de Gemini mediante `function_calling`. La salida continúa pendiente de revisión
humana y no se incorpora automáticamente al clasificador.

## Entregables

- [PDF de ejemplo anonimizado](../../../output/pdf/hu30_contrato_anonimizado.pdf).
- [17 controles de resultados esperados](resultados_esperados_ejemplo_01.md).
- [Verificación del PDF](../../../output/pdf/hu30_contrato_anonimizado.verificacion.json).
- [Resultado estructurado v1](resultado_gemini_ejemplo_01.json) y
  [evaluación v1](evaluacion_gemini_ejemplo_01.md).
- [Resultado estructurado v2](resultado_gemini_ejemplo_01_v2.json) y
  [evaluación v2](evaluacion_gemini_ejemplo_01_v2.md).
- [Registro de los tres intentos autorizados](intento_gemini_2026-09-21.json).
- [Corpus v2 de generalización](corpus_v2.md), con manifiesto verificable,
  cuatro modelos públicos y 23 resultados esperados.
- [Evaluación consolidada del corpus v2](evaluacion_corpus_v2.md): cuatro
  llamadas, revisión control por control y conclusiones.
- [Preparación local v3](preparacion_v3.md): anclaje exacto, tratamiento de
  ambigüedad, regresión local y manifiesto congelado.
- [Evaluación de regresión v3](evaluacion_corpus_v3.md): cuatro llamadas sin
  reintentos, 19/23 controles completos, 12/15 críticos y cero alucinaciones
  aceptadas.
- [Preparación local v4](preparacion_v4.md): reglas atómicas, evidencia breve,
  control explícito de coordinaciones ambiguas y manifiesto congelado.
- [Intento externo v4 del 24/09](intento_v4_2026-09-24.json): V01 bloqueado por
  cuota gratuita antes de generar resultados; V02-V04 no fueron enviados.
- [Intento externo v4 del 25/09](intento_v4_2026-09-25.json): V01 y V02
  recibieron `503 UNAVAILABLE`; V03 y V04 no fueron enviados.

## Comprobaciones realizadas

| Comprobación | Resultado |
|---|---|
| Documento de origen | Hash antes/después idéntico; no se modificó. No se copia su ruta, nombre ni contenido privado al repositorio. |
| Paginación | 13 páginas, conservadas. |
| Zonas retiradas | 17 zonas revisadas: identidades, domicilios, contactos, administración identificable, fechas y montos concretos. |
| Identificadores reconocibles | 15 ocurrencias de DNI/correo/teléfono recuperadas en memoria del contenido retirado; ninguna reaparece en la salida. |
| Secuencias retiradas | 208 secuencias particulares de tres palabras contrastadas, sin reapariciones en el texto de salida. Este chequeo complementa la revisión; no prueba anonimización de cualquier documento. |
| Conservación de texto | Todos los caracteres fuera de las zonas suprimidas coinciden en orden por página usando pdfplumber. |
| Lectura digital | PDF final legible con pypdf; se corrigió la primera reconstrucción para conservar frases en lugar de generar saltos entre cada letra. |
| Privacidad del contenedor | PDF reconstruido desde cero; sin objetos del original, adjuntos, anotaciones, formularios ni acciones de apertura. Metadatos genéricos nuevos. |
| Revisión visual | 13/13 páginas renderizadas con Poppler e inspeccionadas; sin datos identificatorios visibles, solapamientos ni texto cortado. |
| Lectura local de HU30 | 13 páginas digitales, lectura completa y 21.126 caracteres; no requirió OCR. |
| Supabase | Migraciones 23 y 24 aplicadas; RLS comprobado y prueba aislada con rollback aprobada. |
| Gemini v1 | 18 propuestas, 14 con evidencia válida y 4 descartadas. Cobertura aceptada: 11/17 controles y 6/7 críticos. |
| Gemini v2 | 20 propuestas, 17 válidas y 3 rechazadas conservadas. Encontró los 17 controles; 14/17 quedaron con evidencia aceptada y 6/7 críticos. Recuperó E07 entre páginas. |
| OCR real | **Aprobado** con Tesseract 5.4.0 y español sobre un PDF sintético compuesto sólo por una imagen: 1 prueba aprobada. |

Los títulos, apartados y condiciones de mantenimiento/reparación se conservan.
La copia cambia las zonas de identificación y su tipografía se reconstruye con
fuentes locales, por lo que no pretende ser un facsímil ni un documento firmado.
Los plazos relativos y porcentajes contractuales se conservan para no alterar el
sentido de esas cláusulas; los importes particulares se retiraron.

## Reproducir la preparación local

`preparar_ejemplo_local.py` es una herramienta de autoría para **este ejemplo ya
revisado**, no el anonimizador de HU30 ni un servicio de la aplicación. No usarla
con otro contrato sin nueva revisión de las zonas. No incorpora el original ni
contiene sus valores personales. Requiere un archivo fuente local proporcionado
por su titular, Python con `pdfplumber`, `pypdf`, `reportlab` y las fuentes Calibri
del sistema. Estas dependencias se utilizaron desde el runtime de documentos;
no se cambiaron los requisitos del backend.

Desde la raíz de este worktree, con las dependencias disponibles:

```powershell
python docs/evaluaciones/hu30/preparar_ejemplo_local.py RUTA_PDF_LOCAL output/pdf/hu30_contrato_anonimizado.pdf --font-dir C:/Windows/Fonts
```

La herramienta valida el documento concreto, construye la copia sin datos
retirados, verifica el texto y genera el reporte JSON. Al regenerarlo, la revisión
visual vuelve a `pending`: renderizar e inspeccionar las 13 páginas antes de
marcarla como aprobada. Nunca subir el PDF original ni volcados de su texto.

## Pendientes de evaluación

1. Esperar a que Gemini vuelva a responder y, con una nueva autorización,
   iniciar la regresión v4 desde V01. H01-H02 continúan reservados por
   Tobías/Oikos hasta que la regresión conocida cumpla.
2. Revisar con la inmobiliaria qué cláusulas deben usar `operativa`, `contexto` o
   `excluir`; la revisión continúa editable y auditable.

La implementación no crea un PR por sí sola. Los cambios quedan locales en la
rama de HU30 hasta la indicación de commit/push. Se mantiene el acuerdo del
Sprint 3 de documentación en el repositorio mientras Notion esté limitado.
