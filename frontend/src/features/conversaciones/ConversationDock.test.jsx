import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, Link } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConversationDockProvider, ConversationLauncher, QuestionsButton } from './ConversationDock.jsx'
import ProviderQuoteDetailPage from '../proveedores/pages/ProviderQuoteDetailPage.jsx'

const provider = { id: 'provider', rol: 'proveedor', primer_ingreso: false }
const rid = '00000000-0000-0000-0000-000000000033'
const agentId = '00000000-0000-0000-0000-000000000034'
const queryId = '00000000-0000-0000-0000-000000000035'
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const inbox = (extra = {}) => ({ items: [{ id: agentId, solicitud_id: rid, finalidad: 'presupuesto', audiencia: 'proveedor', numero: 33, proveedor: 'Servicio demo', no_leidos: 2 }], no_leidos: 2, page: 1, page_size: 20, total: 1, ...extra })
const thread = (extra = {}) => ({ id: agentId, solicitud_id: rid, finalidad: 'presupuesto', puede_enviar: false, no_leidos: 2,
  ultimo_numero: 1, hay_anteriores: false, hay_nuevos: false, motivo_solo_lectura: 'Los avisos se confirman con las acciones de cada etapa.',
  items: [{ id: 'message', numero: 1, texto: 'Aviso individual del agente', origen: 'agente', autor_nombre: 'Agente AARI', creado_en: '2026-10-29T12:00:00Z' }], ...extra })
const pending = { id: rid, numero: 33, descripcion: 'Pérdida debajo de la pileta', ubicacion: 'Unidad de prueba', estado: 'pendiente', puede_responder: true,
  conversacion_habilitada: true, consulta_tecnica: null, presupuesto: null, vence_en: '2026-10-30T12:00:00Z' }
const fixture = (handler) => vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options = {}) => {
  const value = String(url)
  const result = handler?.(value, options)
  if (result) return result
  if (value.includes('/bandeja?')) return json(inbox())
  if (value.endsWith('/lectura')) return json({ leido_hasta: 1, no_leidos: 0 })
  return json(thread())
})
const mount = (children = <p>Otra pantalla</p>, user = provider) => render(<MemoryRouter><ConversationDockProvider user={user}>{children}</ConversationDockProvider></MemoryRouter>)
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

