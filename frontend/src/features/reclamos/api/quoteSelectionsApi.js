import { apiRequest } from '../../../services/apiClient.js'

const path = (claimId) => `/reclamos/${encodeURIComponent(claimId)}/seleccion-presupuesto`
export const getQuoteSelection = (claimId, options) => apiRequest(path(claimId), options)
export const selectQuote = (claimId, body) => apiRequest(path(claimId), {
  method: 'POST', body: JSON.stringify(body),
})
