import { describe, expect, it } from 'vitest'
import { normalizePropietario, validatePropietario } from './validation.js'

describe('validación de propietarios', () => {
  it('acepta datos válidos y normaliza el email', () => {
    const values = {
      nombre_completo: '  Ana Martínez  ',
      dni: '30123456',
      email: '  ANA@EXAMPLE.COM ',
      telefono: ' +54 3564 555555 ',
    }

    expect(validatePropietario(values)).toEqual({})
    expect(normalizePropietario(values)).toEqual({
      nombre_completo: 'Ana Martínez',
      dni: '30123456',
      email: 'ana@example.com',
      telefono: '+54 3564 555555',
    })
  })

  it('explica cómo corregir DNI, email y teléfono inválidos', () => {
    const errors = validatePropietario({
      nombre_completo: '',
      dni: '30.123',
      email: 'correo-invalido',
      telefono: '12',
    })

    expect(errors).toMatchObject({
      nombre_completo: expect.any(String),
      dni: expect.any(String),
      email: expect.any(String),
      telefono: expect.any(String),
    })
  })
})
