import { apiRequest } from '../../../services/apiClient.js'

export function getProviderChoice(claimId, { signal } = {}) {
  return apiRequest(`/reclamos/${claimId}/tipo-proveedor`, { signal })
}

export function chooseProviderType(claimId, body) {
  return apiRequest(`/reclamos/${claimId}/tipo-proveedor`, { method: 'POST', body: JSON.stringify(body) })
}
