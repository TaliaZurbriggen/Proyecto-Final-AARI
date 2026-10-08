import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AdminHomePage from './AdminHomePage.jsx'

const summary = {
  consultado_en: '2026-10-05T15:30:00Z',
  propietarios: { total: 48 }, propiedades: { total: 62 }, inquilinos: { total: 58 },
  proveedores: { total: 14, activos: 12 }, operadores: { total: 3, activos: 2 },
  reclamos: { activos: 24, pendientes_clasificacion: 4 },
}
const jsonResponse = (body, status = 200) => new Response(JSON.stringify(body), {
  headers: { 'Content-Type': 'application/json' }, status,
})
const renderHome = () => render(<MemoryRouter><AdminHomePage /></MemoryRouter>)
afterEach(() => vi.unstubAllGlobals())

describe('Home administrativo operativo', () => {
  it('consulta datos reales, distingue los subconjuntos y muestra la hora argentina', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(summary))
    vi.stubGlobal('fetch', fetchMock)
    renderHome()
    expect(await screen.findByText('24')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('12 activos')).toBeInTheDocument()
    expect(screen.getByText('2 activos')).toBeInTheDocument()
    expect(screen.getByText('Incluye los pendientes de clasificación.')).toBeInTheDocument()
    expect(screen.getByText(/Última consulta/)).toHaveTextContent('12:30')
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/admin/resumen'),
      expect.objectContaining({ credentials: 'include', signal: expect.any(AbortSignal) }))
  })

  it('mantiene accesos válidos a los listados, contratos e historial por propiedad', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(summary)))
    renderHome()
    await screen.findByText('24')
    for (const label of ['Propietarios', 'Propiedades', 'Inquilinos', 'Proveedores', 'Operadores']) {
      expect(screen.getByRole('link', { name: new RegExp(label) })).toHaveAttribute('href', `/${label.toLowerCase()}`)
    }
    expect(screen.getByRole('link', { name: /Contratos de alquiler/ })).toHaveAttribute('href', '/contratos')
    expect(screen.getByRole('link', { name: /Historial de reclamos/ })).toHaveAttribute('href', '/propiedades')
    expect(screen.getByRole('link', { name: 'Revisar casos' })).toHaveAttribute('href', '/escalados')
    expect(screen.queryByText(/se habilitará cuando se integre HU13/)).not.toBeInTheDocument()
  })

  it('conserva contexto y accesos mientras carga sin inventar ceros', async () => {
    let resolve
    vi.stubGlobal('fetch', vi.fn(() => new Promise((done) => { resolve = done })))
    renderHome()
    expect(screen.getByRole('status', { name: 'Cargando resumen operativo' })).toBeInTheDocument()
    expect(screen.getAllByText('—')).toHaveLength(7)
    expect(screen.queryByText('0')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Actualizar' })).toBeDisabled()
    expect(screen.getByRole('link', { name: /Propietarios/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Revisar casos' })).toHaveAttribute('href', '/escalados')
    await act(async () => resolve(jsonResponse(summary)))
    expect(await screen.findByText('24')).toBeInTheDocument()
  })

  it('muestra ceros y una invitación a comenzar solo cuando la base está vacía', async () => {
    const empty = structuredClone(summary)
    for (const key of ['propietarios', 'propiedades', 'inquilinos', 'proveedores', 'operadores']) {
      empty[key].total = 0
      if ('activos' in empty[key]) empty[key].activos = 0
    }
    empty.reclamos = { activos: 0, pendientes_clasificacion: 0 }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(empty)))
    renderHome()
    expect(await screen.findByRole('heading', { name: 'Tu base de trabajo está lista para empezar' })).toBeInTheDocument()
    expect(screen.getAllByText('0')).toHaveLength(7)
    expect(screen.getByText('Sin pendientes')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Revisar casos' })).toHaveAttribute('href', '/escalados')
  })

  it('permite reintentar después de un fallo sin falsear los datos', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: { message: 'No pudimos obtener el resumen.' } }, 503))
      .mockResolvedValueOnce(jsonResponse(summary))
    vi.stubGlobal('fetch', fetchMock)
    renderHome()
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos obtener el resumen.')
    expect(screen.getAllByText('—')).toHaveLength(7)
    expect(screen.queryByText('0')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Revisar casos' })).toHaveAttribute('href', '/escalados')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Actualizar' }))
    expect(await screen.findByText('24')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('retira los resultados anteriores cuando falla una nueva consulta', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(jsonResponse(summary))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Conexión no disponible.' }, 503)))
    renderHome()
    await screen.findByText('24')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Actualizar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Conexión no disponible.')
    expect(screen.queryByText('24')).not.toBeInTheDocument()
    expect(screen.queryByText('48')).not.toBeInTheDocument()
    expect(screen.queryByText('12 activos')).not.toBeInTheDocument()
    expect(screen.getAllByText('—')).toHaveLength(7)
  })

  it('rechaza un resumen incompleto y conserva los enlaces', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ propietarios: { total: 1 } })))
    renderHome()
    expect(await screen.findByRole('alert')).toHaveTextContent('El resumen recibido está incompleto.')
    expect(within(screen.getByRole('region', { name: 'Contratos e historial' })).getAllByRole('link')).toHaveLength(2)
  })

  it('aborta al salir y no actualiza una pantalla nueva con una respuesta atrasada', async () => {
    let resolveFirst
    let firstSignal
    const fresh = structuredClone(summary)
    fresh.reclamos.activos = 30
    const fetchMock = vi.fn()
      .mockImplementationOnce((_, options) => {
        firstSignal = options.signal
        return new Promise((resolve) => { resolveFirst = resolve })
      })
      .mockResolvedValueOnce(jsonResponse(fresh))
    vi.stubGlobal('fetch', fetchMock)
    const old = renderHome()
    old.unmount()
    expect(firstSignal.aborted).toBe(true)
    renderHome()
    await screen.findByText('30')
    await act(async () => resolveFirst(jsonResponse(summary)))
    await waitFor(() => expect(screen.queryByText('24')).not.toBeInTheDocument())
    expect(screen.getByText('30')).toBeInTheDocument()
  })
})
