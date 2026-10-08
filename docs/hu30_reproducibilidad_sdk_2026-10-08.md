# HU30 / AARI-319 — Reproducibilidad del SDK (08/10/2026)

## Hallazgo y decisión aprobada

Después del merge del PR #28, Tobías detectó que una instalación nueva podía
resolver `google-genai==2.22.0`, aunque los diagnósticos congelados de HU30
registran `2.14.0`. `langchain-google-genai==4.3.2` estaba fijado, pero su
dependencia transitiva no. La prueba del prompt breve compara también las
versiones del SDK: el cambio de entorno invalidaba esa comparación controlada.

Se fija explícitamente `google-genai==2.14.0` en `backend/requirements.txt`.
La restricción declarada por `langchain-google-genai==4.3.2` es
`google-genai>=1.65.0,<3.0.0`, compatible con esa versión. Una nueva prueba
comprueba que ambos pins coincidan con el diagnóstico histórico, sin editarlo.
Antes del pin, esa prueba reprodujo la ausencia de `google-genai`: una aprobada
y una fallida. No se cambia la prueba histórica para aceptar versiones distintas.

Alternativas descartadas: regenerar evidencia antigua falsearía la comparación;
actualizar todo el SDK ampliaría innecesariamente el alcance. No se cambia el
prompt, el modelo, las migraciones ni el flujo asistido. Esta corrección no
equivale a bloquear todas las dependencias transitivas del proyecto.

Talía aprobó implementar y publicar en `codex/AARI-332-home-administrador`,
actualizada sobre `main` `69d0ec6`, dentro del PR #31 abierto. Es una excepción
explícita a la recomendación de un PR independiente. AARI-319 se reabrió
**En curso** hasta integrar el hotfix; sus subtareas previas y tiempos permanecen
intactos. No se autorizó merge ni nuevo registro de horas.

## Validación aislada

Se crea un entorno Windows/Python 3.13.12 nuevo en
`backend/artifacts/hu30-sdk-reproducibilidad-20261008/.venv`, ignorado por Git,
sin acceso a paquetes del entorno compartido (`include-system-site-packages=false`).
Se instala directamente desde `requirements.txt`; no se copia el entorno previo.
Pillow y `pypdfium2` ya estaban declarados y se incluyen en esta instalación.

Las pruebas no cargan `.env`, no cuentan con claves reales, mantienen desactivados
los workers externos y usan dobles para Gemini. PostgreSQL 17 se ejecuta en un
contenedor descartable, accesible sólo en loopback, sin volúmenes compartidos y
con datos sintéticos. No se llama a Gemini, SMTP o Supabase ni se consume cuota.

Comandos desde `backend/` (PowerShell, con las variables de aislamiento anteriores):

```powershell
$qaPython = 'artifacts/hu30-sdk-reproducibilidad-20261008/.venv/Scripts/python.exe'
& $qaPython -m pip --isolated install --disable-pip-version-check -r requirements.txt
& $qaPython -m pip check
& $qaPython -m pytest -q tests/test_contract_dependency_pins.py tests/test_contract_short_prompt_diagnostic.py
& $qaPython -m pytest -q
```

Resultados del entorno limpio:

- Instalación desde `requirements.txt`: aprobada; `google-genai 2.14.0`,
  `langchain-google-genai 4.3.2`, `pypdfium2 5.6.0` y `Pillow 12.3.0` presentes.
- `pip check`: **No broken requirements found**.
- Suite focalizada (dos regresiones nuevas y doce pruebas del diagnóstico):
  **14 passed**. El intento inicial tuvo siete errores de creación de temporales
  por restricciones del sandbox; se repitió con permisos y una carpeta temporal
  propia, sin cambiar las pruebas, y pasó completa.
- Backend completo, incluido PostgreSQL local: **810 passed, 37 skipped,
  18 warnings**, en 56,55 segundos. Las omitidas requieren servicios externos
  u opciones de integración no habilitadas; no se informa que hayan pasado.
  Las advertencias corresponden al adaptador datetime de SQLite en pruebas
  preexistentes de operadores e historial de propiedades.
- Se comprobó que no quedaron bases `aari_pr26_*` y se retiró únicamente el
  contenedor temporal de esta validación. El entorno compartido y los procesos
  de la aplicación local permanecen intactos.
- No se repite frontend: no cambia código de interfaz. Esta entrega modifica
  sólo requirements, la nueva prueba y documentación.

## Entrega y documentación

Se actualizará Jira con rama, commit, validaciones y revisión pendiente después
de publicar. Se intentó agregar la decisión en el apartado de decisiones técnicas
de Notion, pero la operación falló con HTTP 403, `block_limit_reached`: el espacio
agotó sus bloques gratuitos. No se informa Notion como actualizado ni se cambia
su plan. Este documento y el README conservan el registro versionado; queda
pendiente trasladarlo a Notion cuando el espacio permita agregar contenido.

No se modifica ni recalcula ningún resultado, manifiesto, hash, prompt o ejecutor
congelado de `docs/evaluaciones/hu30/`.
