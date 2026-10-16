import { apiRequest } from '../../../services/apiClient.js'

export const listOwnerExpenses = (page, options) =>
  apiRequest(`/propietario/reclamos?page=${page}`, options)
export const getOwnerExpense = (id, options) =>
  apiRequest(`/reclamos/${id}/autorizacion`, options)
export const decideOwnerExpense = (id, decision, body) =>
  apiRequest(`/reclamos/${id}/${decision}`, { method: 'POST', body: JSON.stringify(body) })
