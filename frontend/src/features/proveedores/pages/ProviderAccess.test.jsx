import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../auth/authContext.js'
import ProviderAccessPanel from '../components/ProviderAccessPanel.jsx'
import ProviderActivationPage from './ProviderActivationPage.jsx'
import ProviderHomePage from './ProviderHomePage.jsx'
import ProtectedRoute from '../../auth/ProtectedRoute.jsx'
import { homePathForRole } from '../../auth/routing.js'

const providerId = '00000000-0000-0000-0000-000000000032'
const token = 'x'.repeat(43)
const json = (body, status = 200) => ({ ok: status < 400, status, headers: { get: () => 'application/json' }, json: async () => body })
const auth = { user: null, isLoading: false, logout: vi.fn() }
const pending = { proveedor_id: providerId, email: 'service@example.com', estado: 'pendiente', envio_estado: 'enviado', puede_invitar: true }

function wrap(element, context = auth) {
  return render(<AuthContext.Provider value={context}><MemoryRouter>{element}</MemoryRouter></AuthContext.Provider>)
}

afterEach(() => { vi.restoreAllMocks(); window.history.replaceState(null, '', '/'); auth.logout.mockReset() })

describe('acceso administrativo del proveedor', () => {
  it('valida el correo y habilita sin exponer un enlace secreto', async () => {
    const user = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ proveedor_id: providerId, estado: 'sin_acceso', puede_invitar: true })).mockResolvedValueOnce(json(pending))
    wrap(<ProviderAccessPanel providerId={providerId} active />)
    const input = await screen.findByLabelText(/Correo de acceso/)
    await user.type(input, 'invalido')
    await user.click(screen.getByRole('button', { name: 'Habilitar y enviar invitación' }))
    expect(await screen.findByText('Ingresá un correo válido para enviar la invitación.')).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(1)
    await user.clear(input)
    await user.type(input, 'SERVICE@example.com')
    await user.click(screen.getByRole('button', { name: 'Habilitar y enviar invitación' }))
    expect(await screen.findByText('Pendiente de activación')).toBeVisible()
    expect(JSON.parse(fetch.mock.calls[1][1].body).email).toBe('service@example.com')
    expect(screen.getByText(/Esto no confirma su entrega ni su lectura/)).toBeVisible()
    expect(screen.queryByRole('link', { name: /activar/i })).not.toBeInTheDocument()
  })

  it('requiere confirmar el reenvío y permite cancelar', async () => {
    const user = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(pending))
    wrap(<ProviderAccessPanel providerId={providerId} active />)
    await user.click(await screen.findByRole('button', { name: 'Generar nueva invitación' }))
    expect(screen.getByText(/El enlace anterior dejará de funcionar/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(fetch).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Generar nueva invitación' }))
    await user.click(screen.getByRole('button', { name: 'Generar y enviar' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  })

  it('muestra conflicto de email junto al campo', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({ proveedor_id: providerId, estado: 'sin_acceso', puede_invitar: true })).mockResolvedValueOnce(json({ detail: { field: 'email', message: 'Correo ya utilizado.' } }, 409))
    wrap(<ProviderAccessPanel providerId={providerId} active />)
    await user.type(await screen.findByLabelText(/Correo de acceso/), 'other@example.com')
    await user.click(screen.getByRole('button', { name: 'Habilitar y enviar invitación' }))
    expect(await screen.findByText('Correo ya utilizado.')).toBeVisible()
    expect(screen.getByLabelText(/Correo de acceso/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('muestra el fallo de correo y conserva la cuenta pendiente', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...pending, envio_estado: 'fallido', ultimo_error: 'No se pudo enviar la invitación.' }))
    wrap(<ProviderAccessPanel providerId={providerId} active />)
    expect(await screen.findByText('No se pudo enviar la invitación.')).toBeVisible()
    expect(screen.getByText('Pendiente de activación')).toBeVisible()
  })

  it('no permite cambiar el correo de una cuenta activa', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...pending, estado: 'activo', puede_invitar: false }))
    wrap(<ProviderAccessPanel providerId={providerId} active />)
    expect(await screen.findByLabelText(/Correo de acceso/)).toBeDisabled()
    expect(screen.queryByRole('button', { name: /invitación/ })).not.toBeInTheDocument()
  })
})

