import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BudgetComparisonPage from './BudgetComparisonPage.jsx'
import { getQuoteSelection, selectQuote } from '../api/quoteSelectionsApi.js'

vi.mock('../api/quoteSelectionsApi.js', () => ({ getQuoteSelection: vi.fn(), selectQuote: vi.fn() }))

const quote = { id: 'quote-1', solicitud_id: 'request-1', proveedor: 'Servicio Uno',
  especialidades: ['Plomería'], zonas: [{ localidad: 'Ciudad', provincia: 'Córdoba' }],
  monto: '10000.50', moneda: 'ARS', tipo_importe: 'minimo', descripcion: 'Reparación con materiales', puede_elegir: true }
const view = { reclamo_id: 'claim-1', numero: 1, descripcion: 'Problema de cañerías',
  estado: 'Pendiente de asignación', updated_at: '2026-10-29T12:00:00Z', ronda_id: 'round-1',
  puede_elegir: true, puede_cargar_propio: true, recepcion_abierta: true, decision: null, items: [quote] }
const saved = { id: 'selection-1', modalidad: 'fidelizado', estado_resultante: 'Proveedor seleccionado',
  proveedor_nombre: 'Servicio Uno',
  decidido_en: '2026-10-29T12:05:00Z', actor_nombre: 'Persona de prueba',
  monto: '10000.50', moneda: 'ARS', tipo_importe: 'minimo' }

function setup(options = {}) {
  render(<MemoryRouter initialEntries={['/inquilino/reclamos/claim-1/presupuestos']}><Routes>
    <Route path="inquilino/reclamos/:reclamoId/presupuestos" element={<BudgetComparisonPage {...options} />} />
  </Routes></MemoryRouter>)
  return userEvent.setup()
}

beforeEach(() => { vi.resetAllMocks(); getQuoteSelection.mockResolvedValue(view); selectQuote.mockResolvedValue(saved) })

