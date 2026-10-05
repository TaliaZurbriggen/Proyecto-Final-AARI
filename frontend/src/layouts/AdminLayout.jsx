import { Outlet, useLocation, useNavigate } from 'react-router'
import { AppHeader } from '../components/layout/index.js'
import { useAuth } from '../features/auth/authContext.js'

const navigationItems = [
  { href: '/inicio', label: 'Inicio' },
  { href: '/escalados', label: 'Casos escalados' },
  { href: '/propietarios', label: 'Propietarios' },
  { href: '/propiedades', label: 'Propiedades' },
  { href: '/inquilinos', label: 'Inquilinos' },
  { href: '/proveedores', label: 'Proveedores' },
  { href: '/operadores', label: 'Operadores' },
  { href: '/contratos', label: 'Contratos' },
  { href: '/expensas', label: 'Expensas' },
]

function AdminLayout() {
  const { logout, user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const isProperties = location.pathname.startsWith('/propiedades')
  const isEscalated = location.pathname.startsWith('/escalados')
  const isTenants = location.pathname.startsWith('/inquilinos')
  const isProviders = location.pathname.startsWith('/proveedores')
  const isOperators = location.pathname.startsWith('/operadores')
  const isContracts = location.pathname.startsWith('/contratos')
  const isHome = location.pathname === '/inicio'
  const isExpenses = location.pathname.startsWith('/expensas')
  const activeModule = isHome
    ? { href: '/inicio', label: 'Inicio' }
    : isExpenses
    ? { href: '/expensas', label: 'Expensas', placeholder: '' }
    : isEscalated
    ? { href: '/escalados', label: 'Casos escalados', placeholder: 'Buscar caso escalado' }
    : isContracts
    ? { href: '/contratos', label: 'Contratos', placeholder: 'Buscar inmueble o participante' }
    : isOperators
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
    const params = location.pathname === activeModule.href
      ? new URLSearchParams(location.search) : new URLSearchParams()
    params.delete('page')
    // Conservar el espacio mientras se escribe un nombre compuesto.
    // La API normaliza los extremos al consultar, no durante cada pulsación.
    if (value.trim()) params.set('search', value)
    else params.delete('search')
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
        navigationVariant="tiles"
        onNavigate={(item) => navigate(item.href)}
        onLogout={handleLogout}
        onSearchChange={(event) => updateSearch(event.target.value)}
        onSearchClear={() => updateSearch('')}
        profileName={user?.email ?? 'Usuario administrador'}
        profileRole="Administración"
        searchPlaceholder={activeModule.placeholder}
        searchValue={searchValue}
        showSearch={!isHome && !isExpenses && !isEscalated}
        showNotifications={!isHome}
      />
      <Outlet />
    </>
  )
}

export default AdminLayout
