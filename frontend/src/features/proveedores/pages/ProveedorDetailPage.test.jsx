import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProveedorDetailPage from './ProveedorDetailPage.jsx'

const provider = {
  id: '30000000-0000-0000-0000-000000000001',
  nombre_razon_social: 'Servicios del Centro',
  matricula: 'MP 1234',
  telefono: '+5493564555555',
  activo: true,
  hora_inicio: '08:00:00',
  hora_fin: '17:30:00',
  especialidades: [
    { id: '10000000-0000-0000-0000-000000000001', nombre: 'plomería' },
  ],
  coberturas: [
    {
      id: '40000000-0000-0000-0000-000000000001',
      provincia: 'Córdoba',
      localidad: 'San Francisco',
      cubre_toda_localidad: false,
      barrios: ['Centro', 'La Milka'],
    },
  ],
  created_at: '2026-08-29T12:00:00Z',
  updated_at: '2026-08-29T12:00:00Z',
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

describe('detalle de proveedor', () => {
  it('muestra datos operativos y permite desactivarlo conservando el registro', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(provider))
      .mockResolvedValueOnce(jsonResponse({ ...provider, activo: false }))
    render(
      <MemoryRouter initialEntries={[`/proveedores/${provider.id}`]}>
        <Routes>
          <Route path="proveedores/:proveedorId" element={<ProveedorDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: provider.nombre_razon_social })).toBeInTheDocument()
    expect(screen.getByText('08:00 a 17:30')).toBeInTheDocument()
    expect(screen.getByText('Centro')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Desactivar' }))
    await user.click(screen.getByRole('button', { name: 'Desactivar proveedor' }))

    expect(await screen.findByText(/quedó inactivo/i)).toBeInTheDocument()
    expect(fetchMock.mock.calls[1][1].method).toBe('PATCH')
    expect(screen.getByText('Inactivo')).toBeInTheDocument()
  })
})
