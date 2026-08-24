import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InquilinosListPage from './InquilinosListPage.jsx'

function jsonResponse(body) {
  return {
    headers: { get: () => 'application/json' },
    json: async () => body,
    ok: true,
    status: 200,
  }
}

function renderList() {
  return render(
    <MemoryRouter initialEntries={['/inquilinos']}>
      <Routes>
        <Route path="inquilinos" element={<InquilinosListPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('listado de inquilinos', () => {
  it('muestra identidad, contacto, propiedad y estado', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
            nombre_completo: 'Lucía Pérez',
            dni: '30123456',
            email: 'lucia@example.com',
            telefono: '+54 9 3564 555555',
            propiedad: {
              id: '4fd4e07c-6259-45f1-b8b3-6a607235cc89',
              direccion: 'Av. San Martín 120',
              provincia: 'Santa Fe',
              localidad: 'San Francisco',
              tipo: 'departamento',
              piso: 0,
              numero: 'B',
            },
            estado: 'activo',
            cantidad_reclamos: 0,
            created_at: '2026-08-23T12:00:00Z',
            updated_at: '2026-08-23T12:00:00Z',
          },
        ],
        page: 1,
        page_size: 10,
        total: 1,
        total_pages: 1,
      }),
    )

    renderList()

    expect(await screen.findByRole('link', { name: 'Lucía Pérez' })).toBeInTheDocument()
    expect(screen.getByText('lucia@example.com')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Av. San Martín 120/ })).toBeInTheDocument()
    expect(screen.getByText('Activo')).toBeInTheDocument()
  })

  it('explica el estado vacío', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ items: [], page: 1, page_size: 10, total: 0, total_pages: 0 }),
    )

    renderList()

    expect(await screen.findByText('Todavía no hay inquilinos')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Registrar el primero' })).toBeInTheDocument()
  })
})
