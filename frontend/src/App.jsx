import { Navigate, Route, Routes } from 'react-router'
import AdminLayout from './layouts/AdminLayout.jsx'
import AdminHomePage from './features/home/pages/AdminHomePage.jsx'
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
import ReclamoDetailPage from './features/reclamos/pages/ReclamoDetailPage.jsx'
import ReclamoFormPage from './features/reclamos/pages/ReclamoFormPage.jsx'
import ReclamosListPage from './features/reclamos/pages/ReclamosListPage.jsx'
import PropertyClaimsHistoryPage from './features/reclamos/pages/PropertyClaimsHistoryPage.jsx'
import PropertyClaimDetailPage from './features/reclamos/pages/PropertyClaimDetailPage.jsx'
import OwnerExpensesPage from './features/reclamos/pages/OwnerExpensesPage.jsx'
import OwnerExpenseDecisionPage from './features/reclamos/pages/OwnerExpenseDecisionPage.jsx'
import ProviderChoicePage from './features/reclamos/pages/ProviderChoicePage.jsx'
import ProviderActivationPage from './features/proveedores/pages/ProviderActivationPage.jsx'
import ProviderHomePage from './features/proveedores/pages/ProviderHomePage.jsx'
import ProviderQuoteDetailPage from './features/proveedores/pages/ProviderQuoteDetailPage.jsx'
import EscalatedClaimsPage from './features/reclamos/pages/EscalatedClaimsPage.jsx'
import EscalatedClaimDetailPage from './features/reclamos/pages/EscalatedClaimDetailPage.jsx'
import PendingAssignmentPage from './features/reclamos/pages/PendingAssignmentPage.jsx'
import ProviderCandidatesPage from './features/reclamos/pages/ProviderCandidatesPage.jsx'
import { useAuth } from './features/auth/authContext.js'
import { ConversationDockProvider } from './features/conversaciones/ConversationDock.jsx'
import { destinationForUser } from './features/auth/routing.js'
import ContractsListPage from './features/contratos/pages/ContractsListPage.jsx'
import ContractFormPage from './features/contratos/pages/ContractFormPage.jsx'
import ContractDetailPage from './features/contratos/pages/ContractDetailPage.jsx'
import ExpenseLayout from './features/expensas/ExpenseLayout.jsx'
import ExpensesListPage from './features/expensas/ExpensesListPage.jsx'
import ExpenseDetailPage from './features/expensas/ExpenseDetailPage.jsx'

function SessionHomeRedirect() {
  const { user } = useAuth()
  return <Navigate replace to={destinationForUser(user)} />
}

function ConversationLayer({ children }) {
  const { user } = useAuth()
  return <ConversationDockProvider key={`${user?.id}:${user?.rol}`} user={user}>{children}</ConversationDockProvider>
}

function App() {
  return (
    <AuthProvider>
      <ConversationLayer>
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route path="activar-proveedor" element={<ProviderActivationPage />} />
        <Route element={<ProtectedRoute allowedRoles={['proveedor']} />}>
          <Route element={<RoleLayout />}>
            <Route path="proveedor" element={<ProviderHomePage />} />
            <Route path="proveedor/solicitudes/:requestId" element={<ProviderQuoteDetailPage />} />
          </Route>
        </Route>
        <Route element={<ProtectedRoute allowFirstLogin />}>
          <Route path="cambiar-contrasena" element={<ChangePasswordPage />} />
        </Route>
        <Route element={<ProtectedRoute />}>
          <Route index element={<SessionHomeRedirect />} />
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['administrador', 'operador']} />}>
          <Route element={<ExpenseLayout />}>
            <Route path="expensas" element={<ExpensesListPage />} />
            <Route path="expensas/:reclamoId" element={<ExpenseDetailPage />} />
          </Route>
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['administrador']} />}>
          <Route element={<AdminLayout />}>
            <Route path="inicio" element={<AdminHomePage />} />
            <Route path="escalados" element={<EscalatedClaimsPage />} />
            <Route path="escalados/:reclamoId" element={<EscalatedClaimDetailPage />} />
            <Route path="pendientes-asignacion" element={<PendingAssignmentPage />} />
            <Route path="pendientes-asignacion/:reclamoId" element={<ProviderCandidatesPage />} />
            <Route path="contratos" element={<ContractsListPage />} />
            <Route path="contratos/nuevo" element={<ContractFormPage />} />
            <Route path="contratos/:contractId" element={<ContractDetailPage />} />
            <Route path="contratos/:contractId/editar" element={<ContractFormPage />} />
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
            <Route path="propiedades/:propiedadId/reclamos" element={<PropertyClaimsHistoryPage />} />
            <Route path="propiedades/:propiedadId/reclamos/:reclamoId" element={<PropertyClaimDetailPage />} />
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
            <Route path="propietario/reclamos" element={<OwnerExpensesPage />} />
            <Route path="propietario/reclamos/:reclamoId/autorizar" element={<OwnerExpenseDecisionPage />} />
            <Route path="propietario/reclamos/:reclamoId/tipo-proveedor" element={<ProviderChoicePage ownerView />} />
            <Route path="propietario/contratos" element={<ContractsListPage />} />
            <Route path="propietario/contratos/:contractId" element={<ContractDetailPage />} />
          </Route>
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['inquilino']} />}>
          <Route element={<RoleLayout />}>
            <Route path="inquilino" element={<RoleHomePage />} />
            <Route path="inquilino/reclamos/:reclamoId/tipo-proveedor" element={<ProviderChoicePage />} />
            <Route path="inquilino/propiedades/:propiedadId/reclamos" element={<PropertyClaimsHistoryPage tenantView />} />
            <Route path="inquilino/propiedades/:propiedadId/reclamos/:reclamoId" element={<PropertyClaimDetailPage tenantView />} />
            <Route path="inquilino/contratos" element={<ContractsListPage />} />
            <Route path="inquilino/contratos/:contractId" element={<ContractDetailPage />} />
            <Route
              path="inquilino/reclamos"
              element={<ReclamosListPage />}
            />
            <Route
              path="inquilino/reclamos/nuevo"
              element={<ReclamoFormPage />}
            />
            <Route
              path="inquilino/reclamos/confirmacion"
              element={<ReclamoConfirmationPage />}
            />
            <Route
              path="inquilino/reclamos/:reclamoId"
              element={<ReclamoDetailPage />}
            />
          </Route>
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['operador']} />}>
          <Route element={<RoleLayout />}>
            <Route path="operador" element={<RoleHomePage />} />
            <Route path="operador/escalados" element={<EscalatedClaimsPage operatorView />} />
            <Route path="operador/escalados/:reclamoId" element={<EscalatedClaimDetailPage operatorView />} />
            <Route path="operador/pendientes-asignacion" element={<PendingAssignmentPage operatorView />} />
            <Route path="operador/pendientes-asignacion/:reclamoId" element={<ProviderCandidatesPage operatorView />} />
          </Route>
        </Route>
        <Route path="design-system" element={<DesignSystemPreview />} />
      </Routes>
      </ConversationLayer>
    </AuthProvider>
  )
}

export default App
