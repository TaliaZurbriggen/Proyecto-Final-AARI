import { act, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ReclamoDetailPage from './ReclamoDetailPage.jsx'
import ReclamosListPage from './ReclamosListPage.jsx'

const claim = {
  id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
  numero: 12,
  descripcion: 'La canilla de la cocina pierde agua desde ayer.',
  urgencia: 'media',
  estado: 'Clasificado',
  creado_en: '2026-09-10T13:00:00Z',
  updated_at: '2026-09-10T14:00:00Z',
  propiedad: {
    id: '4fd4e07c-6259-45f1-b8b3-6a607235cc89',
    direccion: 'Av. San Martín 120',
    provincia: 'Santa Fe',
    localidad: 'San Francisco',
    barrio: 'Centro',
    tipo: 'departamento',
    piso: 0,
    numero: 'B',
  },
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('seguimiento de reclamos del inquilino', () => {
  it('lista el estado actual y permite abrir el seguimiento', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ items: [claim] }))

    render(
      <MemoryRouter initialEntries={['/inquilino/reclamos']}>
        <Routes>
          <Route path="inquilino/reclamos" element={<ReclamosListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Reclamo #000012')).toBeInTheDocument()
    expect(screen.getByText('Clasificado')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Ver seguimiento/ })).toHaveAttribute(
      'href',
      `/inquilino/reclamos/${claim.id}`,
    )
  })

  it('explica el estado vacío y ofrece crear el primer reclamo', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ items: [] }))

    render(
      <MemoryRouter initialEntries={['/inquilino/reclamos']}>
        <Routes>
          <Route path="inquilino/reclamos" element={<ReclamosListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Todavía no tenés reclamos')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Crear el primero/ })).toBeInTheDocument()
  })

  it('muestra el estado actual y el historial en orden visual descendente', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        ...claim,
        historial: [
          {
            estado_anterior: null,
            estado_nuevo: 'Recibido',
            origen: 'inquilino',
            timestamp: '2026-09-10T13:00:00Z',
          },
          {
            estado_anterior: 'Recibido',
            estado_nuevo: 'Clasificado',
            origen: 'agente',
            timestamp: '2026-09-10T14:00:00Z',
          },
        ],
      }),
    )

    render(
      <MemoryRouter initialEntries={[`/inquilino/reclamos/${claim.id}`]}>
        <Routes>
          <Route
            path="inquilino/reclamos/:reclamoId"
            element={<ReclamoDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Reclamo #000012' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Clasificado' })).toBeInTheDocument()
    const timeline = screen.getByRole('list')
    expect(timeline).toHaveTextContent('Clasificado')
    expect(timeline).toHaveTextContent('Recibido')
  })

  it('actualiza el listado automáticamente cada 30 segundos', async () => {
    vi.useFakeTimers()
    const updatedClaim = { ...claim, estado: 'Escalado' }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ items: [claim] }))
      .mockResolvedValueOnce(jsonResponse({ items: [updatedClaim] }))

    const view = render(
      <MemoryRouter initialEntries={['/inquilino/reclamos']}>
        <Routes>
          <Route path="inquilino/reclamos" element={<ReclamosListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await act(async () => vi.advanceTimersByTimeAsync(0))
    expect(screen.getByText('Clasificado')).toBeInTheDocument()

    await act(async () => vi.advanceTimersByTimeAsync(30_000))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(screen.getByText('Escalado')).toBeInTheDocument()

    const latestSignal = fetchMock.mock.calls[1][1].signal
    view.unmount()
    expect(latestSignal.aborted).toBe(true)
  })

  it('actualiza el detalle automáticamente cada 30 segundos', async () => {
    vi.useFakeTimers()
    const initialDetail = {
      ...claim,
      historial: [{
        estado_anterior: null,
        estado_nuevo: 'Recibido',
        origen: 'inquilino',
        timestamp: '2026-09-10T13:00:00Z',
      }],
    }
    const updatedDetail = {
      ...initialDetail,
      estado: 'Escalado',
      historial: [
        ...initialDetail.historial,
        {
          estado_anterior: 'Clasificado',
          estado_nuevo: 'Escalado',
          origen: 'operador',
          timestamp: '2026-09-10T15:00:00Z',
        },
      ],
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(initialDetail))
      .mockResolvedValueOnce(jsonResponse(updatedDetail))

    render(
      <MemoryRouter initialEntries={[`/inquilino/reclamos/${claim.id}`]}>
        <Routes>
          <Route
            path="inquilino/reclamos/:reclamoId"
            element={<ReclamoDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    await act(async () => vi.advanceTimersByTimeAsync(0))
    expect(screen.getByRole('heading', { name: 'Clasificado' })).toBeInTheDocument()

    await act(async () => vi.advanceTimersByTimeAsync(30_000))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('heading', { name: 'Escalado' })).toBeInTheDocument()
  })
})