describe('Comparación y selección HU20', () => {
  it('muestra mínimo, moneda, alcance y datos del proveedor sin elegir automáticamente', async () => {
    setup()
    expect(await screen.findByRole('heading', { name: 'Servicio Uno' })).toBeInTheDocument()
    expect(screen.getByText(/Desde .*10.000,50.*ARS/)).toBeInTheDocument()
    expect(screen.getByText('Plomería')).toBeInTheDocument()
    expect(screen.getByText('Ciudad, Córdoba')).toBeInTheDocument()
    expect(selectQuote).not.toHaveBeenCalled()
  })

  it('pide confirmación, transmite referencias y conserva la distinción de importe mínimo', async () => {
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Revisar propuesta de Servicio Uno' }))
    expect(screen.getByRole('heading', { name: 'Revisá tu elección antes de confirmar' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Revisá tu elección antes de confirmar' })).toHaveFocus()
    expect(selectQuote).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Confirmar elección' }))
    expect(await screen.findByRole('heading', { name: 'Presupuesto seleccionado' })).toBeInTheDocument()
    expect(selectQuote).toHaveBeenCalledTimes(1)
    expect(selectQuote).toHaveBeenCalledWith('claim-1', { request_id: expect.any(String), ronda_id: 'round-1',
      expected_updated_at: view.updated_at, modalidad: 'fidelizado', presupuesto_id: 'quote-1' })
    expect(screen.getByText(/Elegiste un importe mínimo/)).toBeInTheDocument()
  })

  it('permite volver antes de confirmar sin registrar nada', async () => {
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Revisar propuesta de Servicio Uno' }))
    await user.click(screen.getByRole('button', { name: 'Volver a comparar' }))
    expect(screen.getByRole('button', { name: 'Revisar propuesta de Servicio Uno' })).toBeInTheDocument()
    expect(selectQuote).not.toHaveBeenCalled()
  })

  it('no inventa un presupuesto cuando no hay respuestas', async () => {
    getQuoteSelection.mockResolvedValue({ ...view, items: [] })
    setup()
    expect(await screen.findByText('Todavía no hay presupuestos disponibles')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Revisar propuesta de/ })).not.toBeInTheDocument()
    expect(selectQuote).not.toHaveBeenCalled()
  })

  it('enlaza el formulario HU18 sin registrar ni cerrar la ronda al abrirlo', async () => {
    setup()
    expect(await screen.findByRole('link', { name: 'Quiero cargar un proveedor propio' }))
      .toHaveAttribute('href', '/inquilino/reclamos/claim-1/proveedor-externo')
    expect(screen.getByText(/Abrir el formulario no modifica el reclamo ni cierra la recepción/)).toBeInTheDocument()
    expect(selectQuote).not.toHaveBeenCalled()
  })

  it.each([0, 500, 503])('reintenta una respuesta incierta (%s) con el mismo identificador', async (status) => {
    selectQuote.mockRejectedValueOnce(Object.assign(new Error('No pudimos confirmar la conexión.'), { status })).mockResolvedValueOnce(saved)
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Revisar propuesta de Servicio Uno' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar elección' }))
    expect(await screen.findByText(/conservamos el identificador/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Volver a comparar' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Confirmar elección' }))
    await screen.findByRole('heading', { name: 'Presupuesto seleccionado' })
    expect(selectQuote.mock.calls[0][1]).toEqual(selectQuote.mock.calls[1][1])
  })

  it('actualiza la vista ante un conflicto y no confirma la propuesta vieja', async () => {
    selectQuote.mockRejectedValue(Object.assign(new Error('La etapa cambió.'), { status: 409 }))
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Revisar propuesta de Servicio Uno' }))
    getQuoteSelection.mockResolvedValue({ ...view, puede_elegir: false })
    await user.click(screen.getByRole('button', { name: 'Confirmar elección' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Revisar propuesta de Servicio Uno' })).toBeDisabled())
    expect(screen.queryByRole('button', { name: 'Confirmar elección' })).not.toBeInTheDocument()
  })

  it('carga una decisión persistida como sólo lectura después de recargar', async () => {
    getQuoteSelection.mockResolvedValue({ ...view, decision: saved, puede_elegir: false })
    setup()
    expect(await screen.findByRole('heading', { name: 'Presupuesto seleccionado' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Revisar propuesta/ })).not.toBeInTheDocument()
  })

  it('ofrece recuperación de un error de carga', async () => {
    getQuoteSelection.mockRejectedValueOnce(new Error('No pudimos cargar.')).mockResolvedValueOnce(view)
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Volver a intentar' }))
    expect(await screen.findByRole('heading', { name: 'Servicio Uno' })).toBeInTheDocument()
  })

  it('bloquea confirmaciones simultáneas mientras guarda', async () => {
    let complete
    selectQuote.mockImplementation(() => new Promise((resolve) => { complete = resolve }))
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Revisar propuesta de Servicio Uno' }))
    await user.dblClick(screen.getByRole('button', { name: 'Confirmar elección' }))
    expect(selectQuote).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled()
    await act(async () => complete(saved))
    expect(await screen.findByRole('heading', { name: 'Presupuesto seleccionado' })).toBeInTheDocument()
  })

  it.each([false, true])('conserva el guardado si falla la recarga y reintenta sólo la consulta (propietario=%s)', async (ownerView) => {
    getQuoteSelection.mockResolvedValueOnce(view)
      .mockRejectedValueOnce(new Error('No pudimos actualizar los datos.'))
      .mockResolvedValueOnce({ ...view, estado: 'Proveedor seleccionado', decision: saved, puede_elegir: false })
    const user = setup({ ownerView })
    await user.click(await screen.findByRole('button', { name: 'Revisar propuesta de Servicio Uno' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar elección' }))
    const retry = await screen.findByRole('button', { name: 'Reintentar actualización' })
    const confirmation = screen.getByRole('region', { name: 'Selección registrada' })
    expect(within(confirmation).getByRole('heading', { name: 'Presupuesto seleccionado' })).toBeInTheDocument()
    expect(within(confirmation).getByRole('heading', { name: 'Servicio Uno' })).toBeInTheDocument()
    expect(within(confirmation).getByText(/Desde .*10.000,50.*ARS/)).toBeInTheDocument()
    expect(screen.getByText(/La selección está guardada, pero no pudimos actualizar el estado del reclamo/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirmar elección' })).not.toBeInTheDocument()
    expect(selectQuote).toHaveBeenCalledTimes(1)
    await user.click(retry)
    const claim = await screen.findByRole('region', { name: 'Reclamo' })
    expect(within(claim).getByText('Proveedor seleccionado')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Selección registrada' })).toBeInTheDocument()
    expect(getQuoteSelection).toHaveBeenCalledTimes(3)
    expect(selectQuote).toHaveBeenCalledTimes(1)
  })

  it.each([false, true])('distingue el estado actual del reclamo de la selección histórica (propietario=%s)', async (ownerView) => {
    getQuoteSelection.mockResolvedValue({ ...view, estado: 'Resuelto', decision: saved, puede_elegir: false })
    setup({ ownerView })
    const claim = await screen.findByRole('region', { name: 'Reclamo' })
    expect(within(claim).getByText('Resuelto')).toBeInTheDocument()
    expect(within(claim).queryByText('Proveedor seleccionado')).not.toBeInTheDocument()
    const confirmation = screen.getByRole('region', { name: 'Selección registrada' })
    expect(within(confirmation).getByRole('heading', { name: 'Servicio Uno' })).toBeInTheDocument()
    expect(within(confirmation).getByText('Estado al confirmar la selección: Proveedor seleccionado')).toBeInTheDocument()
    expect(selectQuote).not.toHaveBeenCalled()
  })

  it('mantiene visible la confirmación mientras consulta el estado vigente', async () => {
    let completeReload
    getQuoteSelection.mockResolvedValueOnce(view).mockImplementationOnce(() => new Promise((resolve) => { completeReload = resolve }))
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Revisar propuesta de Servicio Uno' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar elección' }))
    await waitFor(() => expect(getQuoteSelection).toHaveBeenCalledTimes(2))
    expect(screen.getByRole('heading', { name: 'Presupuesto seleccionado' })).toHaveFocus()
    expect(screen.getByRole('region', { name: 'Selección registrada' })).toBeInTheDocument()
    expect(screen.getByText('Actualizando estado del reclamo')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Reclamo' })).not.toBeInTheDocument()
    await act(async () => completeReload({ ...view, estado: 'Resuelto', decision: saved, puede_elegir: false }))
    expect(within(screen.getByRole('region', { name: 'Reclamo' })).getByText('Resuelto')).toBeInTheDocument()
    expect(selectQuote).toHaveBeenCalledTimes(1)
  })
})
