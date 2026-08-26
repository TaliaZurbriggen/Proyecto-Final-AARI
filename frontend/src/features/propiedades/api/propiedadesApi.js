import { apiRequest } from '../../../services/apiClient.js'

export function listPropiedades({ page = 1, pageSize = 10, search = '', signal }) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (search.trim()) params.set('search', search.trim())
  return apiRequest(`/propiedades?${params.toString()}`, { signal })
}

export async function listAllPropiedades({ signal } = {}) {
  const firstPage = await listPropiedades({ pageSize: 100, signal })
  if (firstPage.total_pages <= 1) return firstPage.items

  const remainingPages = await Promise.all(
    Array.from({ length: firstPage.total_pages - 1 }, (_, index) =>
      listPropiedades({ page: index + 2, pageSize: 100, signal }),
    ),
  )
  return [firstPage, ...remainingPages].flatMap((page) => page.items)
}

export function getPropiedad(propiedadId, { signal } = {}) {
  return apiRequest(`/propiedades/${propiedadId}`, { signal })
}

export function createPropiedad(payload) {
  return apiRequest('/propiedades', {
    body: JSON.stringify(payload),
    method: 'POST',
  })
}

export function updatePropiedad(propiedadId, payload) {
  return apiRequest(`/propiedades/${propiedadId}`, {
    body: JSON.stringify(payload),
    method: 'PUT',
  })
}

export function deletePropiedad(propiedadId) {
  return apiRequest(`/propiedades/${propiedadId}`, { method: 'DELETE' })
}
