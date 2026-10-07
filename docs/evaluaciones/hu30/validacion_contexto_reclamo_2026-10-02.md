# HU30 — ensayo del contexto contractual en un reclamo (02/10/2026)

## Propósito y alcance

Comprobar si el clasificador usa el contexto contractual explícitamente
habilitado y comparar el modelo configurado para reclamos
(`gemini-3.5-flash`) con `gemini-3.5-flash-lite`. Es un ensayo funcional acotado,
no una medición estadística ni una validación jurídica.

Se usó un reclamo ficticio sobre expensas ordinarias habituales, sin obras ni
fondo de reserva. La cláusula de prueba, también ficticia, asigna únicamente
esos gastos al inquilino. No se envió ningún PDF ni dato personal. El ejecutor
reproducible es `backend/scripts/evaluate_claim_contract_context.py`, que
limita los reintentos y no imprime credenciales ni texto de excepciones.

## Resultados de Gemini

Se realizaron cuatro invocaciones lógicas autorizadas: un caso sin cláusula y
otro con la cláusula habilitada para cada modelo. Todas obtuvieron respuesta.

| Modelo | Contexto recibido | Resultado | Confianza | Lectura frente al prompt vigente |
| --- | --- | --- | ---: | --- |
| `gemini-3.5-flash` | Ninguno | Escala: `causa_no_identificable` | 0,60 | Respeta que la regla `expensas-01` requiere cláusula contractual. |
| `gemini-3.5-flash` | Cláusula ficticia habilitada | `expensa` | 0,95 | Usa la cláusula para fundamentar la clasificación. |
| `gemini-3.5-flash-lite` | Ninguno | `expensa` | 0,95 | Omite el requisito contractual de `expensas-01`; no es adecuado cambiar de modelo solo por cuota. |
| `gemini-3.5-flash-lite` | Cláusula ficticia habilitada | `expensa` | 0,95 | Menciona la cláusula en el fundamento. |

Esta diferencia demuestra uso del contexto en el caso ensayado, pero no prueba
la precisión general del clasificador ni que la cláusula sería legalmente
válida. No se modifica `GEMINI_MODEL` ni el modelo de extracción contractual.
Los límites de solicitudes dependen del modelo y del proyecto de AI Studio;
haber completado estas llamadas no permite inferir la cuota diaria de AARI.

## Validación del circuito

- Pruebas locales de activación y flujo HTTP/LangGraph:
  `10 passed, 1 skipped` en la primera ejecución; el caso PostgreSQL se ejecutó
  posteriormente por separado y pasó.
- Interfaz de contratos: `Contratos.test.jsx`, `17 passed`.
- Regresión completa sin servicios externos: backend `355 passed, 23 skipped`
  (dos advertencias de bibliotecas) y frontend `106 passed` en 24 archivos.
- El repositorio SQL selecciona únicamente cláusulas editadas y habilitadas
  expresamente de la última versión firmada de un contrato vigente; la prueba
  PostgreSQL existente cubre confirmación como contexto y habilitación explícita.
- En el primer intento, el pooler de Supabase rechazó el identificador del
  proyecto antes de ejecutar consultas. Tras la reactivación del proyecto, la
  misma prueba `test_migration_worker_review_context_rls_and_rollback` pasó
  sin cambiar el `.env`. Validó migraciones en un esquema aislado, propuestas
  como contexto, habilitación explícita, selección por propiedad/vigencia,
  permisos RLS y rollback; no dejó datos de prueba persistidos. El diagnóstico
  del segundo intento se capturó para no imprimir la conexión.

Antes de cerrar HU30 falta una revisión visual manual del flujo y la decisión
conjunta sobre el alcance de entrega: extracción asistida con revisión humana
frente a los umbrales internos de evaluación de propuestas, que v5 todavía no
alcanza en V04.
