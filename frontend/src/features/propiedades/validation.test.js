import { describe, expect, it } from 'vitest'
import { normalizePropiedad, validatePropiedad } from './validation.js'

const validValues = {
  direccion: ' Av. San Martín   120 ',
  provincia: 'Santa Fe',
  localidad: ' San   Francisco ',
  barrio: ' Centro ',
  tipo: 'departamento',
  piso: ' 0 ',
  numero: ' B ',
  propietario_id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
}

describe('validación de propiedades', () => {
  it('exige dirección, provincia, localidad, tipo y propietario', () => {
    const errors = validatePropiedad({
      direccion: '',
      provincia: '',
      localidad: '',
      barrio: '',
      tipo: '',
      piso: '',
      numero: '',
      propietario_id: '',
    })

    expect(errors).toMatchObject({
      direccion: expect.any(String),
      provincia: expect.any(String),
      localidad: expect.any(String),
      tipo: expect.any(String),
      propietario_id: expect.any(String),
    })
  })

  it('normaliza los datos de un departamento', () => {
    expect(normalizePropiedad(validValues)).toMatchObject({
      direccion: 'Av. San Martín 120',
      provincia: 'Santa Fe',
      localidad: 'San Francisco',
      barrio: 'Centro',
      piso: 0,
      numero: 'B',
    })
  })

  it('descarta piso y número para otros tipos', () => {
    expect(normalizePropiedad({ ...validValues, tipo: 'casa' })).toMatchObject({
      piso: null,
      numero: null,
    })
  })

  it('guarda el barrio vacío como null', () => {
    expect(normalizePropiedad({ ...validValues, barrio: '  ' }).barrio).toBeNull()
  })

  it('rechaza PB y explica que planta baja se representa con cero', () => {
    const errors = validatePropiedad({ ...validValues, piso: 'PB' })

    expect(errors.piso).toMatch(/0 para planta baja/i)
  })

  it('rechaza ubicaciones formadas únicamente por números', () => {
    const errors = validatePropiedad({
      ...validValues,
      direccion: '444',
      localidad: '444',
      barrio: '444',
    })

    expect(errors).toMatchObject({
      direccion: 'La dirección debe incluir el nombre de la calle o ruta.',
      localidad: 'La localidad debe contener al menos una letra.',
      barrio: 'El barrio debe contener al menos una letra.',
    })
  })

  it('acepta direcciones y localidades válidas que incluyen números', () => {
    const errors = validatePropiedad({
      ...validValues,
      direccion: 'Ruta 9 km 72',
      localidad: '9 de Julio',
      barrio: 'Barrio 300 Viviendas',
    })

    expect(errors).toEqual({})
  })
})
