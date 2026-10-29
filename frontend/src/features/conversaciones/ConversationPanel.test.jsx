import { StrictMode } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ConversationPanel from './ConversationPanel.jsx'
import ClaimQuoteSummary from '../proveedores/components/ClaimQuoteSummary.jsx'
import ProviderQuoteDetailPage from '../proveedores/pages/ProviderQuoteDetailPage.jsx'
import ProviderQuoteRequests from '../proveedores/components/ProviderQuoteRequests.jsx'

const rid = '00000000-0000-0000-0000-000000000033'
const msg = (numero, texto = `Consulta ${numero}`, extra = {}) => ({
  id: `message-${numero}`, numero, texto, origen: 'humano', autor_nombre: 'Proveedor sintético',
  creado_en: '2026-10-28T20:00:00Z', propio: false, ...extra,
})
const conversation = (items = [msg(1, 'Solicitud publicada', { origen: 'agente', autor_nombre: 'Agente AARI' })], extra = {}) => ({
  id: 'conversation', solicitud_id: rid, finalidad: 'consulta_tecnica', numero_reclamo: 33,
  puede_enviar: true, motivo_solo_lectura: null, ultimo_numero: items.at(-1)?.numero ?? 0,
  leido_hasta: 0, no_leidos: items.length, hay_anteriores: false, hay_nuevos: false, items, ...extra,
})
const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const defaultRead = (options) => json({ leido_hasta: JSON.parse(options.body).hasta_numero, no_leidos: 0 })
const request = { id: rid, numero: 33, descripcion: 'Pérdida bajo la pileta.', ubicacion: 'Unidad sintética',
  estado: 'respondida', puede_responder: false, vence_en: '2026-10-29T20:00:00Z',
  conversacion_habilitada: true, conversacion_no_leidos: 2,
  presupuesto: { monto: '10000', tipo_importe: 'minimo', moneda: 'ARS', descripcion: 'Diagnóstico y materiales', recibido_en: '2026-10-28T20:00:00Z' } }

afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })
const mock = (handler = () => json(conversation())) => vi.spyOn(globalThis, 'fetch').mockImplementation((url, options = {}) => {
  if (String(url).endsWith('/lectura')) return Promise.resolve(defaultRead(options))
  return Promise.resolve(handler(String(url), options))
})

