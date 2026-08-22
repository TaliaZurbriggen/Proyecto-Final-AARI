import { Outlet, useLocation, useNavigate } from 'react-router'
import { AppHeader } from '../components/layout/index.js'

const navigationItems = [{ href: '/propietarios', label: 'Propietarios' }]

function AdminLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const searchValue = new URLSearchParams(location.search).get('search') ?? ''

  const updateSearch = (value) => {
    const params = new URLSearchParams()
    if (value.trim()) params.set('search', value.trim())
    const suffix = params.toString() ? `?${params.toString()}` : ''
    navigate(`/propietarios${suffix}`, { replace: true })
  }

  return (
    <>
      <AppHeader
        activeItem={
          location.pathname.startsWith('/propietarios') ? 'Propietarios' : ''
        }
        items={navigationItems}
        onNavigate={(item) => navigate(item.href)}
        onSearchChange={(event) => updateSearch(event.target.value)}
        onSearchClear={() => updateSearch('')}
        profileName="Usuario administrador"
        profileRole="Administración"
        searchPlaceholder="Buscar propietario"
        searchValue={searchValue}
      />
      <Outlet />
    </>
  )
}

export default AdminLayout
