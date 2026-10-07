import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../features/auth/authContext.js'
import AdminLayout from './AdminLayout.jsx'
import RoleLayout from './RoleLayout.jsx'

function show(role, path) {
  return render(
    <AuthContext.Provider value={{ user: { rol: role, email: 'staff@example.com' }, logout: vi.fn() }}>
      <MemoryRouter initialEntries={[path]}>
        {role === 'administrador' ? <AdminLayout /> : <RoleLayout />}
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('integración de navegación HU13 y HU14', () => {
  it.each([
    ['administrador', '/escalados', 'Casos escalados'],
    ['administrador', '/expensas', 'Expensas'],
    ['operador', '/operador/escalados', 'Casos escalados'],
    ['operador', '/expensas', 'Expensas'],
  ])('conserva ambas bandejas y el módulo activo para %s en %s', (role, path, active) => {
    show(role, path)
    expect(screen.getByRole('link', { name: 'Casos escalados' })).toHaveAttribute(
      'href', role === 'operador' ? '/operador/escalados' : '/escalados',
    )
    expect(screen.getByRole('link', { name: 'Expensas' })).toHaveAttribute('href', '/expensas')
    expect(screen.getByRole('link', { name: active })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
  })

  it.each(['inquilino', 'propietario'])('no muestra bandejas del personal al %s', (role) => {
    show(role, `/${role}`)
    expect(screen.queryByRole('link', { name: 'Casos escalados' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Expensas' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Mis contratos' })).toBeInTheDocument()
  })
})
