import { apiRequest } from '../../services/apiClient.js'
export const getVisit = (id, options = {}) => apiRequest(`/reclamos/${encodeURIComponent(id)}/visita`, options)
export const listVisits = (page = 1, options = {}) => apiRequest(`/reclamos/visitas/propias?page=${page}&page_size=20`, options)
export const visitAction = (id, action, payload) => apiRequest(`/reclamos/${encodeURIComponent(id)}/visita/${action}`, { method: 'POST', body: JSON.stringify(payload) })
export const argentineTime = (day, time) => `${day}T${time}:00-03:00`
export const visitDate = (value) => value ? new Intl.DateTimeFormat('es-AR', { dateStyle: 'short', timeStyle: 'short', hourCycle: 'h23', timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date(value)) : 'Sin confirmar'
export const visitLabels = { esperando_disponibilidad: 'Esperando horarios del inquilino', esperando_confirmacion: 'Esperando al proveedor', negociando: 'Buscando otro horario', confirmada: 'Visita programada', sin_acuerdo: 'Sin acuerdo en plazo', invalidada: 'Coordinación no vigente' }
