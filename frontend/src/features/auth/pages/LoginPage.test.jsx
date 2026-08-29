import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { AuthProvider } from '../AuthContext.jsx'
import LoginPage from './LoginPage.jsx'


function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}


function renderLogin() {
  render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/propietarios" element={<h1>Panel administrativo</h1>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}


afterEach(() => {
  vi.unstubAllGlobals()
})


describe('LoginPage', () => {
  it('inicia sesión y redirige al panel', async () => {
    const fetchMock = vi.fn(async (url) => {
      if (url.endsWith('/auth/me')) {
        return jsonResponse(
          { detail: { message: 'La sesión no es válida o venció.' } },
          401,
        )
      }
      return jsonResponse({
        user: {
          email: 'admin@example.com',
          id: '00000000-0000-0000-0000-000000000056',
          primer_ingreso: false,
          rol: 'administrador',
        },
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email*'), 'admin@example.com')
    await user.type(screen.getByLabelText('Contraseña*'), 'correcta')
    await user.click(screen.getByRole('button', { name: 'Ingresar' }))

    expect(
      await screen.findByRole('heading', { name: 'Panel administrativo' }),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/auth/login'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('muestra el error devuelto por el backend', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        if (url.endsWith('/auth/me')) {
          return jsonResponse({ detail: 'Sin sesión' }, 401)
        }
        return jsonResponse(
          {
            detail: {
              code: 'unauthorized',
              message: 'El email o la contraseña son incorrectos.',
            },
          },
          401,
        )
      }),
    )
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email*'), 'admin@example.com')
    await user.type(screen.getByLabelText('Contraseña*'), 'incorrecta')
    await user.click(screen.getByRole('button', { name: 'Ingresar' }))

    await waitFor(() => {
      expect(
        screen.getByText('El email o la contraseña son incorrectos.'),
      ).toBeInTheDocument()
    })
  })
})
