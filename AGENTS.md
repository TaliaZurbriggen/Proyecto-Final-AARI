# Guía de trabajo para agentes Codex — AARI

Estas instrucciones aplican a todo el repositorio.

## Forma de trabajo

La persona responsable del proyecto debe comprender y aprobar cada cambio antes
de que se implemente.

1. Para toda tarea de implementación, explicar primero una propuesta en español
   claro. Debe indicar objetivo, alcance, archivos previstos, decisiones de
   diseño, dependencias, pruebas y riesgos o pendientes.
2. No crear ni editar código, instalar dependencias, ejecutar migraciones,
   hacer commits ni subir cambios hasta recibir una aprobación explícita de la
   propuesta.
3. Se permiten inspecciones de solo lectura para preparar la propuesta.
4. Si la implementación revela una decisión de producto o arquitectura no
   acordada, detenerse, explicar las alternativas y esperar indicación.

## Implementación y validación

- Crear una rama desde la versión actual de `main` para cada tarea.
- Mantener el alcance limitado a la tarea acordada y no modificar trabajo ajeno.
- Nunca incluir claves, contraseñas ni datos personales en código, commits,
  documentación o mensajes. Usar archivos `.env` locales y `.env.example` sin
  valores reales.
- Ejecutar pruebas proporcionales al cambio antes de dar por lista una tarea.
- Las pruebas que consuman una API externa, cuota o dinero requieren autorización
  explícita. Las pruebas automatizadas deben usar dobles o mocks cuando sea
  posible.
- Antes de commit o push, revisar el diff y comprobar que no haya secretos ni
  errores de formato.

## Cierre de una implementación

Al finalizar, entregar un resumen que incluya:

- Qué se implementó y las decisiones relevantes.
- Archivos o componentes principales afectados.
- Pruebas ejecutadas, comandos y resultados.
- Qué no se pudo validar, riesgos y próximos pasos, si existieran.

No hacer commit, push, abrir PR, fusionar ramas ni cerrar tareas de Jira sin una
indicación explícita de la persona responsable. Una vez autorizado, dejar en
Jira un comentario breve con rama, commit, validaciones y estado de revisión.

## Documentación

Registrar en Notion las decisiones técnicas o de producto que cambien el rumbo
del proyecto, incluyendo contexto, alternativas consideradas y motivo de la
decisión. Mantener el README actualizado cuando cambie la forma de levantar el
proyecto, su estructura o el estado relevante del Sprint.
