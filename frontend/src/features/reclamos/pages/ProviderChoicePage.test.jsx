import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProviderChoicePage from './ProviderChoicePage.jsx'
import OwnerExpenseDecisionPage from './OwnerExpenseDecisionPage.jsx'

const claim = { reclamo_id: '1c604bda-c38b-4621-b6cf-1458ce7fcdae', numero: 26,
  descripcion: 'Problema sintético para elegir cómo continuar.', estado: 'Pendiente de respuesta del responsable',
  propiedad: { direccion: 'Unidad Sintética', localidad: 'Localidad de prueba' },
  actor_tipo: 'inquilino', solicitud_id: 'f2f08798-a123-4456-8888-a4d3384d1111',
  solicitado_en: '2026-10-18T10:00:00Z', respuesta_vence_en: '2026-10-21T10:00:00Z',
  updated_at: '2026-10-18T10:00:00Z', puede_elegir: true, decision: null }
const result = (choice) => ({ reclamo_id: claim.reclamo_id, solicitud_id: claim.solicitud_id,
  tipo_proveedor: choice, estado: choice === 'fidelizado' ? 'Pendiente de asignación' : 'Pendiente de datos de proveedor propio',
  siguiente_paso: choice === 'fidelizado' ? 'solicitar_presupuestos' : 'registrar_proveedor_propio',
  actor_nombre: 'Actor Sintético', decidido_en: '2026-10-18T11:00:00Z' })
const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function show(owner = false, initial) {
  const role = owner ? 'propietario' : 'inquilino'
  render(<MemoryRouter initialEntries={[initial || `/${role}/reclamos/${claim.reclamo_id}/tipo-proveedor`]}>
    <Routes>
      <Route path={`/${role}/reclamos/:reclamoId/tipo-proveedor`} element={<ProviderChoicePage ownerView={owner} />} />
      <Route path="/propietario/reclamos/:reclamoId/autorizar" element={<OwnerExpenseDecisionPage />} />
    </Routes>
  </MemoryRouter>)
}
afterEach(() => vi.restoreAllMocks())

describe('HU17 elección de proveedor', () => {
  it('muestra dos opciones explícitas, contexto y plazo, accesibles por teclado', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(claim))
    show()
    const own = await screen.findByRole('button', { name: 'Elegir proveedor propio' })
    expect(screen.getByText(claim.descripcion)).toBeInTheDocument()
    expect(screen.getByText(/a las 72 horas/)).toBeInTheDocument()
    const user = userEvent.setup()
    await user.tab()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Elegir proveedor fidelizado' })).toHaveFocus()
    await user.tab()
    expect(own).toHaveFocus()
  })

  it.each(['fidelizado', 'propio'])('guarda %s y no promete acciones de HU18/HU19 ya realizadas', async (choice) => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, opts) =>
      Promise.resolve(json(opts?.method === 'POST' ? result(choice) : claim)))
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: `Elegir proveedor ${choice}` }))
    expect(await screen.findByRole('heading', { name: `Elección registrada: proveedor ${choice}` })).toBeInTheDocument()
    expect(screen.getByText(choice === 'propio' ? /Todavía no se registró el contacto/ : /Todavía no se envió ninguna solicitud/)).toBeInTheDocument()
    const [, options] = fetch.mock.calls.find(([, opts]) => opts?.method === 'POST')
    expect(JSON.parse(options.body)).toEqual({ request_id: expect.any(String), solicitud_id: claim.solicitud_id,
      expected_updated_at: claim.updated_at, tipo_proveedor: choice })
    expect(screen.queryByRole('button', { name: /Elegir proveedor/ })).not.toBeInTheDocument()
  })

  it('conserva UUID y elección ante respuesta perdida', async () => {
    let posts = 0
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, opts) => {
      if (opts?.method !== 'POST') return Promise.resolve(json(claim))
      return ++posts === 1 ? Promise.reject(new TypeError('network')) : Promise.resolve(json(result('propio')))
    })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Elegir proveedor propio' }))
    await screen.findByText(/No pudimos conectarnos/)
    expect(screen.getByRole('button', { name: 'Elegir proveedor fidelizado' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Elegir proveedor propio' }))
    await screen.findByText('Elección registrada: proveedor propio')
    const calls = fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST')
    expect(calls[0][1].body).toEqual(calls[1][1].body)
  })

  it('bloquea doble envío durante guardado', async () => {
    let finish
    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, opts) => opts?.method === 'POST'
      ? new Promise((resolve) => { finish = resolve }) : Promise.resolve(json(claim)))
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Elegir proveedor fidelizado' }))
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Elegir proveedor propio' })).toBeDisabled()
    await act(async () => finish(json(result('fidelizado'))))
    await screen.findByText('Elección registrada: proveedor fidelizado')
  })

  it('recarga ante conflicto y no permite elegir si venció', async () => {
    let conflict = false
    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, opts) => {
      if (opts?.method === 'POST') {
        conflict = true
        return Promise.resolve(json({ detail: { message: 'El reclamo cambió.' } }, 409))
      }
      return Promise.resolve(json(conflict ? { ...claim, puede_elegir: false, estado: 'Pendiente de respuesta - vencido' } : claim))
    })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Elegir proveedor propio' }))
    await screen.findByText(/Esta solicitud ya no admite/)
    expect(screen.queryByRole('button', { name: /Elegir proveedor/ })).not.toBeInTheDocument()
  })

  it('recupera una decisión persistida al recargar', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...claim, puede_elegir: false, decision: result('propio') }))
    show(true)
    await screen.findByText('Elección registrada: proveedor propio')
    expect(screen.getByRole('link', { name: 'Volver a autorizaciones' })).toHaveAttribute('href', '/propietario/reclamos')
  })

  it('muestra errores de acceso sin decisiones', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: { message: 'Sin acceso a esta elección.' } }, 404))
    show()
    await screen.findByText('Sin acceso a esta elección.')
    expect(screen.queryByRole('button', { name: /Elegir proveedor/ })).not.toBeInTheDocument()
  })

  it('enlaza de verdad autorizar HU16 → cargar HU17 → elegir proveedor', async () => {
    const expense = { ...claim, id: claim.reclamo_id, fundamento: 'Extraordinario.', puede_decidir: true,
      historial: [], decision: null }
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((url, opts) => {
      if (url.endsWith('/autorizar')) return Promise.resolve(json({ decision: 'autorizar', siguiente_paso: 'eleccion_proveedor',
        propietario_nombre: 'Titular Sintético', decidido_en: '2026-10-18T11:00:00Z', estado: 'Autorizado' }))
      if (url.endsWith('/autorizacion')) return Promise.resolve(json(expense))
      return Promise.resolve(json(opts?.method === 'POST' ? result('fidelizado') : { ...claim, actor_tipo: 'propietario', estado: 'Autorizado' }))
    })
    show(true, `/propietario/reclamos/${claim.reclamo_id}/autorizar`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Autorizar intervención' }))
    await user.click(await screen.findByRole('button', { name: 'Elegir proveedor fidelizado' }))
    await screen.findByText('Elección registrada: proveedor fidelizado')
    expect(fetch.mock.calls.some(([url, opts]) => url.endsWith('/tipo-proveedor') && opts?.method === 'POST')).toBe(true)
  })
})