describe('conversación privada HU33', () => {
  it('muestra origen, hora argentina, texto seguro y registra sólo mensajes recuperados', async () => {
    const read = vi.fn()
    const fetch = mock(() => json(conversation([msg(1, '<script>alert(1)</script>'), msg(2, 'Evento', { origen: 'agente' })], { ultimo_numero: 90, hay_nuevos: true })))
    render(<ConversationPanel requestId={rid} onRead={read} />)
    expect(await screen.findByText('<script>alert(1)</script>')).toBeVisible()
    expect(document.querySelector('script')).toBeNull()
    expect(screen.getByText('Aviso automático del agente')).toBeVisible()
    expect(screen.getAllByText(/28\/10\/26, 17:00/)).toHaveLength(2)
    await waitFor(() => expect(read).toHaveBeenCalledWith(rid, 0))
    const body = JSON.parse(fetch.mock.calls.find(([url]) => String(url).endsWith('/lectura'))[1].body)
    expect(body.hasta_numero).toBe(2)
  })

  it('abre desde el primer pendiente y no salta las páginas iniciales de 66 mensajes', async () => {
    let through = 0
    const reads = []
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options = {}) => {
      if (String(url).endsWith('/lectura')) {
        through = JSON.parse(options.body).hasta_numero
        reads.push(through)
        return json({ leido_hasta: through, no_leidos: 66 - through })
      }
      const after = new URL(String(url), 'http://aari.test').searchParams.get('despues')
      const start = after == null ? 37 : Number(after) + 1
      const end = Math.min(start + 29, 66)
      return json(conversation(Array.from({ length: end - start + 1 }, (_, index) => msg(start + index)), {
        leido_hasta: through, no_leidos: 66 - through, ultimo_numero: 66,
        hay_anteriores: after == null, hay_nuevos: after != null && end < 66,
      }))
    })
    render(<ConversationPanel requestId={rid} />)
    expect(await screen.findByText('Consulta 1')).toBeVisible()
    await waitFor(() => expect(reads).toEqual([30]))
    expect(screen.getByText(/36 sin leer/)).toBeVisible()
    expect(screen.queryByText('Consulta 66')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ver mensajes nuevos' }))
    await waitFor(() => expect(reads).toEqual([30, 60]))
    expect(screen.getByText(/6 sin leer/)).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Ver mensajes nuevos' }))
    await waitFor(() => expect(reads).toEqual([30, 60, 66]))
    expect(screen.getByText('Consulta 66')).toBeVisible()
    expect(screen.getByText(/0 sin leer/)).toBeVisible()
    expect(fetch.mock.calls.some(([url]) => String(url).includes('despues=0'))).toBe(true)
  })

  it('respeta una lectura previa y conserva la navegación de historia ya leída', async () => {
    let through = 40
    const reads = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options = {}) => {
      if (String(url).endsWith('/lectura')) {
        through = JSON.parse(options.body).hasta_numero
        reads.push(through)
        return json({ leido_hasta: through, no_leidos: 96 - through })
      }
      const query = new URL(String(url), 'http://aari.test').searchParams
      const older = query.has('antes')
      const start = older ? 11 : query.has('despues') ? Number(query.get('despues')) + 1 : 67
      const end = Math.min(start + 29, 96)
      return json(conversation(Array.from({ length: end - start + 1 }, (_, i) => msg(start + i)), {
        leido_hasta: through, no_leidos: 96 - through, ultimo_numero: 96,
        hay_anteriores: older || !query.has('despues'), hay_nuevos: !older && end < 96,
      }))
    })
    render(<ConversationPanel requestId={rid} />)
    expect(await screen.findByText('Consulta 41')).toBeVisible()
    await waitFor(() => expect(reads).toEqual([70]))
    await userEvent.click(screen.getByRole('button', { name: 'Ver mensajes anteriores' }))
    expect(await screen.findByText('Consulta 11')).toBeVisible()
    expect(reads).toEqual([70])
    await userEvent.click(screen.getByRole('button', { name: 'Ver mensajes nuevos' }))
    await waitFor(() => expect(reads).toEqual([70, 96]))
  })

  it('no confirma la página final si falla recuperar el primer tramo pendiente', async () => {
    let retry = false
    const fetch = mock((url) => {
      if (!url.includes('despues=0')) return json(conversation([msg(37), msg(66)], { hay_anteriores: true }))
      if (!retry) return Promise.reject(new TypeError('network'))
      return json(conversation(Array.from({ length: 30 }, (_, i) => msg(i + 1)), { hay_nuevos: true }))
    })
    render(<ConversationPanel requestId={rid} />)
    expect(await screen.findByText(/No pudimos conectarnos/)).toBeVisible()
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/lectura'))).toBe(false)
    retry = true
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar conversación' }))
    expect(await screen.findByText('Consulta 1')).toBeVisible()
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/lectura'))).toBe(true))
    const reads = fetch.mock.calls.filter(([url]) => String(url).endsWith('/lectura'))
    expect(reads.map(([, options]) => JSON.parse(options.body).hasta_numero)).toEqual([30])
  })

  it('avanza sólo por secuencias contiguas aunque una respuesta venga incompleta', async () => {
    const fetch = mock((url) => json(url.includes('despues=2')
      ? conversation([msg(3), msg(4)])
      : conversation([msg(1), msg(2), msg(4)], { hay_nuevos: true })))
    render(<ConversationPanel requestId={rid} />)
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/lectura'))).toBe(true))
    let reads = fetch.mock.calls.filter(([url]) => String(url).endsWith('/lectura'))
    expect(JSON.parse(reads[0][1].body).hasta_numero).toBe(2)
    await userEvent.click(screen.getByRole('button', { name: 'Ver mensajes nuevos' }))
    expect(await screen.findByText('Consulta 3')).toBeVisible()
    await waitFor(() => {
      reads = fetch.mock.calls.filter(([url]) => String(url).endsWith('/lectura'))
      expect(reads.map(([, options]) => JSON.parse(options.body).hasta_numero)).toEqual([2, 4])
    })
  })

  it('consulta después de cero si se abrió vacío y luego llegan muchas novedades', async () => {
    let arrived = false
    const fetch = mock((url) => !arrived ? json(conversation([])) : json(url.includes('despues=0')
      ? conversation(Array.from({ length: 30 }, (_, i) => msg(i + 1)), { hay_nuevos: true })
      : conversation([msg(37), msg(66)], { hay_anteriores: true })))
    render(<ConversationPanel requestId={rid} />)
    await screen.findByText('Todavía no hay mensajes')
    arrived = true
    await userEvent.click(screen.getByRole('button', { name: 'Actualizar conversación' }))
    expect(await screen.findByText('Consulta 1')).toBeVisible()
    const reads = fetch.mock.calls.filter(([url]) => String(url).endsWith('/lectura'))
    expect(reads.map(([, options]) => JSON.parse(options.body).hasta_numero)).toEqual([30])
  })

  it('cancela la recuperación inicial sin confirmar lectura al cerrar el hilo', async () => {
    let resolvePage
    let signal
    const fetch = mock((url, options) => {
      if (!url.includes('despues=0')) return json(conversation([msg(37), msg(66)], { hay_anteriores: true }))
      signal = options.signal
      return new Promise((resolve) => { resolvePage = resolve })
    })
    const view = render(<ConversationPanel requestId={rid} />)
    await waitFor(() => expect(resolvePage).toBeTypeOf('function'))
    view.unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => resolvePage(json(conversation([msg(1)]))))
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/lectura'))).toBe(false)
  })

  it('conserva borrador e identificador ante una respuesta perdida, sin duplicar confirmaciones', async () => {
    let posts = 0
    const fetch = mock((_url, options) => {
      if (options.method !== 'POST') return json(conversation())
      posts++
      return posts === 1 ? Promise.reject(new TypeError('network')) : json({ mensaje: msg(2, '¿Incluye materiales?', { propio: true }), repetido: true })
    })
    render(<ConversationPanel requestId={rid} />)
    const input = await screen.findByLabelText('Tu mensaje')
    const user = userEvent.setup()
    await user.type(input, '¿Incluye materiales?')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    expect(await screen.findByText(/No pudimos conectarnos/)).toBeVisible()
    expect(input).toHaveValue('¿Incluye materiales?')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    await waitFor(() => expect(input).toHaveValue(''))
    await waitFor(() => expect(input).toHaveFocus())
    const bodies = fetch.mock.calls.filter(([url]) => String(url).endsWith('/mensajes')).map(([, options]) => JSON.parse(options.body))
    expect(bodies).toHaveLength(2)
    expect(bodies[0]).toEqual(bodies[1])
    expect(bodies[0]).toEqual({ texto: '¿Incluye materiales?', request_id: expect.any(String) })
    expect(await screen.findByText('¿Incluye materiales?')).toBeVisible()
  })

  it('el POST no salta mensajes concurrentes al refrescar', async () => {
    const fetch = mock((url, options) => {
      if (options.method === 'POST') return json({ mensaje: msg(4, 'Mi respuesta', { propio: true }) })
      return json(url.includes('despues=1') ? conversation([msg(2), msg(3), msg(4, 'Mi respuesta', { propio: true })]) : conversation())
    })
    render(<ConversationPanel requestId={rid} />)
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Tu mensaje'), 'Mi respuesta')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    expect(await screen.findByText('Consulta 2')).toBeVisible()
    expect(screen.getByText('Consulta 3')).toBeVisible()
    expect(screen.getAllByText('Mi respuesta')).toHaveLength(1)
    expect(fetch.mock.calls.filter(([url]) => String(url).includes('despues=4'))).toHaveLength(0)
  })

  it('carga historia anterior sin duplicar y conserva la ventana nueva', async () => {
    const fetch = mock((url) => json(url.includes('antes=31')
      ? conversation(Array.from({ length: 30 }, (_, i) => msg(i + 1)), { leido_hasta: 32, ultimo_numero: 32, hay_anteriores: false })
      : conversation([msg(31), msg(32)], { leido_hasta: 30, hay_anteriores: true })))
    render(<ConversationPanel requestId={rid} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Ver mensajes anteriores' }))
    expect(await screen.findByText('Consulta 1')).toBeVisible()
    expect(screen.getAllByText('Consulta 31')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Ver mensajes anteriores' })).not.toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => String(url).includes('antes=31'))).toBe(true)
  })

  it('no permite enviar en un intento cancelado', async () => {
    mock(() => json(conversation([msg(1)], { puede_enviar: false, motivo_solo_lectura: 'Este intento fue cancelado.' })))
    render(<ConversationPanel requestId={rid} />)
    expect(await screen.findByText('Este intento fue cancelado.')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Enviar mensaje' })).not.toBeInTheDocument()
    expect(screen.getByText('Consulta 1')).toBeVisible()
  })

  it('oculta historial y formulario cuando se revoca el acceso', async () => {
    let revoked = false
    mock(() => revoked ? json({ detail: { message: 'No encontramos esa conversación.' } }, 404) : json(conversation([msg(1, 'Mensaje privado')])))
    render(<ConversationPanel requestId={rid} />)
    expect(await screen.findByText('Mensaje privado')).toBeVisible()
    revoked = true
    await userEvent.click(screen.getByRole('button', { name: 'Actualizar conversación' }))
    expect(await screen.findByText('No encontramos esa conversación.')).toBeVisible()
    expect(screen.queryByText('Mensaje privado')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Tu mensaje')).not.toBeInTheDocument()
  })

  it('no mezcla una conversación anterior con la siguiente', async () => {
    mock((url) => json(conversation([msg(1, url.includes('/otro?') ? 'Segundo hilo' : 'Primer hilo')])))
    const view = render(<ConversationPanel requestId={rid} />)
    expect(await screen.findByText('Primer hilo')).toBeVisible()
    view.rerender(<ConversationPanel requestId="otro" />)
    expect(await screen.findByText('Segundo hilo')).toBeVisible()
    expect(screen.queryByText('Primer hilo')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Tu mensaje')).toHaveValue('')
  })

  it('sigue recuperando mensajes tras el montaje estricto de React', async () => {
    mock()
    render(<StrictMode><ConversationPanel requestId={rid} /></StrictMode>)
    expect(await screen.findByText('Solicitud publicada')).toBeVisible()
  })

  it('detiene sondeos en segundo plano y cancela consultas al desmontar', async () => {
    const fetch = mock()
    const view = render(<ConversationPanel requestId={rid} />)
    await screen.findByLabelText('Tu mensaje')
    await waitFor(() => expect(screen.getByText(/0 sin leer/)).toBeVisible())
    vi.useFakeTimers()
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    const before = fetch.mock.calls.length
    await act(async () => { vi.advanceTimersByTime(24000) })
    expect(fetch.mock.calls).toHaveLength(before)
    visibility.mockReturnValue('visible')
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(fetch.mock.calls.length).toBeGreaterThan(before)
    view.unmount()
    const after = fetch.mock.calls.length
    await act(async () => { vi.advanceTimersByTime(24000) })
    expect(fetch.mock.calls).toHaveLength(after)
  })
})

describe('integración con pantallas reales', () => {
  it('el detalle conserva el presupuesto y ofrece el acceso global, sin abrir un chat inline', async () => {
    mock(() => json(request))
    render(<MemoryRouter initialEntries={['/proveedor/solicitudes/' + rid + '?page=2&estado=enviadas']}><Routes>
      <Route path="/proveedor/solicitudes/:requestId" element={<ProviderQuoteDetailPage />} />
    </Routes></MemoryRouter>)
    expect(await screen.findByText('Tu presupuesto enviado')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Volver a mis solicitudes' })).toHaveAttribute('href', '/proveedor?page=2&estado=enviadas')
    expect(screen.queryByLabelText('Tu mensaje')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ver avisos del agente' })).toBeVisible()
  })

  it('el resumen ofrece avisos individuales, no un chat directo con el responsable', async () => {
    mock(() => json({ items: [{ ...request, proveedor: 'Servicio Uno' }] }))
    render(<ClaimQuoteSummary claimId="claim" />)
    expect(await screen.findByRole('button', { name: 'Ver avisos de Servicio Uno' })).toBeVisible()
    expect(screen.queryByLabelText('Tu mensaje')).not.toBeInTheDocument()
  })

  it('el listado muestra no leídos sin abrir todas las conversaciones', async () => {
    const fetch = mock(() => json({ items: [request], total: 1, page: 1, page_size: 10 }))
    render(<MemoryRouter><ProviderQuoteRequests /></MemoryRouter>)
    expect(await screen.findByText('2 mensajes sin leer')).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
