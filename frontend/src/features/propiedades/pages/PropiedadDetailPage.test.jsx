import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PropiedadDetailPage from './PropiedadDetailPage.jsx'

const property = {
  id: '4fd4e07c-6259-45f1-b8b3-6a607235cc89',
  direccion: 'Av. San Martín 120',
  provincia: 'Santa Fe',
  localidad: 'San Francisco',
  barrio: 'Centro',
  tipo: 'departamento',
  piso: 0,
  numero: 'B',
  propietario: {
    id: '81d0af67-65e4-4143-9f2e-31355e6640f6',
    nombre_completo: 'Ana Martínez',
  },
  cantidad_reclamos: 0,
  tiene_inquilino_activo: true,
  created_at: '2026-08-23T12:00:00Z',
  updated_at: '2026-08-23T12:00:00Z',
}

const tenant = {
  id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
  nombre_completo: 'Lucía Pérez',
  dni: '30123456',
  email: 'lucia@example.com',
  telefono: '+54 9 3564 555555',
  propiedad: property,
  estado: 'activo',
  cantidad_reclamos: 0,
  created_at: '2026-08-23T12:00:00Z',
  updated_at: '2026-08-23T12:00:00Z',
}

function jsonResponse(body) {
  return {
    headers: { get: () => 'application/json' },
    json: async () => body,
    ok: true,
    status: 200,
  }
}

afterEach(() => vi.restoreAllMocks())

describe('detalle de propiedad con inquilino', () => {
  it('muestra al inquilino asociado después del alta', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(property))
      .mockResolvedValueOnce(jsonResponse(tenant))

    render(
      <MemoryRouter initialEntries={[`/propiedades/${property.id}`]}>
        <Routes>
          <Route path="propiedades/:propiedadId" element={<PropiedadDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Lucía Pérez')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver inquilino' })).toHaveAttribute(
      'href',
      `/inquilinos/${tenant.id}`,
    )
    expect(screen.getByText('Ocupada')).toBeInTheDocument()
    expect(
      screen.getAllByText('Tiene un inquilino activo. Primero debe resolverse esa asociación.'),
    ).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Eliminar' })).toBeDisabled()
  })
})
