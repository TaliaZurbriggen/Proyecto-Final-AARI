import { Outlet, useLocation, useNavigate } from 'react-router'
import { AppHeader } from '../components/layout/index.js'

const navigationItems = [
  { href: '/propietarios', label: 'Propietarios' },
  { href: '/propiedades', label: 'Propiedades' },
]

function AdminLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const isProperties = location.pathname.startsWith('/propiedades')
  const activeModule = isProperties
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

  return (
    <>
      <AppHeader
        activeItem={activeModule.label}
        items={navigationItems}
        onNavigate={(item) => navigate(item.href)}
        onSearchChange={(event) => updateSearch(event.target.value)}
        onSearchClear={() => updateSearch('')}
        profileName="Usuario administrador"
        profileRole="Administración"
        searchPlaceholder={activeModule.placeholder}
        searchValue={searchValue}
      />
      <Outlet />
    </>
  )
}

export default AdminLayout
