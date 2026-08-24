import { useCallback, useEffect, useState } from 'react'
import { Eye, Pencil, Plus, Trash2, UserRound } from 'lucide-react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  LoadingState,
  StatusBadge,
} from '../../../components/ui/index.js'
import { deleteInquilino, listInquilinos } from '../api/inquilinosApi.js'
import styles from './Inquilinos.module.css'

const PAGE_SIZE = 10

function propertySummary(property) {
  if (!property) return 'Sin propiedad asignada'
  const unit = property.tipo === 'departamento'
    ? [
        property.piso === 0 ? 'PB' : property.piso != null ? `Piso ${property.piso}` : null,
        property.numero ? `Unidad ${property.numero}` : null,
      ].filter(Boolean).join(' · ')
    : ''
  return `${property.direccion}${unit ? ` · ${unit}` : ''}`
}

function InquilinosListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const page = Math.max(Number(searchParams.get('page')) || 1, 1)
  const search = searchParams.get('search') ?? ''
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(location.state?.notice ?? '')
  const [loadedQuery, setLoadedQuery] = useState('')
  const [tenantToDelete, setTenantToDelete] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const queryKey = `${page}:${search}`
  const loadTenants = useCallback(
    (signal) =>
      listInquilinos({ page, pageSize: PAGE_SIZE, search, signal })
        .then((result) => {
          setData(result)
          setError('')
          setLoadedQuery(`${page}:${search}`)
        })
        .catch((requestError) => {
          if (requestError.name !== 'AbortError') {
            setError(requestError.message)
            setLoadedQuery(`${page}:${search}`)
          }
        }),
    [page, search],
  )

  useEffect(() => {
    const controller = new AbortController()
    loadTenants(controller.signal)
    return () => controller.abort()
  }, [loadTenants])

  const goToPage = (nextPage) => {
    const params = new URLSearchParams(searchParams)
    params.set('page', String(nextPage))
    setSearchParams(params)
  }

  const requestDelete = (tenant) => {
    setNotice('')
    if (tenant.cantidad_reclamos > 0) {
      setError(
        'No se puede eliminar el inquilino porque tiene reclamos históricos. Podés desasociarlo desde su detalle.',
      )
      return
    }
    setError('')
    setTenantToDelete(tenant)
  }

  const handleDelete = async () => {
    if (!tenantToDelete) return
    setIsDeleting(true)
    try {
      await deleteInquilino(tenantToDelete.id)
      setTenantToDelete(null)
      setNotice('El inquilino se eliminó correctamente.')
      await loadTenants()
    } catch (requestError) {
      setTenantToDelete(null)
      setError(requestError.message)
    } finally {
      setIsDeleting(false)
    }
  }

  const tenants = data?.items ?? []
  const isLoading = loadedQuery !== queryKey
  const hasNoResults = !isLoading && !error && tenants.length === 0

  return (
    <PageContainer>
      <PageHeading
        action={
          <Link className={styles.primaryLink} to="/inquilinos/nuevo">
            <Plus aria-hidden="true" />
            Nuevo inquilino
          </Link>
        }
        description="Administrá los datos de contacto y la propiedad asignada a cada persona."
        eyebrow="Administración"
        title="Inquilinos"
      />

      <div className={styles.feedbackStack}>
        {notice ? <AlertMessage tone="success">{notice}</AlertMessage> : null}
        {error ? <AlertMessage>{error}</AlertMessage> : null}
      </div>

      {isLoading ? <LoadingState label="Cargando inquilinos" lines={6} /> : null}

      {hasNoResults ? (
        <EmptyState
          action={
            search ? (
              <Button onClick={() => setSearchParams({})} variant="secondary">
                Limpiar búsqueda
              </Button>
            ) : (
              <Link className={styles.primaryLink} to="/inquilinos/nuevo">
                <Plus aria-hidden="true" />
                Registrar el primero
              </Link>
            )
          }
          description={
            search
              ? `No hay coincidencias para “${search}”. Probá con otro nombre, DNI o propiedad.`
              : 'Registrá un inquilino y asignalo a una propiedad disponible.'
          }
          icon={UserRound}
          title={search ? 'Sin resultados' : 'Todavía no hay inquilinos'}
        />
      ) : null}

      {!isLoading && tenants.length ? (
        <section className={styles.listPanel} aria-labelledby="tenants-list-title">
          <div className={styles.listSummary}>
            <div>
              <h2 id="tenants-list-title">
                {search ? 'Resultados de la búsqueda' : 'Inquilinos registrados'}
              </h2>
              <p>{data.total} registros en total</p>
            </div>
          </div>

          <div className={styles.tableRegion}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Inquilino</th>
                  <th>Contacto</th>
                  <th>Propiedad</th>
                  <th>Estado</th>
                  <th><span className="aari-sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {tenants.map((tenant) => (
                  <tr key={tenant.id}>
                    <td data-label="Inquilino">
                      <Link className={styles.tenantLink} to={`/inquilinos/${tenant.id}`}>
                        {tenant.nombre_completo}
                      </Link>
                      <small className={styles.secondaryCopy}>DNI {tenant.dni}</small>
                    </td>
                    <td data-label="Contacto">
                      {tenant.email}
                      <small className={styles.secondaryCopy}>{tenant.telefono}</small>
                    </td>
                    <td data-label="Propiedad">
                      {tenant.propiedad ? (
                        <Link
                          className={styles.propertyLink}
                          to={`/propiedades/${tenant.propiedad.id}`}
                        >
                          {propertySummary(tenant.propiedad)}
                        </Link>
                      ) : (
                        'Sin asignar'
                      )}
                    </td>
                    <td data-label="Estado">
                      <StatusBadge tone={tenant.estado === 'activo' ? 'success' : 'warning'}>
                        {tenant.estado === 'activo' ? 'Activo' : 'Sin propiedad'}
                      </StatusBadge>
                    </td>
                    <td className={styles.actionsCell}>
                      <Link
                        aria-label={`Ver ${tenant.nombre_completo}`}
                        className={styles.iconLink}
                        to={`/inquilinos/${tenant.id}`}
                      >
                        <Eye aria-hidden="true" />
                      </Link>
                      <Link
                        aria-label={`Editar ${tenant.nombre_completo}`}
                        className={styles.iconLink}
                        to={`/inquilinos/${tenant.id}/editar`}
                      >
                        <Pencil aria-hidden="true" />
                      </Link>
                      <IconButton
                        label={`Eliminar ${tenant.nombre_completo}`}
                        onClick={() => requestDelete(tenant)}
                        variant="ghost"
                      >
                        <Trash2 />
                      </IconButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.total_pages > 1 ? (
            <nav className={styles.pagination} aria-label="Paginación de inquilinos">
              <Button
                disabled={page === 1}
                onClick={() => goToPage(page - 1)}
                size="sm"
                variant="secondary"
              >
                Anterior
              </Button>
              <span>Página {page} de {data.total_pages}</span>
              <Button
                disabled={page === data.total_pages}
                onClick={() => goToPage(page + 1)}
                size="sm"
                variant="secondary"
              >
                Siguiente
              </Button>
            </nav>
          ) : null}
        </section>
      ) : null}

      <ConfirmDialog
        confirmLabel="Eliminar inquilino"
        description={
          tenantToDelete
            ? `Vas a eliminar a ${tenantToDelete.nombre_completo}. Esta acción no se puede deshacer.`
            : ''
        }
        isBusy={isDeleting}
        onCancel={() => setTenantToDelete(null)}
        onConfirm={handleDelete}
        open={Boolean(tenantToDelete)}
        title="¿Eliminar inquilino?"
      />
    </PageContainer>
  )
}

export default InquilinosListPage