describe('bandeja flotante HU33', () => {
  it('avisa con contador sin abrir ni marcar como leído y no cambia el foco', async () => {
    const fetch = fixture()
    mount(<button>Acción de la página</button>)
    const action = screen.getByRole('button', { name: 'Acción de la página' })
    action.focus()
    expect(await screen.findByRole('button', { name: 'Mensajes, 2 sin leer' })).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(action).toHaveFocus()
    expect(fetch.mock.calls.every(([url]) => !String(url).endsWith('/lectura'))).toBe(true)
  })

  it('marca únicamente el hilo abierto y no ofrece escritura en avisos del agente', async () => {
    const fetch = fixture()
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Mensajes, 2 sin leer' }))
    expect(screen.queryByText('Aviso individual del agente')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Reclamo #000033/ }))
    expect(await screen.findByText('Aviso individual del agente')).toBeVisible()
    expect(screen.queryByLabelText('Tu mensaje')).not.toBeInTheDocument()
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('/hilos/' + agentId + '/lectura'))).toBe(true))
  })

  it('cierra con Escape, restaura foco y desmonta el hilo para no leer al estar cerrado', async () => {
    const fetch = fixture()
    mount()
    const button = await screen.findByRole('button', { name: 'Mensajes, 2 sin leer' })
    await userEvent.click(button)
    await userEvent.click(screen.getByRole('button', { name: /Reclamo #000033/ }))
    await screen.findByText('Aviso individual del agente')
    expect(document.body.style.overflow).toBe('hidden')
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(button).toHaveFocus()
    expect(document.body.style.overflow).not.toBe('hidden')
    const reads = fetch.mock.calls.filter(([url]) => String(url).endsWith('/lectura')).length
    vi.useFakeTimers()
    await act(async () => { vi.advanceTimersByTime(16000) })
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/lectura'))).toHaveLength(reads)
  })

  it('la bandeja permanece disponible al navegar entre pantallas', async () => {
    fixture()
    render(<MemoryRouter><ConversationDockProvider user={provider}><Routes>
      <Route path="/" element={<Link to="/otra">Ir a otra pantalla</Link>} />
      <Route path="/otra" element={<h1>Otra pantalla</h1>} />
    </Routes></ConversationDockProvider></MemoryRouter>)
    await screen.findByRole('button', { name: 'Mensajes, 2 sin leer' })
    await userEvent.click(screen.getByRole('link', { name: 'Ir a otra pantalla' }))
    expect(await screen.findByRole('heading', { name: 'Otra pantalla' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Mensajes, 2 sin leer' })).toBeVisible()
  })

  it('al cambiar de sesión borra el historial privado y al salir oculta el acceso', async () => {
    fixture()
    const view = mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Mensajes, 2 sin leer' }))
    await userEvent.click(screen.getByRole('button', { name: /Reclamo #000033/ }))
    await screen.findByText('Aviso individual del agente')
    view.rerender(<MemoryRouter><ConversationDockProvider user={null}><p>Login</p></ConversationDockProvider></MemoryRouter>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Aviso individual del agente')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Mensajes/ })).not.toBeInTheDocument()
  })

  it('consulta páginas en servidor y no conserva una página vieja al fallar', async () => {
    fixture((url) => url.includes('/bandeja?') ? url.includes('page=2&') ? json({ detail: { message: 'Fallo de la segunda página' } }, 503) : json(inbox({ total: 21 })) : null)
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Mensajes, 2 sin leer' }))
    await userEvent.click(screen.getByRole('button', { name: 'Ver siguientes' }))
    expect(await screen.findByText('Fallo de la segunda página')).toBeVisible()
    expect(screen.queryByRole('button', { name: /Reclamo #000033/ })).not.toBeInTheDocument()
  })

  it('desactiva sondeo en segundo plano y aborta al desmontar', async () => {
    const fetch = fixture()
    const view = mount()
    await screen.findByRole('button', { name: 'Mensajes, 2 sin leer' })
    vi.useFakeTimers()
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    const count = fetch.mock.calls.length
    await act(async () => { vi.advanceTimersByTime(24000) })
    expect(fetch.mock.calls).toHaveLength(count)
    visibility.mockReturnValue('visible')
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(fetch.mock.calls.length).toBeGreaterThan(count)
    view.unmount()
    expect(fetch.mock.calls.at(-1)[1].signal.aborted).toBe(true)
  })

  it('sin funcionalidad habilitada no deja un botón roto', async () => {
    fixture(() => json({ detail: { code: 'conversations_disabled', message: 'Deshabilitado' } }, 503))
    mount()
    await waitFor(() => expect(screen.queryByRole('button', { name: /^Mensajes/ })).not.toBeInTheDocument())
  })

  it('acceso desde resumen resuelve el hilo individual pero no envía texto libre', async () => {
    fixture()
    mount(<ConversationLauncher requestId={rid} />)
    await userEvent.click(screen.getByRole('button', { name: 'Ver avisos del agente' }))
    expect(await screen.findByText('Aviso individual del agente')).toBeVisible()
    expect(screen.queryByLabelText('Tu mensaje')).not.toBeInTheDocument()
  })
})

describe('consultas técnicas por excepción', () => {
  it('doble clic abre una sola consulta y el error conserva la clave para reintentar', async () => {
    let attempt = 0
    const keys = []
    fixture((url, options) => {
      if (!url.endsWith('/consultas')) return null
      keys.push(JSON.parse(options.body).request_id)
      attempt += 1
      return attempt === 1 ? json({ detail: { message: 'Inquilino sin acceso activo' } }, 409) : json({ id: queryId })
    })
    mount(<QuestionsButton request={pending} />)
    await userEvent.click(screen.getByRole('button', { name: 'Necesito hacer unas preguntas' }))
    expect(await screen.findByText('Inquilino sin acceso activo')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Necesito hacer unas preguntas' }))
    await screen.findByRole('dialog')
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBe(keys[1])
  })

  it('el cierre es explícito, pasa a sólo lectura y avisa al formulario real', async () => {
    let closed = false
    const changed = vi.fn()
    window.addEventListener('aari:consultas-cambiaron', changed)
    fixture((url) => {
      if (url.includes('/bandeja?')) return json(inbox({ items: [{ ...inbox().items[0], id: queryId, finalidad: 'consulta_tecnica' }] }))
      if (url.endsWith('/finalizar-consultas')) { closed = true; return json({ id: queryId }) }
      if (url.includes('/hilos/') && !url.endsWith('/lectura')) return json(thread({ id: queryId, finalidad: 'consulta_tecnica', puede_enviar: !closed, puede_finalizar: !closed, motivo_solo_lectura: 'Consultas finalizadas.' }))
      return null
    })
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Mensajes, 2 sin leer' }))
    await userEvent.click(screen.getByRole('button', { name: /Reclamo #000033/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Finalizar consultas y continuar presupuesto' }))
    expect(await screen.findByText('Consultas finalizadas.')).toBeVisible()
    expect(screen.queryByLabelText('Tu mensaje')).not.toBeInTheDocument()
    expect(changed).toHaveBeenCalled()
    window.removeEventListener('aari:consultas-cambiaron', changed)
  })

  it('el detalle real bloquea el presupuesto mientras hay consultas y conserva navegación', async () => {
    fixture((url) => !url.includes('/conversaciones/') ? json({ ...pending, consulta_tecnica: { id: queryId, consultas_cerradas_en: null } }) : null)
    render(<MemoryRouter initialEntries={['/proveedor/solicitudes/' + rid + '?page=2&estado=pendientes']}><ConversationDockProvider user={provider}><Routes>
      <Route path="/proveedor/solicitudes/:requestId" element={<ProviderQuoteDetailPage />} />
    </Routes></ConversationDockProvider></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Revisar presupuesto' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Continuar consultas con el inquilino' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Volver a mis solicitudes' })).toHaveAttribute('href', '/proveedor?page=2&estado=pendientes')
  })
})
