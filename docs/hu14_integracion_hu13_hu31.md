# HU14 — Contrato de integración con HU13 y HU31

Guía para revisar/integrar HU14 sin incluir las historias ajenas en su PR.
Revisión del 07/10/2026: `main` sigue en `80afb67`, HU13/PR #29 sigue abierto
en `053236ac` y HU31 permanece en su rama `f6dd2206`. No se fusionaron ni
modificaron sus ramas. La prueba temporal combinada ya pasó; sus resultados
completos figuran en [hu14_derivacion_expensas.md](hu14_derivacion_expensas.md).

## Persistencia compartida con HU13

Al resolver el conflicto en `backend/app/db/reclamos.py`, conservar el helper
común y la auditoría manual de HU13. En su transacción de clasificación:

1. Mantener la revalidación del usuario activo, bloqueo del reclamo, versión
   esperada, resultado anterior y autor/rol de la decisión.
2. Conservar en la consulta los campos HU14: número, ingreso, descripción,
   urgencia, unidad y contacto mínimo del inquilino.
3. Para `tipo_gasto == 'expensa'` y responsable inmobiliaria, llamar a
   `expense_report(..., origin=params['origen'])` y después
   `enqueue_expense_report(session, report, recipient)` en la misma transacción.
   El origen puede ser agente, operador o administrador; la factory excluye
   confianza de LLM en decisiones humanas. No hacer llamadas a modelos ni SMTP.
4. Usar este reporte **en lugar de** `responsable_inicial`, no además de él.
   Ordinarios/extraordinarios mantienen el aviso genérico HU12.
5. Conservar la supresión del aviso inicial duplicado al inquilino para
   expensa: el aviso sencillo se genera al confirmar la derivación, por HU10.
6. Mantener confirmación de entrega con lease vigente y `clock_timestamp()`;
   no derivar antes del resultado SMTP ni sobreescribir un estado avanzado.

La prueba HU13
`test_manual_decision_preserves_evidence_and_starts_one_responsible_request`
debe esperar `expensa_reporte` para expensa y `responsable_inicial` para los
otros tipos, comprobando ausencia del otro evento. No debilitar verificaciones
de autoría, auditoría, concurrencia o rollback para adaptarla.

## Routers y navegación compartidos

- En `backend/app/main.py`, preservar routers de Home, escalados, expensas y
  configuración. Registrar las rutas estáticas de escalados antes de las rutas
  genéricas `/reclamos/{id}` para no interpretar `escalados` como UUID.
- En `frontend/src/App.jsx`, preservar Inicio/Home y rutas administrativas y
  operativas de escalados, además de las rutas privadas compartidas de Expensas.
- En `AdminLayout.jsx`, mantener navegación/variante visual de HU31 y sumar
  Expensas sin reemplazar Inicio ni Casos escalados. Preservar módulo activo
  y ocultar búsquedas globales cuando la pantalla gestiona sus propios filtros.
- En `RoleLayout.jsx`, el operador debe conservar Casos escalados y Expensas.
  Inquilino/propietario no reciben esos accesos.
- El botón interno `Revisar casos` del Home sigue deshabilitado en HU31.
  Habilitarlo corresponde a la integración de esa historia con HU13; no se
  modifica el Home como parte de este PR de HU14.

## Validación de la combinación definitiva

Repetir suites completas backend/frontend, lint/build y recorrido con
PostgreSQL local descartable y SMTP simulado. Incluir decisiones de operador y
administrador: reporte único con origen humano/confianza nula, autoría y
resultado anterior intactos, transición solo tras entrega registrada, un
aviso sencillo al inquilino sin notas/fundamento y rechazo de decisión repetida.
Verificar Home: al clasificar baja el contador de pendientes, pero el reclamo
sigue activo porque todavía no está reparado. Verificar roles y móvil.

No reaplicar migraciones HU14 por hacer pull: ya se aplicaron al Supabase de
desarrollo. Consultar nombres/versiones locales y remotas en el documento de
HU14; no renombrar SQL aplicado ni copiar seeds/contactos reales. La prueba
temporal acredita las versiones indicadas, no versiones posteriores ni un
merge ya publicado. Resolver conflictos sobre la combinación aprobada vigente.
