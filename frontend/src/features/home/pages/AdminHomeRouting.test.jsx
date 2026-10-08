import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../../../App.jsx'

const summary = {
  consultado_en: '2026-10-05T15:30:00Z',
  propietarios: { total: 1 }, propiedades: { total: 1 }, inquilinos: { total: 1 },
  proveedores: { total: 1, activos: 1 }, operadores: { total: 1, activos: 1 },
  reclamos: { activos: 1, pendientes_clasificacion: 0 },
}
function sessionFetch(user) {
  const fetchMock = vi.fn(async (url) => {
    const isSession = url.endsWith('/auth/me')
    return new Response(JSON.stringify(isSession ? user ? { user } : { detail: 'Sin sesión' } : summary), {
      status: isSession && !user ? 401 : 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
function renderApp(path) { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
afterEach(() => vi.unstubAllGlobals())

describe('integración del Home con sesión y rutas', () => {
  it.each(['/', '/inicio'])('el administrador entra desde %s y ve su identidad', async (path) => {
    sessionFetch({ email: 'admin@example.com', rol: 'administrador', primer_ingreso: false })
    renderApp(path)
    expect(await screen.findByRole('heading', { name: 'Tu inmobiliaria, de un vistazo.' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir perfil de admin@example.com' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Inicio' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /notificaciones/ })).not.toBeInTheDocument()
  })

  it('sin sesión envía al login y no consulta los contadores', async () => {
    const fetchMock = sessionFetch(null)
    renderApp('/inicio')
    await screen.findByRole('heading', { name: 'Iniciá sesión' })
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/admin/resumen'))).toBe(false)
  })

  it.each(['propietario', 'inquilino', 'operador'])('el rol %s no puede acceder', async (rol) => {
    const fetchMock = sessionFetch({ email: 'persona@example.com', rol, primer_ingreso: false })
    renderApp('/inicio')
    await screen.findByRole('heading', { name: 'Tu sesión está protegida y lista' })
    expect(screen.queryByRole('heading', { name: 'Tu inmobiliaria, de un vistazo.' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/admin/resumen'))).toBe(false)
  })

  it('el primer ingreso administrativo debe cambiar su contraseña antes del panel', async () => {
    const fetchMock = sessionFetch({ email: 'admin@example.com', rol: 'administrador', primer_ingreso: true })
    renderApp('/inicio')
    await screen.findByRole('heading', { name: 'Creá tu contraseña' })
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/admin/resumen'))).toBe(false)
  })

  it.each(['ordinario', 'extraordinario', 'expensa'])('revisa un caso desde el Home y actualiza pendientes sin cerrar la reparación: %s', async (expense) => {
    const user = userEvent.setup()
    const claim = {
      id: '00000000-0000-0000-0000-000000000101', numero: 25,
      descripcion: 'Desperfecto sintético cuyo origen requiere revisión.',
      estado: 'Escalado', urgencia: 'media', creado_en: '2026-10-01T10:00:00Z',
      escalado_en: '2026-10-01T12:00:00Z', updated_at: '2026-10-01T12:00:00.123456Z',
      motivo_escalado: 'confianza_insuficiente', confianza_clasificacion: 0.55,
      propiedad: { direccion: 'Unidad de prueba 100', provincia: 'Córdoba', localidad: 'Localidad de prueba', tipo: 'casa' },
      inquilino_nombre: 'Inquilino de prueba', puede_resolver: true, fotos: [], decisiones: [], historial: [],
    }
    let classified = false
    const json = (body) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
    const fetchMock = vi.fn(async (url, options) => {
      const path = new URL(url).pathname
      if (path === '/auth/me') return json({ user: { email: 'admin@example.com', rol: 'administrador', primer_ingreso: false } })
      if (path === '/admin/resumen') return json({ ...summary, reclamos: { activos: 1, pendientes_clasificacion: classified ? 0 : 1 } })
      if (path === '/reclamos/escalados') return json({ items: classified ? [] : [claim], total: classified ? 0 : 1, page: 1, page_size: 20, total_pages: 1 })
      if (path === `/reclamos/${claim.id}/resolver-escalado` && options.method === 'POST') {
        classified = true
        return json({})
      }
      if (path === `/reclamos/escalados/${claim.id}`) return json({ ...claim, puede_resolver: !classified,
        estado: classified ? 'Pendiente de respuesta del responsable' : claim.estado })
      throw new Error(`Solicitud no prevista: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    renderApp('/inicio')
    await screen.findByText('Requieren revisión')
    await user.click(screen.getByRole('link', { name: 'Revisar casos' }))
    await user.click(await screen.findByRole('link', { name: 'Resolver clasificación del reclamo #000025' }))
    await user.selectOptions(await screen.findByLabelText(/Tipo de gasto/), expense)
    await user.type(screen.getByLabelText(/Fundamento de la decisión/), 'La revisión manual confirmó la causa del desperfecto.')
    await user.click(screen.getByRole('button', { name: 'Confirmar clasificación' }))
    await screen.findByText(/la reparación todavía no está resuelta/)
    const posts = fetchMock.mock.calls.filter(([, options]) => options.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(JSON.parse(posts[0][1].body)).toEqual({ tipo_gasto: expense,
      fundamento: 'La revisión manual confirmó la causa del desperfecto.', expected_updated_at: claim.updated_at })
    await user.click(screen.getByRole('link', { name: 'Inicio' }))
    await screen.findByText('Sin pendientes')
    const activeCard = screen.getByRole('heading', { name: 'Reclamos activos' }).closest('article')
    expect(within(activeCard).getByText('1')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/admin/resumen'))).toHaveLength(2)
    await user.click(screen.getByRole('link', { name: 'Revisar casos' }))
    expect(await screen.findByText('No hay casos en esta página')).toBeInTheDocument()
  })
})
