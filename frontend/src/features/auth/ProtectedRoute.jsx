import { Navigate, Outlet, useLocation } from 'react-router'
import LoadingState from '../../components/ui/LoadingState.jsx'
import styles from './ProtectedRoute.module.css'
import { useAuth } from './authContext.js'
import { homePathForRole } from './routing.js'

function ProtectedRoute({ allowFirstLogin = false, allowedRoles = [] }) {
  const { isLoading, user } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <main className={styles.loading}>
        <LoadingState label="Comprobando tu sesión" />
      </main>
    )
  }

  if (!user) {
    return <Navigate replace state={{ from: location }} to="/login" />
  }

  if (user.primer_ingreso && !allowFirstLogin) {
    return <Navigate replace to="/cambiar-contrasena" />
  }

  if (allowedRoles.length > 0 && !allowedRoles.includes(user.rol)) {
    return <Navigate replace to={homePathForRole(user.rol)} />
  }

  return <Outlet />
}

export default ProtectedRoute
