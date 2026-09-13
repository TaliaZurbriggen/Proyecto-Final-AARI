import { apiRequest } from '../../../services/apiClient.js'

export function listContracts({ page = 1, pageSize = 10, search = '', inquilinoId = '', propiedadId = '', signal } = {}) {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (search.trim()) query.set('search', search.trim())
  if (inquilinoId) query.set('inquilino_id', inquilinoId)
  if (propiedadId) query.set('propiedad_id', propiedadId)
  return apiRequest(`/contratos?${query}`, { signal })
}
export const getContract = (id, options = {}) => apiRequest(`/contratos/${id}`, options)
export const createContract = (data) => apiRequest('/contratos', { method: 'POST', body: JSON.stringify(data) })
export const updateContract = (id, data) => apiRequest(`/contratos/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export function uploadContract(id, { file, signed, revision }) {
  const body = new FormData()
  body.append('archivo', file)
  body.append('firmado', String(signed))
  body.append('revision', String(revision))
  return apiRequest(`/contratos/${id}/documentos`, { method: 'POST', body })
}
export const downloadContract = (id, documentId) => apiRequest(`/contratos/${id}/documentos/${documentId}/descarga`, { method: 'POST' })
export const endContract = (id, data) => apiRequest(`/contratos/${id}/finalizar`, { method: 'POST', body: JSON.stringify(data) })
