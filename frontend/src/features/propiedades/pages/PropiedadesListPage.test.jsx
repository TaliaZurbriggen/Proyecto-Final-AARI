import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PropiedadesListPage from './PropiedadesListPage.jsx'

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
    id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
    nombre_completo: 'Ana Martínez',
  },
  cantidad_reclamos: 0,
  tiene_inquilino_activo: false,
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

function propertyPage(items) {
  return {
    items,
    page: 1,
    page_size: 10,
    total: items.length,
    total_pages: items.length ? 1 : 0,
  }
}

function renderList() {
  return render(
    <MemoryRouter initialEntries={['/propiedades']}>
      <Routes>
        <Route path="propiedades" element={<PropiedadesListPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('listado de propiedades', () => {
  it('muestra ubicación, tipo y propietario', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(propertyPage([property])))

    renderList()

    expect(await screen.findByRole('link', { name: property.direccion })).toBeInTheDocument()
    expect(screen.getByText('San Francisco, Santa Fe')).toBeInTheDocument()
    expect(screen.getByText('Barrio Centro')).toBeInTheDocument()
    expect(screen.getByText('Planta baja (piso 0) · Unidad B')).toBeInTheDocument()
    expect(screen.getByText('Departamento')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ana Martínez' })).toBeInTheDocument()
  })

  it('evita solicitar la eliminación cuando existen reclamos históricos', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(propertyPage([{ ...property, cantidad_reclamos: 2 }])))
    renderList()

    await user.click(
      await screen.findByRole('button', { name: `Eliminar ${property.direccion}` }),
    )

    expect(
      screen.getByText(/tiene reclamos históricos asociados/i),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
