import AdminLayout from '../../layouts/AdminLayout.jsx'
import RoleLayout from '../../layouts/RoleLayout.jsx'
import { useAuth } from '../auth/authContext.js'

export default function ExpenseLayout() {
  const { user } = useAuth()
  return user?.rol === 'administrador' ? <AdminLayout /> : <RoleLayout />
}
