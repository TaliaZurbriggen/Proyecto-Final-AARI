export const quoteLabels = { pendiente: 'Pendiente', respondida: 'Presupuesto enviado', vencida: 'Vencida', cancelada: 'Cancelada' }
export const quoteListFilters = { pendientes: 'Pendientes', enviadas: 'Enviadas', todas: 'Todas' }
export const quoteListFilter = (value) => Object.hasOwn(quoteListFilters, value) ? value : 'pendientes'
export const quoteDate = (value) => new Date(value).toLocaleString('es-AR', { timeZone: 'America/Argentina/Buenos_Aires', dateStyle: 'short', timeStyle: 'short' })
export function quoteAmount(quote) {
  const amount = new Intl.NumberFormat('es-AR', { style: 'currency', currency: quote.moneda, minimumFractionDigits: 2 }).format(Number(quote.monto))
  return `${quote.tipo_importe === 'minimo' ? 'Desde ' : ''}${amount} ${quote.moneda}`
}
export function positiveAmount(value) {
  const trimmed = value.trim()
  if (!/^\d{1,10}([.,]\d{1,2})?$/.test(trimmed)) return null
  const normalized = trimmed.replace(',', '.')
  return Number(normalized) > 0 ? normalized : null
}
