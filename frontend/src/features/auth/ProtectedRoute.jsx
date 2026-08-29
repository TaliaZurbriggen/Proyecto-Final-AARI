import { Navigate, Outlet, useLocation } from 'react-router'
import LoadingState from '../../components/ui/LoadingState.jsx'
import styles from './ProtectedRoute.module.css'
import { useAuth } from './authContext.js'

function ProtectedRoute({ allowedRoles = [] }) {
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

  if (allowedRoles.length > 0 && !allowedRoles.includes(user.rol)) {
    return <Navigate replace to="/login" />
  }

  return <Outlet />
}

export default ProtectedRoute
