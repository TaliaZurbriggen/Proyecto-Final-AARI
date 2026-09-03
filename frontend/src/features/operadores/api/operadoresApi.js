import { apiRequest } from '../../../services/apiClient.js'

const path = '/usuarios/operadores'

export function listOperadores({ page = 1, search = '', signal } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: '10' })
  if (search.trim()) params.set('search', search.trim())
  return apiRequest(`${path}?${params}`, { signal })
}

export function createOperador(payload) {
  return apiRequest(path, { method: 'POST', body: JSON.stringify(payload) })
}

export function deactivateOperador(id) {
  return apiRequest(`${path}/${id}/desactivar`, { method: 'PATCH' })
}

export function retryOperadorAccess(id) {
  return apiRequest(`${path}/${id}/acceso/reintentar`, { method: 'POST' })
}
