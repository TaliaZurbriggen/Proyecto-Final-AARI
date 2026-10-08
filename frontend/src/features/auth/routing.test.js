import { describe, expect, it } from 'vitest'
import { destinationForUser, homePathForRole } from './routing.js'

describe('destinos después de iniciar sesión', () => {
  it.each([
    ['administrador', '/inicio'], ['inquilino', '/inquilino'],
    ['operador', '/operador'], ['propietario', '/propietario'],
  ])('conserva el destino correcto para %s', (rol, expected) => {
    expect(homePathForRole(rol)).toBe(expected)
    expect(destinationForUser({ rol, primer_ingreso: false })).toBe(expected)
    expect(destinationForUser({ rol, primer_ingreso: true })).toBe('/cambiar-contrasena')
  })
  it('envía sesiones ausentes y roles desconocidos al login', () => {
    expect(destinationForUser(null)).toBe('/login')
    expect(homePathForRole('desconocido')).toBe('/login')
  })
})
