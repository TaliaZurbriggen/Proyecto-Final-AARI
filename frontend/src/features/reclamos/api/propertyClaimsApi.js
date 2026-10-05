import { apiRequest } from '../../../services/apiClient.js'

export function listPropertyClaims(propertyId, query, { signal } = {}) {
  const suffix = query ? `?${query}` : ''
  return apiRequest(`/propiedades/${propertyId}/reclamos${suffix}`, { signal })
}

export function getPropertyClaim(propertyId, claimId, { signal } = {}) {
  return apiRequest(`/propiedades/${propertyId}/reclamos/${claimId}`, { signal })
}
