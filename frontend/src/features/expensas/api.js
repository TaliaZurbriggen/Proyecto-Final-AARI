import { apiRequest } from '../../services/apiClient.js'

export const listExpenses = (query, options) => apiRequest(`/expensas?${query}`, options)
export const getExpense = (id, options) => apiRequest(`/expensas/${id}`, options)
export const addExpenseNote = (id, contenido, options) => apiRequest(`/expensas/${id}/notas`, {
  ...options, method: 'POST', body: JSON.stringify({ contenido }),
})
export const getAgencyEmail = (options) => apiRequest('/configuracion/correo-inmobiliaria', options)
export const updateAgencyEmail = (email, options) => apiRequest('/configuracion/correo-inmobiliaria', {
  ...options, method: 'PUT', body: JSON.stringify({ email }),
})

export const deliveryLabels = {
  pendiente: 'Reporte pendiente', procesando: 'Enviando reporte', enviado: 'Reporte enviado',
  fallido: 'Reporte no enviado', configuracion_pendiente: 'Configuración pendiente',
  historico: 'Sin reporte HU14',
}
export const deliveryTone = (status) => status === 'enviado' ? 'success'
  : status === 'fallido' ? 'danger' : ['pendiente', 'procesando', 'configuracion_pendiente'].includes(status)
    ? 'warning' : 'neutral'
