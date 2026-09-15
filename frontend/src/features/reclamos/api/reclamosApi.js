import { apiRequest } from '../../../services/apiClient.js'

export function getClaimContext({ signal } = {}) {
  return apiRequest('/reclamos/contexto', { signal })
}

export function listMyClaims({ signal } = {}) {
  return apiRequest('/reclamos', { signal })
}

export function getMyClaim(claimId, { signal } = {}) {
  return apiRequest(`/reclamos/${claimId}`, { signal })
}

export function createClaim({ descripcion, fotos, urgencia }) {
  const body = new FormData()
  body.append('descripcion', descripcion)
  body.append('urgencia', urgencia)
  fotos.forEach((photo) => body.append('fotos', photo))
  return apiRequest('/reclamos', { body, method: 'POST' })
}
