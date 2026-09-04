import { describe, expect, it } from 'vitest'
import { claimPropertyLabel, normalizeClaim, validateClaim } from './validation.js'

describe('validación de reclamos', () => {
  it('requiere descripción suficiente y urgencia', () => {
    expect(validateClaim({ descripcion: 'Pérdida', fotos: [], urgencia: '' })).toEqual({
      descripcion: 'Describí el problema usando entre 20 y 1000 caracteres.',
      urgencia: 'Seleccioná el nivel de urgencia.',
    })
  })

  it('rechaza más de tres fotos y archivos mayores a 5 MB', () => {
    const small = { size: 100, type: 'image/png' }
    expect(
      validateClaim({
        descripcion: 'La canilla de la cocina pierde agua desde ayer.',
        fotos: [small, small, small, small],
        urgencia: 'media',
      }).fotos,
    ).toBe('Podés adjuntar hasta 3 fotos.')

    expect(
      validateClaim({
        descripcion: 'La canilla de la cocina pierde agua desde ayer.',
        fotos: [{ size: 5 * 1024 * 1024 + 1, type: 'image/jpeg' }],
        urgencia: 'alta',
      }).fotos,
    ).toBe('Cada foto debe pesar como máximo 5 MB.')
  })

  it('normaliza la descripción y forma la etiqueta de la unidad', () => {
    expect(
      normalizeClaim({ descripcion: '  Una descripción válida para enviar.  ' }).descripcion,
    ).toBe('Una descripción válida para enviar.')
    expect(
      claimPropertyLabel({
        direccion: 'Av. San Martín 120',
        localidad: 'San Francisco',
        numero: 'B',
        piso: 0,
        provincia: 'Santa Fe',
        tipo: 'departamento',
      }),
    ).toBe('Av. San Martín 120 · PB · Unidad B · San Francisco · Santa Fe')
  })
})
