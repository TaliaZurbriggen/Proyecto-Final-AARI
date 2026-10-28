import { apiRequest } from '../../../services/apiClient.js'

export const listQuoteRequests = (page, estado, options) => apiRequest(`/proveedor/solicitudes?${new URLSearchParams({ page: String(page), page_size: '10', estado })}`, options)
export const getQuoteRequest = (id, options) => apiRequest(`/proveedor/solicitudes/${id}`, options)
export const submitQuote = (id, body) => apiRequest(`/proveedor/solicitudes/${id}/presupuesto`, {
  method: 'POST', body: JSON.stringify(body),
})
export const getClaimQuotes = (id, options) => apiRequest(`/reclamos/${id}/presupuestos`, options)
