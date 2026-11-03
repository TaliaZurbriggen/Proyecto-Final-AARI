import { apiRequest } from '../../../services/apiClient.js'

const path = (claimId) => `/reclamos/${encodeURIComponent(claimId)}/cancelacion-coordinacion`
export const getCoordinationCancellation = (claimId, options) => apiRequest(path(claimId), options)
export const cancelCoordination = (claimId, body) => apiRequest(path(claimId), {
  method: 'POST', body: JSON.stringify(body),
})
