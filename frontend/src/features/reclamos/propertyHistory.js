export const CLAIM_STATES = [
  'Recibido', 'Clasificado', 'Clasificación pendiente', 'Escalado',
  'Pendiente de respuesta del responsable', 'Pendiente de respuesta - vencido',
  'Autorizado', 'Rechazado por propietario', 'Pendiente de asignación',
  'Sin presupuestos recibidos', 'Proveedor seleccionado', 'En proceso',
  'Visita programada', 'Resuelto', 'Resuelto (sin confirmación)',
  'Reabierto por disconformidad', 'Derivado a inmobiliaria (expensa)',
  'Derivado a proveedor externo', 'Sesión expirada', 'Pendiente de autorización - vencido',
]

export const EXPENSE_LABELS = {
  ordinario: 'Ordinario', extraordinario: 'Extraordinario', expensa: 'Expensa',
  sin_clasificar: 'Sin clasificar',
}

export function expenseLabel(value) {
  return EXPENSE_LABELS[value] ?? 'Sin clasificar'
}

export function propertyHistoryPath(propertyId, tenantView = false) {
  return `${tenantView ? '/inquilino' : ''}/propiedades/${propertyId}/reclamos`
}
