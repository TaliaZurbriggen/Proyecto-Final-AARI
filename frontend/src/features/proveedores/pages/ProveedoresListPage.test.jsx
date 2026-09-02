import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProveedoresListPage from './ProveedoresListPage.jsx'

const provider = {
  id: '30000000-0000-0000-0000-000000000001',
  nombre_razon_social: 'Servicios del Centro',
  matricula: 'MP 1234',
  telefono: '+5493564555555',
  activo: true,
  especialidades: [
    { id: '10000000-0000-0000-0000-000000000001', nombre: 'plomería' },
  ],
  coberturas: [
    {
      id: '40000000-0000-0000-0000-000000000001',
      provincia: 'Córdoba',
      localidad: 'San Francisco',
      cubre_toda_localidad: true,
      barrios: [],
    },
  ],
}

function jsonResponse(body, status = 200) {
  return {
    headers: { get: () => 'application/json' },
    json: async () => body,
    ok: status >= 200 && status < 300,
    status,
  }
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/proveedores']}>
      <Routes>
        <Route path="proveedores" element={<ProveedoresListPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('listado de proveedores', () => {
  it('no envía un filtro por barrio sin provincia y localidad', async () => {
    const user = userEvent.setup()
    let providerRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/especialidades')) return jsonResponse([])
      if (url.includes('/proveedores?')) {
        providerRequests += 1
        return jsonResponse({ items: [provider], page: 1, page_size: 10, total: 1, total_pages: 1 })
      }
      throw new Error(`Solicitud inesperada: ${url}`)
    })
    renderPage()

    expect(await screen.findByText(provider.nombre_razon_social)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Barrio'), 'Centro')
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }))

    expect(screen.getByText('Seleccioná provincia y localidad para filtrar por barrio.')).toBeInTheDocument()
    expect(providerRequests).toBe(1)
  })

  it('oculta los resultados anteriores si la nueva búsqueda falla', async () => {
    const user = userEvent.setup()
    let providerRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/especialidades')) return jsonResponse([])
      if (url.includes('/proveedores?')) {
        providerRequests += 1
        if (providerRequests === 1) {
          return jsonResponse({ items: [provider], page: 1, page_size: 10, total: 1, total_pages: 1 })
        }
        return jsonResponse({ detail: 'No pudimos actualizar el listado.' }, 500)
      }
      throw new Error(`Solicitud inesperada: ${url}`)
    })
    renderPage()

    expect(await screen.findByText(provider.nombre_razon_social)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Provincia'), 'Córdoba')
    await user.type(screen.getByLabelText('Localidad'), 'San Francisco')
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }))

    expect(await screen.findByText('No pudimos actualizar el listado.')).toBeInTheDocument()
    expect(screen.queryByText(provider.nombre_razon_social)).not.toBeInTheDocument()
  })
})
