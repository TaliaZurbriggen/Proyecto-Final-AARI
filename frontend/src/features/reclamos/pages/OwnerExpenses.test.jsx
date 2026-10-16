import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OwnerExpensesPage from './OwnerExpensesPage.jsx'
import OwnerExpenseDecisionPage from './OwnerExpenseDecisionPage.jsx'

const claim = {
  id: '1c604bda-c38b-4621-b6cf-1458ce7fcdae', numero: 26,
  descripcion: 'Problema sintético que requiere intervención.', estado: 'Pendiente de respuesta del responsable',
  fundamento: 'Gasto extraordinario según la clasificación informada.', puede_decidir: true,
  updated_at: '2026-10-15T10:00:00Z', solicitado_en: '2026-10-15T10:00:00Z',
  respuesta_vence_en: '2026-10-18T10:00:00Z', decision: null,
  propiedad: { direccion: 'Unidad Sintética 100', localidad: 'Localidad de prueba', provincia: 'Córdoba' },
  historial: [{ estado_nuevo: 'Pendiente de respuesta del responsable', timestamp: '2026-10-15T10:00:00Z', origen: 'agente' }],
}
const saved = (decision) => ({ reclamo_id: claim.id, decision,
  estado: decision === 'autorizar' ? 'Autorizado' : 'Rechazado por propietario',
  propietario_nombre: 'Titular Sintetico', decidido_en: '2026-10-15T11:00:00Z' })
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})
function show(detail = true) {
  render(<MemoryRouter initialEntries={[detail ? `/propietario/reclamos/${claim.id}/autorizar` : '/propietario/reclamos']}>
    <Routes><Route path="/propietario/reclamos/:reclamoId/autorizar" element={<OwnerExpenseDecisionPage />} />
      <Route path="/propietario/reclamos" element={<OwnerExpensesPage />} /></Routes>
  </MemoryRouter>)
}
afterEach(() => vi.restoreAllMocks())

describe('HU16 decisiones del propietario', () => {
  it('presenta contexto, clasificación, plazo y dos decisiones exclusivas', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(claim))
    show()
    expect(await screen.findByRole('heading', { name: 'Reclamo #000026' })).toBeInTheDocument()
    expect(screen.getByText(claim.descripcion)).toBeInTheDocument()
    expect(screen.getByText(claim.fundamento)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Autorizar intervención' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Rechazar intervención' })).toBeEnabled()
  })

  it('registra autorización sin afirmar entrega SMTP o implementación de HU17', async () => {
    const user = userEvent.setup()
    const post = saved('autorizar')
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) => Promise.resolve(
      json(options?.method === 'POST' ? post : claim)))
    show()
    await user.click(await screen.findByRole('button', { name: 'Autorizar intervención' }))
    expect(await screen.findByText(/todavía pendiente de HU17/)).toBeInTheDocument()
    const call = fetch.mock.calls.find(([, options]) => options?.method === 'POST')
    expect(call[0]).toContain(`/reclamos/${claim.id}/autorizar`)
    expect(JSON.parse(call[1].body)).toEqual({ request_id: expect.any(String), expected_updated_at: claim.updated_at })
    expect(screen.queryByRole('button', { name: 'Rechazar intervención' })).not.toBeInTheDocument()
  })

  it('confirma el rechazo y permite cancelar por teclado sin enviar', async () => {
    const user = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) =>
      Promise.resolve(json(options?.method === 'POST' ? saved('rechazar') : claim)))
    show()
    await user.click(await screen.findByRole('button', { name: 'Rechazar intervención' }))
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(fetch.mock.calls.filter(([, o]) => o?.method === 'POST')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Rechazar intervención' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar rechazo' }))
    expect(await screen.findByText(/El ciclo de esta solicitud quedó cerrado/)).toBeInTheDocument()
  })

  it('reutiliza el request_id si se pierde la respuesta e impide la acción opuesta', async () => {
    const user = userEvent.setup()
    let posts = 0
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) => {
      if (options?.method !== 'POST') return Promise.resolve(json(claim))
      posts++
      return posts === 1 ? Promise.reject(new TypeError('network')) : Promise.resolve(json(saved('autorizar')))
    })
    show()
    await user.click(await screen.findByRole('button', { name: 'Autorizar intervención' }))
    expect(await screen.findByText(/No pudimos conectarnos/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rechazar intervención' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Autorizar intervención' }))
    await screen.findByText(/todavía pendiente de HU17/)
    const calls = fetch.mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(calls).toHaveLength(2)
    expect(calls[0][1].body).toEqual(calls[1][1].body)
  })

  it('deshabilita ambas decisiones durante el guardado', async () => {
    const user = userEvent.setup()
    let finish
    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) => options?.method === 'POST'
      ? new Promise((resolve) => { finish = resolve }) : Promise.resolve(json(claim)))
    show()
    await user.click(await screen.findByRole('button', { name: 'Autorizar intervención' }))
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Rechazar intervención' })).toBeDisabled()
    await act(async () => finish(json(saved('autorizar'))))
    await screen.findByText(/todavía pendiente de HU17/)
  })

  it('actualiza un conflicto y no permite decidir sobre un plazo vencido', async () => {
    const user = userEvent.setup()
    let conflict = false
    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) => {
      if (options?.method === 'POST') {
        conflict = true
        return Promise.resolve(json({ detail: { message: 'El reclamo cambió.' } }, 409))
      }
      return Promise.resolve(json(conflict ? { ...claim, puede_decidir: false, estado: 'Pendiente de autorización - vencido' } : claim))
    })
    show()
    await user.click(await screen.findByRole('button', { name: 'Autorizar intervención' }))
    await screen.findByText(/La solicitud ya no admite decisiones/)
    expect(screen.queryByRole('button', { name: 'Autorizar intervención' })).not.toBeInTheDocument()
  })

  it('muestra un estado vacío sin dejar la página en blanco', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ items: [], total_pages: 1 }))
    show(false)
    await screen.findByText('No hay gastos extraordinarios para mostrar')
  })

  it('muestra el error de acceso sin ofrecer botones de decisión', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: { message: 'No encontramos ese reclamo.' } }, 404))
    show()
    await screen.findByText('No encontramos ese reclamo.')
    expect(screen.queryByRole('button', { name: 'Autorizar intervención' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Volver a autorizaciones' })).toBeInTheDocument()
  })

  it('lista sólo datos devueltos y enlaza al detalle protegido', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ items: [claim], total_pages: 1 }))
    show(false)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Revisar y decidir' })).toHaveAttribute('href', `/propietario/reclamos/${claim.id}/autorizar`))
  })
})
