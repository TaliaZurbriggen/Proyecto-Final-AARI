export const MAX_PDF_SIZE = 10 * 1024 * 1024
export function fileError(file, required = false) {
  if (!file) return required ? 'Seleccioná el PDF del contrato.' : ''
  if (!file.name.toLowerCase().endsWith('.pdf') || (file.type && !['application/pdf', 'application/octet-stream'].includes(file.type))) return 'Seleccioná un archivo PDF.'
  if (!file.size || file.size > MAX_PDF_SIZE) return 'El PDF debe pesar entre 1 byte y 10 MB.'
  return ''
}
export function validateDates(start, end) {
  const errors = {}
  if (!start) errors.fecha_inicio = 'Indicá la fecha de inicio.'
  if (!end) errors.fecha_fin = 'Indicá la fecha de finalización.'
  if (start && end && end <= start) errors.fecha_fin = 'La finalización debe ser posterior al inicio.'
  return errors
}
export const contractBase = (role) => role === 'administrador' ? '/contratos' : `/${role}/contratos`
export const dateLabel = (value) => value ? value.slice(0, 10).split('-').reverse().join('/') : '—'
export function nextDay(value) {
  const date = new Date(`${value}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + 1)
  return date.toISOString().slice(0, 10)
}
export const contractTone = (label) => ({ Vigente: 'success', Borrador: 'neutral', Vencido: 'warning', Finalizado: 'neutral', 'Próximo a iniciar': 'info' }[label] ?? 'neutral')
