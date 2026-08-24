import { describe, expect, it } from 'vitest'
import { normalizeInquilino, validateInquilino } from './validation.js'

const validValues = {
  nombre_completo: 'Lucía Pérez',
  dni: '30123456',
  email: 'lucia@example.com',
  telefono: '+54 9 3564 555555',
  propiedad_id: '4fd4e07c-6259-45f1-b8b3-6a607235cc89',
}

describe('validación de inquilinos', () => {
  it('rechaza identidad, contacto y propiedad incompletos', () => {
    const errors = validateInquilino({
      nombre_completo: 'x',
      dni: '30.123.456',
      email: 'invalido',
      telefono: '123',
      propiedad_id: '',
    })

    expect(errors).toEqual(expect.objectContaining({
      nombre_completo: expect.any(String),
      dni: expect.any(String),
      email: expect.any(String),
      telefono: expect.any(String),
      propiedad_id: expect.any(String),
    }))
  })

  it('permite editar un inquilino sin propiedad asignada', () => {
    expect(
      validateInquilino(
        { ...validValues, propiedad_id: '' },
        { propertyRequired: false },
      ),
    ).toEqual({})
  })

  it('normaliza espacios, email y asociación vacía', () => {
    expect(
      normalizeInquilino({
        ...validValues,
        nombre_completo: '  Lucía   Pérez ',
        email: ' LUCIA@EXAMPLE.COM ',
        telefono: ' +54 9 3564   555555 ',
        propiedad_id: '',
      }),
    ).toMatchObject({
      nombre_completo: 'Lucía Pérez',
      email: 'lucia@example.com',
      telefono: '+54 9 3564 555555',
      propiedad_id: null,
    })
  })

  it.each(['43428013', 'Juan123', '@@@'])(
    'rechaza %s como nombre completo',
    (nombre_completo) => {
      expect(
        validateInquilino({ ...validValues, nombre_completo }).nombre_completo,
      ).toBe(
        'Ingresá un nombre válido usando solo letras, espacios, apóstrofes o guiones.',
      )
    },
  )

  it.each(["María José O'Connor", 'Ana-María Pérez', 'Zoë Dubois'])(
    'acepta %s como nombre completo',
    (nombre_completo) => {
      expect(
        validateInquilino({ ...validValues, nombre_completo }).nombre_completo,
      ).toBeUndefined()
    },
  )
})
