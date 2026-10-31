import { apiRequest } from '../../../services/apiClient.js'

const path = (id) => `/reclamos/${encodeURIComponent(id)}/proveedor-externo`
export const getExternalProvider = (id, { signal } = {}) => apiRequest(path(id), { signal })
export const registerExternalProvider = (id, body) => apiRequest(path(id), { method: 'POST', body: JSON.stringify(body) })

export function validateExternalProvider(values) {
  const nombre = values.nombre.normalize('NFC').trim().replace(/\s+/g, ' ')
  const rawPhone = values.telefono.trim()
  const telefono = rawPhone.replace(/[ +()-]/g, '')
  const errors = {}
  if (nombre.length < 3 || nombre.length > 120 || !/^[\p{L} '’-]+$/u.test(nombre) || !/\p{L}/u.test(nombre)) {
    errors.nombre = 'Ingresá un nombre completo de 3 a 120 caracteres, sin números ni símbolos.'
  }
  if (!/^\+?[0-9 ()-]+$/.test(rawPhone) || !/^[0-9]{8,15}$/.test(telefono)) {
    errors.telefono = 'Ingresá un teléfono de 8 a 15 dígitos, sin letras.'
  }
  return { errors, normalized: { nombre, telefono } }
}
