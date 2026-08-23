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

function App() {
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<Navigate replace to="/propietarios" />} />
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
        <Route path="propiedades/:propiedadId" element={<PropiedadDetailPage />} />
        <Route
          path="propiedades/:propiedadId/editar"
          element={<PropiedadFormPage />}
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="design-system" element={<DesignSystemPreview />} />
    </Routes>
  )
}

export default App
