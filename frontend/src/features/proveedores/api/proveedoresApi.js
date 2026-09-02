import { apiRequest } from '../../../services/apiClient.js'

export function listEspecialidades({ signal } = {}) {
  return apiRequest('/especialidades', { signal })
}

export function listProveedores({
  page = 1,
  pageSize = 10,
  search = '',
  especialidadId = '',
  provincia = '',
  localidad = '',
  barrio = '',
  activo = '',
  signal,
}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (search.trim()) params.set('search', search.trim())
  if (especialidadId) params.set('especialidad_id', especialidadId)
  if (provincia) params.set('provincia', provincia)
  if (localidad.trim()) params.set('localidad', localidad.trim())
  if (barrio.trim()) params.set('barrio', barrio.trim())
  if (activo !== '') params.set('activo', activo)
  return apiRequest(`/proveedores?${params.toString()}`, { signal })
}

export function getProveedor(proveedorId, { signal } = {}) {
  return apiRequest(`/proveedores/${proveedorId}`, { signal })
}

export function createProveedor(payload) {
  return apiRequest('/proveedores', {
    body: JSON.stringify(payload),
    method: 'POST',
  })
}

export function updateProveedor(proveedorId, payload) {
  return apiRequest(`/proveedores/${proveedorId}`, {
    body: JSON.stringify(payload),
    method: 'PUT',
  })
}

export function updateProveedorEstado(proveedorId, activo) {
  return apiRequest(`/proveedores/${proveedorId}/estado`, {
    body: JSON.stringify({ activo }),
    method: 'PATCH',
  })
}
