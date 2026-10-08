import { apiRequest } from '../../../services/apiClient.js'
import { listQuery } from '../../../services/listQuery.js'

export function listInquilinos({ page = 1, pageSize = 10, search = '', filters, signal }) {
  return apiRequest(`/inquilinos?${listQuery({ page, pageSize, search, filters })}`, { signal })
}

export function getInquilino(inquilinoId, { signal } = {}) {
  return apiRequest(`/inquilinos/${inquilinoId}`, { signal })
}

export function getPropertyTenant(propiedadId, { signal } = {}) {
  return apiRequest(`/propiedades/${propiedadId}/inquilino`, { signal })
}

export function createInquilino(payload) {
  return apiRequest('/inquilinos', {
    body: JSON.stringify(payload),
    method: 'POST',
  })
}

export function updateInquilino(inquilinoId, payload) {
  return apiRequest(`/inquilinos/${inquilinoId}`, {
    body: JSON.stringify(payload),
    method: 'PUT',
  })
}

export function disassociateInquilino(inquilinoId) {
  return apiRequest(`/inquilinos/${inquilinoId}/desasociar`, {
    method: 'PATCH',
  })
}

export function deleteInquilino(inquilinoId) {
  return apiRequest(`/inquilinos/${inquilinoId}`, { method: 'DELETE' })
}

export function retryInquilinoAccess(inquilinoId) {
  return apiRequest(`/inquilinos/${inquilinoId}/acceso/reintentar`, {
    method: 'POST',
  })
}
