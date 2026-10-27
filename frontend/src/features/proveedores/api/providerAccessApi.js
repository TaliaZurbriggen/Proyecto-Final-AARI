import { apiRequest } from '../../../services/apiClient.js'

export const getProviderAccess = (id, options) => apiRequest(`/proveedores/${id}/acceso`, options)
export const inviteProvider = (id, payload) => apiRequest(`/proveedores/${id}/acceso`, {
  method: 'POST', body: JSON.stringify(payload),
})
export const activateProvider = (payload) => apiRequest('/auth/proveedores/activar', {
  method: 'POST', body: JSON.stringify(payload),
})
export const getProviderProfile = (options) => apiRequest('/proveedor/perfil', options)
