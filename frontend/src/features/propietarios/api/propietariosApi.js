import { apiRequest } from '../../../services/apiClient.js'

export function listPropietarios({ page = 1, pageSize = 10, search = '', signal }) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (search.trim()) params.set('search', search.trim())
  return apiRequest(`/propietarios?${params.toString()}`, { signal })
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
