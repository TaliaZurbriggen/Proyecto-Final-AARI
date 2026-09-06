import { apiRequest } from '../../../services/apiClient.js'

export function getClaimContext({ signal } = {}) {
  return apiRequest('/reclamos/contexto', { signal })
}

export function createClaim({ descripcion, fotos, urgencia }) {
  const body = new FormData()
  body.append('descripcion', descripcion)
  body.append('urgencia', urgencia)
  fotos.forEach((photo) => body.append('fotos', photo))
  return apiRequest('/reclamos', { body, method: 'POST' })
}
