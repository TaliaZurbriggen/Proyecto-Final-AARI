import { Navigate, Route, Routes } from 'react-router'
import AdminLayout from './layouts/AdminLayout.jsx'
import DesignSystemPreview from './pages/DesignSystemPreview.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import PropietarioDetailPage from './features/propietarios/pages/PropietarioDetailPage.jsx'
import PropietarioFormPage from './features/propietarios/pages/PropietarioFormPage.jsx'
import PropietariosListPage from './features/propietarios/pages/PropietariosListPage.jsx'
import PropiedadDetailPage from './features/propiedades/pages/PropiedadDetailPage.jsx'
import PropiedadFormPage from './features/propiedades/pages/PropiedadFormPage.jsx'
import PropiedadesListPage from './features/propiedades/pages/PropiedadesListPage.jsx'
import InquilinoDetailPage from './features/inquilinos/pages/InquilinoDetailPage.jsx'
import InquilinoFormPage from './features/inquilinos/pages/InquilinoFormPage.jsx'
import InquilinosListPage from './features/inquilinos/pages/InquilinosListPage.jsx'
import ProveedorDetailPage from './features/proveedores/pages/ProveedorDetailPage.jsx'
import ProveedorFormPage from './features/proveedores/pages/ProveedorFormPage.jsx'
import ProveedoresListPage from './features/proveedores/pages/ProveedoresListPage.jsx'
import OperadoresListPage from './features/operadores/pages/OperadoresListPage.jsx'
import OperadorFormPage from './features/operadores/pages/OperadorFormPage.jsx'
import { AuthProvider } from './features/auth/AuthContext.jsx'
import ProtectedRoute from './features/auth/ProtectedRoute.jsx'
import LoginPage from './features/auth/pages/LoginPage.jsx'
import ChangePasswordPage from './features/auth/pages/ChangePasswordPage.jsx'
import RoleHomePage from './features/auth/pages/RoleHomePage.jsx'
import RoleLayout from './layouts/RoleLayout.jsx'
import ReclamoConfirmationPage from './features/reclamos/pages/ReclamoConfirmationPage.jsx'
import ReclamoFormPage from './features/reclamos/pages/ReclamoFormPage.jsx'
import { useAuth } from './features/auth/authContext.js'
import { destinationForUser } from './features/auth/routing.js'

function SessionHomeRedirect() {
  const { user } = useAuth()
  return <Navigate replace to={destinationForUser(user)} />
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route element={<ProtectedRoute allowFirstLogin />}>
          <Route path="cambiar-contrasena" element={<ChangePasswordPage />} />
        </Route>
        <Route element={<ProtectedRoute />}>
          <Route index element={<SessionHomeRedirect />} />
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['administrador']} />}>
          <Route element={<AdminLayout />}>
            <Route path="operadores" element={<OperadoresListPage />} />
            <Route path="operadores/nuevo" element={<OperadorFormPage />} />
            <Route path="propietarios" element={<PropietariosListPage />} />
            <Route path="propietarios/nuevo" element={<PropietarioFormPage />} />
            <Route
              path="propietarios/:propietarioId"
              element={<PropietarioDetailPage />}
            />
            <Route
              path="propietarios/:propietarioId/editar"
              element={<PropietarioFormPage />}
            />
            <Route path="propiedades" element={<PropiedadesListPage />} />
            <Route path="propiedades/nueva" element={<PropiedadFormPage />} />
            <Route
              path="propiedades/:propiedadId"
              element={<PropiedadDetailPage />}
            />
            <Route
              path="propiedades/:propiedadId/editar"
              element={<PropiedadFormPage />}
            />
            <Route path="inquilinos" element={<InquilinosListPage />} />
            <Route path="inquilinos/nuevo" element={<InquilinoFormPage />} />
            <Route
              path="inquilinos/:inquilinoId"
              element={<InquilinoDetailPage />}
            />
            <Route
              path="inquilinos/:inquilinoId/editar"
              element={<InquilinoFormPage />}
            />
            <Route path="proveedores" element={<ProveedoresListPage />} />
            <Route path="proveedores/nuevo" element={<ProveedorFormPage />} />
            <Route
              path="proveedores/:proveedorId"
              element={<ProveedorDetailPage />}
            />
            <Route
              path="proveedores/:proveedorId/editar"
              element={<ProveedorFormPage />}
            />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['propietario']} />}>
          <Route element={<RoleLayout />}>
            <Route path="propietario" element={<RoleHomePage />} />
          </Route>
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['inquilino']} />}>
          <Route element={<RoleLayout />}>
            <Route path="inquilino" element={<RoleHomePage />} />
            <Route
              path="inquilino/reclamos/nuevo"
              element={<ReclamoFormPage />}
            />
            <Route
              path="inquilino/reclamos/confirmacion"
              element={<ReclamoConfirmationPage />}
            />
          </Route>
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['operador']} />}>
          <Route element={<RoleLayout />}>
            <Route path="operador" element={<RoleHomePage />} />
          </Route>
        </Route>
        <Route path="design-system" element={<DesignSystemPreview />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
