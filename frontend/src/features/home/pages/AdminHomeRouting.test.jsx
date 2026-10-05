import { render, screen } from '@testing-library/react'
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
})
