const terminalStatuses = new Set(['Resuelto', 'Resuelto (sin confirmación)'])
const warningStatuses = new Set([
  'Escalado',
  'Pendiente de respuesta - vencido',
  'Sin presupuestos recibidos',
  'Sesión expirada',
  'Pendiente de autorización - vencido',
])
const dangerStatuses = new Set(['Rechazado por propietario'])

export function claimStatusTone(status) {
  if (terminalStatuses.has(status)) return 'success'
  if (dangerStatuses.has(status)) return 'danger'
  if (warningStatuses.has(status)) return 'warning'
  if (status === 'Recibido') return 'info'
  return 'neutral'
}

export function formatClaimNumber(number) {
  return `#${String(number).padStart(6, '0')}`
}

export function formatClaimDate(value, options = {}) {
  return new Intl.DateTimeFormat('es-AR', {
    dateStyle: options.short ? 'medium' : 'long',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function urgencyLabel(urgency) {
  return { alta: 'Alta', baja: 'Baja', media: 'Media' }[urgency] ?? urgency
}
