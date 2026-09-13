import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AppHeader from './AppHeader.jsx'

const items = ['Propietarios', 'Propiedades', 'Inquilinos', 'Proveedores', 'Operadores', 'Contratos']
  .map(label => ({ label, href: `/${label.toLowerCase()}` }))

describe('cabecera compartida', () => {
  it('conserva el correo completo como nombre accesible y ayuda del texto truncado', async () => {
    const email = 'administracion.inmobiliaria@example.com'
    const logout = vi.fn()
    render(<AppHeader items={items} activeItem="Contratos" profileName={email} onLogout={logout} />)
    expect(screen.getByRole('button', { name: `Abrir perfil de ${email}` })).toBeInTheDocument()
    expect(screen.getByTitle(email)).toHaveTextContent(email)
    expect(screen.getByRole('navigation')).toHaveAccessibleName('Navegación principal')
    expect(screen.getByRole('link', { name: 'Contratos' })).toHaveAttribute('aria-current', 'page')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(logout).toHaveBeenCalledOnce()
  })

  it('centra el enlace activo desplazando solo el menú, no la página', () => {
    const { rerender } = render(<AppHeader items={items} activeItem="Propietarios" />)
    const navigation = screen.getByRole('navigation')
    const activeLink = screen.getByRole('link', { name: 'Contratos' })
    Object.defineProperties(navigation, {
      scrollWidth: { value: 640 }, clientWidth: { value: 300 },
    })
    Object.defineProperty(activeLink, 'offsetWidth', { value: 100 })
    navigation.getBoundingClientRect = () => ({ left: 16 })
    activeLink.getBoundingClientRect = () => ({ left: 536 })
    navigation.scrollTo = vi.fn()
    activeLink.scrollIntoView = vi.fn()
    rerender(<AppHeader items={items} activeItem="Contratos" />)
    expect(navigation.scrollTo).toHaveBeenCalledWith({ left: 420, behavior: 'instant' })
    expect(activeLink.scrollIntoView).not.toHaveBeenCalled()
  })

  it('mantiene la navegación y el cierre de sesión sin buscador ni notificaciones', async () => {
    const navigate = vi.fn()
    render(<AppHeader items={items} onNavigate={navigate} showSearch={false} showNotifications={false} onLogout={() => {}} />)
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /notificaciones/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('link', { name: 'Contratos' }))
    expect(navigate).toHaveBeenCalledWith(items[5])
  })
})
