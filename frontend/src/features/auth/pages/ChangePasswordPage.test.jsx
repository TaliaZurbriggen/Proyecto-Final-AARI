import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { AuthProvider } from '../AuthContext.jsx'
import ChangePasswordPage from './ChangePasswordPage.jsx'

const firstLoginUser = {
  email: 'ana@example.com',
  id: '00000000-0000-0000-0000-000000000068',
  perfil_id: '00000000-0000-0000-0000-000000000069',
  primer_ingreso: true,
  rol: 'propietario',
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/cambiar-contrasena']}>
      <AuthProvider>
        <Routes>
          <Route path="/cambiar-contrasena" element={<ChangePasswordPage />} />
          <Route path="/login" element={<h1>Iniciar sesión</h1>} />
          <Route path="/propietario" element={<h1>Portal propietario</h1>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('ChangePasswordPage', () => {
  it('identifica la cuenta activa y permite cerrar una sesión equivocada', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ user: firstLoginUser }))
      .mockResolvedValueOnce(jsonResponse({ message: 'Sesión cerrada.' }))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText(firstLoginUser.email)).toBeInTheDocument()
    expect(screen.getByText('Propietario')).toBeInTheDocument()

    await user.click(
      screen.getByRole('button', { name: 'No soy yo: cerrar sesión' }),
    )

    expect(
      await screen.findByRole('heading', { name: 'Iniciar sesión' }),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/auth/logout'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('valida longitud, número y confirmación antes de enviar', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ user: firstLoginUser }))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('heading', { name: 'Creá tu contraseña' })
    await user.type(screen.getByLabelText('Contraseña temporal*'), '30123456')
    await user.type(screen.getByLabelText('Contraseña nueva*'), 'sinNumero')
    await user.type(screen.getByLabelText('Confirmar contraseña*'), 'diferente1')
    await user.click(screen.getByRole('button', { name: 'Guardar y continuar' }))

    expect(screen.getByText('Incluí al menos un número.')).toBeInTheDocument()
    expect(screen.getByText('Las contraseñas no coinciden.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('actualiza la contraseña y redirige según el rol', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ user: firstLoginUser }))
      .mockResolvedValueOnce(
        jsonResponse({
          user: { ...firstLoginUser, primer_ingreso: false },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('heading', { name: 'Creá tu contraseña' })
    await user.type(screen.getByLabelText('Contraseña temporal*'), '30123456')
    await user.type(screen.getByLabelText('Contraseña nueva*'), 'segura123')
    await user.type(screen.getByLabelText('Confirmar contraseña*'), 'segura123')
    await user.click(screen.getByRole('button', { name: 'Guardar y continuar' }))

    expect(
      await screen.findByRole('heading', { name: 'Portal propietario' }),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/auth/cambiar-contrasena'),
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
