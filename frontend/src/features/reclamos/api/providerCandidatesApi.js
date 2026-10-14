import { apiRequest } from '../../../services/apiClient.js'

export const listPendingAssignment = (query, options) =>
  apiRequest(`/reclamos/pendientes-asignacion?${query}`, options)
export const getProviderCandidates = (id, query, options) =>
  apiRequest(`/reclamos/${id}/proveedores-candidatos?${query}`, options)
export const getCandidateSpecialties = (options) =>
  apiRequest('/reclamos/especialidades-proveedores', options)
export const searchProviderCandidates = (id, body) =>
  apiRequest(`/reclamos/${id}/buscar-proveedores`, { method: 'POST', body: JSON.stringify(body) })
