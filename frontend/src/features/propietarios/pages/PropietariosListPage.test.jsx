import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PropietariosListPage from './PropietariosListPage.jsx'

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
    <MemoryRouter initialEntries={['/propietarios']}>
      <Routes>
        <Route path="propietarios" element={<PropietariosListPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('listado de propietarios', () => {
  it('muestra los datos y la cantidad de inmuebles recibidos', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
            nombre_completo: 'Ana Martínez',
            dni: '30123456',
            email: 'ana@example.com',
            telefono: '+54 3564 555555',
            cantidad_inmuebles: 2,
            created_at: '2026-08-22T12:00:00Z',
            updated_at: '2026-08-22T12:00:00Z',
          },
        ],
        page: 1,
        page_size: 10,
        total: 1,
        total_pages: 1,
      }),
    )

    renderList()

    expect(await screen.findByRole('link', { name: 'Ana Martínez' })).toBeInTheDocument()
    expect(screen.getByText('ana@example.com')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('explica el estado vacío y ofrece registrar el primer propietario', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        items: [],
        page: 1,
        page_size: 10,
        total: 0,
        total_pages: 0,
      }),
    )

    renderList()

    expect(await screen.findByText('Todavía no hay propietarios')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Registrar el primero' })).toBeInTheDocument()
  })
})
