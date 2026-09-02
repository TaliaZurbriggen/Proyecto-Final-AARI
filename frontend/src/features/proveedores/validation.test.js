import { describe, expect, it } from 'vitest'
import { normalizeProveedor, validateProveedor } from './validation.js'

const values = {
  nombre_razon_social: ' Servicios del Centro ',
  matricula: ' mp 1234 ',
  telefono: '+54 9 3564 555555',
  activo: true,
  hora_inicio: '08:00',
  hora_fin: '17:30',
  especialidad_ids: ['specialty-1'],
  especialidades_personalizadas: ' Bombas, bombas ',
  coberturas: [
    {
      provincia: 'Córdoba',
      localidad: ' San   Francisco ',
      cubre_toda_localidad: false,
      barrios: 'Centro, La Milka, Centro',
    },
  ],
}

describe('validación de proveedores', () => {
  it('normaliza contacto, especialidades, horario y cobertura', () => {
    expect(validateProveedor(values)).toEqual({})
    expect(normalizeProveedor(values)).toEqual({
      nombre_razon_social: 'Servicios del Centro',
      matricula: 'MP 1234',
      telefono: '+5493564555555',
      activo: true,
      hora_inicio: '08:00',
      hora_fin: '17:30',
      especialidad_ids: ['specialty-1'],
      especialidades_personalizadas: ['bombas'],
      coberturas: [
        {
          provincia: 'Córdoba',
          localidad: 'San Francisco',
          cubre_toda_localidad: false,
          barrios: ['Centro', 'La Milka'],
        },
      ],
    })
  })

  it('rechaza horario nocturno, teléfono sin país y cobertura incompleta', () => {
    const errors = validateProveedor({
      ...values,
      telefono: '3564555555',
      hora_inicio: '18:00',
      hora_fin: '08:00',
      especialidad_ids: [],
      especialidades_personalizadas: '',
      coberturas: [
        {
          provincia: 'Córdoba',
          localidad: '444',
          cubre_toda_localidad: false,
          barrios: '',
        },
      ],
    })

    expect(errors.telefono).toMatch(/código de país/i)
    expect(errors.horario).toMatch(/posterior/i)
    expect(errors.especialidades).toBeTruthy()
    expect(errors['cobertura-0-localidad']).toBeTruthy()
    expect(errors['cobertura-0-barrios']).toBeTruthy()
  })

  it('evita repetir una misma provincia y localidad', () => {
    const errors = validateProveedor({
      ...values,
      coberturas: [
        { ...values.coberturas[0], cubre_toda_localidad: true, barrios: '' },
        { ...values.coberturas[0], localidad: 'san francisco', cubre_toda_localidad: true, barrios: '' },
      ],
    })

    expect(errors['cobertura-1-localidad']).toMatch(/ya están cargadas/i)
  })
})
