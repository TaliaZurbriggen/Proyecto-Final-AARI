import { Outlet, useLocation, useNavigate } from 'react-router'
import { AppHeader } from '../components/layout/index.js'
import { useAuth } from '../features/auth/authContext.js'
import { homePathForRole } from '../features/auth/routing.js'

const roleLabels = {
  inquilino: 'Inquilino',
  operador: 'Operación',
  propietario: 'Propietario',
  proveedor: 'Proveedor de servicios',
}

function RoleLayout() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const homePath = homePathForRole(user?.rol)
  const items = user?.rol === 'inquilino'
    ? [
        { href: homePath, label: 'Inicio' },
        { href: '/inquilino/reclamos', label: 'Mis reclamos' },
        { href: '/inquilino/reclamos/nuevo', label: 'Nuevo reclamo' },
      ]
    : [{ href: homePath, label: user?.rol === 'proveedor' ? 'Mis solicitudes' : 'Inicio' }]
  if (['inquilino', 'propietario'].includes(user?.rol)) {
    items.push({ href: `${homePath}/contratos`, label: 'Mis contratos' })
  }
  if (user?.rol === 'propietario') {
    items.push({ href: '/propietario/reclamos', label: 'Autorizaciones' })
  }
  if (user?.rol === 'operador') {
    items.push({ href: '/operador/escalados', label: 'Casos escalados' })
    items.push({ href: '/operador/pendientes-asignacion', label: 'Candidatos' })
    items.push({ href: '/expensas', label: 'Expensas' })
  }
  const activeItem = user?.rol === 'proveedor' ? 'Mis solicitudes' : location.pathname.startsWith('/expensas')
    ? 'Expensas'
    : location.pathname.startsWith('/operador/escalados')
    ? 'Casos escalados'
    : location.pathname.startsWith('/operador/pendientes-asignacion')
    ? 'Candidatos'
    : location.pathname.startsWith('/propietario/reclamos')
    ? 'Autorizaciones'
    : location.pathname.includes('/contratos')
    ? 'Mis contratos'
    : location.pathname === '/inquilino/reclamos/nuevo'
      || location.pathname === '/inquilino/reclamos/confirmacion'
      ? 'Nuevo reclamo'
      : location.pathname.startsWith('/inquilino/reclamos')
        || location.pathname.startsWith('/inquilino/propiedades/')
        ? 'Mis reclamos'
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
