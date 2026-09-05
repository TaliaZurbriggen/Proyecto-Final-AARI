import { Outlet, useLocation, useNavigate } from 'react-router'
import { AppHeader } from '../components/layout/index.js'
import { useAuth } from '../features/auth/authContext.js'
import { homePathForRole } from '../features/auth/routing.js'

const roleLabels = {
  inquilino: 'Inquilino',
  operador: 'Operación',
  propietario: 'Propietario',
}

function RoleLayout() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const homePath = homePathForRole(user?.rol)
  const items = user?.rol === 'inquilino'
    ? [
        { href: homePath, label: 'Inicio' },
        { href: '/inquilino/reclamos/nuevo', label: 'Nuevo reclamo' },
      ]
    : [{ href: homePath, label: 'Inicio' }]
  const activeItem = location.pathname.startsWith('/inquilino/reclamos')
    ? 'Nuevo reclamo'
    : 'Inicio'

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <AppHeader
        activeItem={activeItem}
        items={items}
        onLogout={handleLogout}
        onNavigate={(item) => navigate(item.href)}
        profileName={user?.email ?? 'Usuario AARI'}
        profileRole={roleLabels[user?.rol] ?? 'Acceso personal'}
        showNotifications={false}
        showSearch={false}
      />
      <Outlet />
    </>
  )
}

export default RoleLayout
