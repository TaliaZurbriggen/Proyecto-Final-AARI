import { apiRequest } from '../../../services/apiClient.js'
import { listQuery } from '../../../services/listQuery.js'

export function listPropietarios({ page = 1, pageSize = 10, search = '', filters, signal }) {
  return apiRequest(`/propietarios?${listQuery({ page, pageSize, search, filters })}`, { signal })
}

export function getPropietario(propietarioId, { signal } = {}) {
  return apiRequest(`/propietarios/${propietarioId}`, { signal })
}

export function createPropietario(payload) {
  return apiRequest('/propietarios', {
    body: JSON.stringify(payload),
    method: 'POST',
  })
}

export function updatePropietario(propietarioId, payload) {
  return apiRequest(`/propietarios/${propietarioId}`, {
    body: JSON.stringify(payload),
    method: 'PUT',
  })
}

export function deletePropietario(propietarioId) {
  return apiRequest(`/propietarios/${propietarioId}`, { method: 'DELETE' })
}

export function retryPropietarioAccess(propietarioId) {
  return apiRequest(`/propietarios/${propietarioId}/acceso/reintentar`, {
    method: 'POST',
  })
}