describe('activación del proveedor', () => {
  it('quita el secreto de la URL, valida confirmación y permite activarse', async () => {
    window.history.replaceState(null, '', `/activar-proveedor#token=${token}`)
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ message: 'Activada' }))
    const user = userEvent.setup()
    wrap(<ProviderActivationPage />)
    expect(window.location.hash).toBe('')
    await user.type(screen.getByLabelText(/Nueva contraseña/), 'Prueba123')
    await user.type(screen.getByLabelText(/Confirmá tu contraseña/), 'Distinta123')
    await user.click(screen.getByRole('button', { name: 'Activar mi cuenta' }))
    expect(screen.getByText('La confirmación no coincide con la contraseña.')).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
    await user.clear(screen.getByLabelText(/Confirmá tu contraseña/))
    await user.type(screen.getByLabelText(/Confirmá tu contraseña/), 'Prueba123')
    await user.click(screen.getByRole('button', { name: 'Activar mi cuenta' }))
    expect(await screen.findByRole('heading', { name: 'Tu cuenta está activa' })).toBeVisible()
    expect(JSON.parse(fetch.mock.calls[0][1].body).token).toBe(token)
    expect(screen.getByRole('link', { name: 'Ir a iniciar sesión' })).toBeVisible()
  })

  it('explica un enlace incompleto sin hacer peticiones', () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
    wrap(<ProviderActivationPage />)
    expect(screen.getByText(/El enlace está incompleto/)).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('muestra el vencimiento sin afirmar activación', async () => {
    window.history.replaceState(null, '', `/activar-proveedor#token=${token}`)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: { message: 'Invitación vencida. Pedí una nueva.' } }, 400))
    const user = userEvent.setup()
    wrap(<ProviderActivationPage />)
    await user.type(screen.getByLabelText(/Nueva contraseña/), 'Prueba123')
    await user.type(screen.getByLabelText(/Confirmá tu contraseña/), 'Prueba123')
    await user.click(screen.getByRole('button', { name: 'Activar mi cuenta' }))
    expect(await screen.findByText('Invitación vencida. Pedí una nueva.')).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Tu cuenta está activa' })).not.toBeInTheDocument()
  })

  it('no cierra la sesión existente automáticamente', () => {
    window.history.replaceState(null, '', `/activar-proveedor#token=${token}`)
    wrap(<ProviderActivationPage />, { ...auth, user: { rol: 'administrador' } })
    expect(screen.getByText(/Tenés una sesión abierta/)).toBeVisible()
    expect(auth.logout).not.toHaveBeenCalled()
    expect(screen.queryByLabelText(/Nueva contraseña/)).not.toBeInTheDocument()
  })
})

describe('portal y rutas', () => {
  it('identifica al proveedor y diferencia la integración pendiente de una bandeja real', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ proveedor_id: providerId, nombre_razon_social: 'Servicio Sintético', email: 'service@example.com', solicitudes_disponibles: false }))
    wrap(<ProviderHomePage />)
    expect(await screen.findByText('Servicio Sintético')).toBeVisible()
    expect(screen.getByText(/La recepción de solicitudes de presupuesto todavía está en preparación/)).toBeVisible()
    expect(screen.queryByText('No tenés solicitudes')).not.toBeInTheDocument()
    expect(homePathForRole('proveedor')).toBe('/proveedor')
  })

  it('redirige a login sin sesión', () => {
    wrap(<Routes><Route element={<ProtectedRoute allowedRoles={['proveedor']} />}><Route path="/" element={<ProviderHomePage />} /></Route><Route path="/login" element={<p>Login de prueba</p>} /></Routes>)
    expect(screen.getByText('Login de prueba')).toBeVisible()
  })

  it('un proveedor no accede a administración aunque cambie la URL', () => {
    wrap(<Routes><Route element={<ProtectedRoute allowedRoles={['administrador']} />}><Route path="/" element={<p>Administración protegida</p>} /></Route><Route path="/proveedor" element={<p>Inicio del proveedor</p>} /></Routes>, { ...auth, user: { rol: 'proveedor', primer_ingreso: false } })
    expect(screen.getByText('Inicio del proveedor')).toBeVisible()
    expect(screen.queryByText('Administración protegida')).not.toBeInTheDocument()
  })
})
