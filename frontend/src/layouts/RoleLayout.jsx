import { Outlet, useNavigate } from 'react-router'
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
  const homePath = homePathForRole(user?.rol)

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <AppHeader
        activeItem="Inicio"
        items={[{ href: homePath, label: 'Inicio' }]}
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
