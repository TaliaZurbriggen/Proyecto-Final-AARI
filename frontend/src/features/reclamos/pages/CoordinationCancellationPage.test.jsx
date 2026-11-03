import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CoordinationCancellationPage from './CoordinationCancellationPage.jsx'
import { cancelCoordination, getCoordinationCancellation } from '../api/coordinationCancellationsApi.js'

vi.mock('../api/coordinationCancellationsApi.js', () => ({ cancelCoordination: vi.fn(), getCoordinationCancellation: vi.fn() }))

const view = { reclamo_id: 'claim-1', numero: 1, descripcion: 'Problema sintético de cañerías',
  estado: 'Proveedor seleccionado', updated_at: '2026-11-03T12:00:00Z', eleccion_id: 'choice-1',
  puede_cancelar: true, motivo_bloqueo: null, historial: [] }
const saved = { id: 'cancel-1', eleccion_id: 'choice-1', eleccion_nueva_id: 'choice-2',
  actor_nombre: 'Responsable de prueba', creada_en: '2026-11-03T12:05:00Z',
  estado_resultante: 'Pendiente de respuesta del responsable' }

function setup(ownerView = false) {
  const role = ownerView ? 'propietario' : 'inquilino'
  render(<MemoryRouter initialEntries={[`/${role}/reclamos/claim-1/cancelar-coordinacion`]}><Routes>
    <Route path={`${role}/reclamos/:reclamoId/cancelar-coordinacion`} element={<CoordinationCancellationPage ownerView={ownerView} />} />
    <Route path={`${role}/reclamos/:reclamoId/tipo-proveedor`} element={<h1>Elección de tipo de proveedor</h1>} />
  </Routes></MemoryRouter>)
  return userEvent.setup()
}

beforeEach(() => { vi.resetAllMocks(); getCoordinationCancellation.mockResolvedValue(view); cancelCoordination.mockResolvedValue(saved) })

describe('Cancelación y reelección HU24', () => {
  it.each([false, true])('confirma explícitamente y vuelve a la elección del rol (%s)', async (owner) => {
    const user = setup(owner)
    const button = await screen.findByRole('button', { name: 'Sí, cancelar y volver a elegir' })
    expect(screen.getByText(/Conservaremos los presupuestos/)).toBeInTheDocument()
    expect(cancelCoordination).not.toHaveBeenCalled()
    await user.click(button)
    expect(await screen.findByRole('heading', { name: 'Coordinación cancelada' })).toHaveFocus()
    expect(cancelCoordination).toHaveBeenCalledWith('claim-1', { request_id: expect.any(String),
      eleccion_id: 'choice-1', expected_updated_at: view.updated_at, confirmar: true })
    expect(cancelCoordination).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('link', { name: 'Volver a elegir proveedor' }))
    expect(await screen.findByRole('heading', { name: 'Elección de tipo de proveedor' })).toBeInTheDocument()
  })

  it('permite decir No sin escribir ni cancelar el intento', async () => {
    const user = setup()
    await user.click(await screen.findByRole('link', { name: 'No, continuar con este intento' }))
    expect(await screen.findByRole('heading', { name: 'Elección de tipo de proveedor' })).toBeInTheDocument()
    expect(cancelCoordination).not.toHaveBeenCalled()
  })

  it('bloquea una visita programada y muestra el motivo del servidor', async () => {
    getCoordinationCancellation.mockResolvedValue({ ...view, estado: 'Visita programada', puede_cancelar: false,
      motivo_bloqueo: 'La visita ya está programada. Esta etapa no admite cancelar y reelegir.' })
    setup()
    expect(await screen.findByRole('heading', { name: 'Cancelación no disponible' })).toBeInTheDocument()
    expect(screen.getByText(/La visita ya está programada/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Sí, cancelar/ })).not.toBeInTheDocument()
    expect(cancelCoordination).not.toHaveBeenCalled()
  })

  it.each([0, 500, 503])('conserva el identificador ante una respuesta incierta (%s)', async (status) => {
    cancelCoordination.mockRejectedValueOnce(Object.assign(new Error('Error de conexión.'), { status })).mockResolvedValueOnce(saved)
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Sí, cancelar y volver a elegir' }))
    expect(await screen.findByText(/Reintentá la misma cancelación/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'No, continuar con este intento' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reintentar cancelación' }))
    await screen.findByRole('heading', { name: 'Coordinación cancelada' })
    expect(cancelCoordination.mock.calls[0][1]).toEqual(cancelCoordination.mock.calls[1][1])
  })

  it('conserva la confirmación si el GET posterior falla y reintenta sólo la consulta', async () => {
    getCoordinationCancellation.mockResolvedValueOnce(view).mockRejectedValueOnce(new Error('Consulta interrumpida.')).mockResolvedValue(view)
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Sí, cancelar y volver a elegir' }))
    expect(await screen.findByText(/La cancelación está guardada/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Coordinación cancelada' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Sí, cancelar/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reintentar consulta' }))
    await waitFor(() => expect(getCoordinationCancellation).toHaveBeenCalledTimes(3))
    expect(cancelCoordination).toHaveBeenCalledTimes(1)
  })

  it('no duplica el POST con doble clic mientras está pendiente', async () => {
    let resolve
    cancelCoordination.mockImplementation(() => new Promise((done) => { resolve = done }))
    const user = setup()
    await user.dblClick(await screen.findByRole('button', { name: 'Sí, cancelar y volver a elegir' }))
    expect(screen.getByRole('button', { name: 'Cancelando…' })).toBeDisabled()
    expect(cancelCoordination).toHaveBeenCalledTimes(1)
    await act(async () => resolve(saved))
    expect(await screen.findByRole('heading', { name: 'Coordinación cancelada' })).toBeInTheDocument()
  })

  it('devuelve el foco al reintento cuando la consulta vuelve a fallar', async () => {
    getCoordinationCancellation.mockResolvedValueOnce(view).mockRejectedValue(new Error('Consulta interrumpida.'))
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Sí, cancelar y volver a elegir' }))
    await user.click(await screen.findByRole('button', { name: 'Reintentar consulta' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reintentar consulta' })).toHaveFocus())
    expect(cancelCoordination).toHaveBeenCalledTimes(1)
  })

  it('retira acciones obsoletas después de un conflicto y recarga', async () => {
    cancelCoordination.mockRejectedValue(Object.assign(new Error('La visita cambió.'), { status: 409 }))
    getCoordinationCancellation.mockResolvedValueOnce(view).mockResolvedValue({ ...view,
      estado: 'Visita programada', puede_cancelar: false, motivo_bloqueo: 'La visita ya está programada.' })
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Sí, cancelar y volver a elegir' }))
    expect(await screen.findByRole('heading', { name: 'Cancelación no disponible' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Sí, cancelar/ })).not.toBeInTheDocument()
  })

  it('conserva visibles los datos históricos de cancelaciones anteriores', async () => {
    getCoordinationCancellation.mockResolvedValue({ ...view, historial: [{ id: 'cancel-old',
      timestamp: saved.creada_en, actor_nombre: 'Responsable anterior', proveedor: 'Servicio de prueba' }] })
    setup()
    expect(await screen.findByRole('heading', { name: 'Cancelaciones anteriores' })).toBeInTheDocument()
    expect(screen.getByText(/Responsable anterior/)).toBeInTheDocument()
    expect(screen.getByText('Proveedor: Servicio de prueba')).toBeInTheDocument()
  })
})
