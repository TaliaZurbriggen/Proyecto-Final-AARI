import { apiRequest } from '../../../services/apiClient.js'

export const listEscalatedClaims = (query, options) => apiRequest(`/reclamos/escalados?${query}`, options)
export const getEscalatedClaim = (id, options) => apiRequest(`/reclamos/escalados/${id}`, options)
export const resolveEscalatedClaim = (id, body) => apiRequest(`/reclamos/${id}/resolver-escalado`, {
  method: 'POST', body: JSON.stringify(body),
})

export function escalatedPhotoUrl(claimId, photoId) {
  const base = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')
  return `${base}/reclamos/escalados/${claimId}/fotos/${photoId}`
}
