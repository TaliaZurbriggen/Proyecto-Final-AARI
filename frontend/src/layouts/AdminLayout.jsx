import { Outlet, useLocation, useNavigate } from 'react-router'
import { AppHeader } from '../components/layout/index.js'
import { useAuth } from '../features/auth/authContext.js'

const navigationItems = [
  { href: '/propietarios', label: 'Propietarios' },
  { href: '/propiedades', label: 'Propiedades' },
  { href: '/inquilinos', label: 'Inquilinos' },
  { href: '/proveedores', label: 'Proveedores' },
  { href: '/operadores', label: 'Operadores' },
]

function AdminLayout() {
  const { logout, user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const isProperties = location.pathname.startsWith('/propiedades')
  const isTenants = location.pathname.startsWith('/inquilinos')
  const isProviders = location.pathname.startsWith('/proveedores')
  const isOperators = location.pathname.startsWith('/operadores')
  const activeModule = isOperators
    ? { href: '/operadores', label: 'Operadores', placeholder: 'Buscar operador por nombre o email' }
    : isProviders
    ? {
        href: '/proveedores',
        label: 'Proveedores',
        placeholder: 'Buscar proveedor, teléfono o matrícula',
      }
    : isTenants
    ? {
        href: '/inquilinos',
        label: 'Inquilinos',
        placeholder: 'Buscar inquilino, DNI o propiedad',
      }
    : isProperties
    ? {
        href: '/propiedades',
        label: 'Propiedades',
        placeholder: 'Buscar por dirección o ubicación',
      }
    : {
        href: '/propietarios',
        label: 'Propietarios',
        placeholder: 'Buscar propietario',
      }
  const searchValue = new URLSearchParams(location.search).get('search') ?? ''

  const updateSearch = (value) => {
    const params = new URLSearchParams()
    if (value.trim()) params.set('search', value.trim())
    const suffix = params.toString() ? `?${params.toString()}` : ''
    navigate(`${activeModule.href}${suffix}`, { replace: true })
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <AppHeader
        activeItem={activeModule.label}
        items={navigationItems}
        onNavigate={(item) => navigate(item.href)}
        onLogout={handleLogout}
        onSearchChange={(event) => updateSearch(event.target.value)}
        onSearchClear={() => updateSearch('')}
        profileName={user?.email ?? 'Usuario administrador'}
        profileRole="Administración"
        searchPlaceholder={activeModule.placeholder}
        searchValue={searchValue}
      />
      <Outlet />
    </>
  )
}

export default AdminLayout
