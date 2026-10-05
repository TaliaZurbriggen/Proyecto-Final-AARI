import { useCallback, useEffect, useRef, useState } from 'react'
import { Building2, Eye, Pencil, Plus, Trash2, Users } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import ListFilterPanel from '../../../components/ui/ListFilterPanel.jsx'
import { useListFilters } from '../../../hooks/useListFilters.js'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  LoadingState,
} from '../../../components/ui/index.js'
import {
  deletePropietario,
  listPropietarios,
} from '../api/propietariosApi.js'
import styles from './Propietarios.module.css'

const PAGE_SIZE = 10
const FILTER_FIELDS = [{ name: 'con_inmuebles', label: 'Inmuebles asociados', options: [
  { value: 'true', label: 'Con inmuebles' }, { value: 'false', label: 'Sin inmuebles' },
] }]

function PropietariosListPage() {
  const location = useLocation()
  const { page, search, filters, panelKey, queryKey, hasFilters, applyFilters, clearFilters, goToPage, normalizePage } = useListFilters(FILTER_FIELDS)
  const requestSequence = useRef(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(location.state?.notice ?? '')
  const [loadedQuery, setLoadedQuery] = useState('')
  const [ownerToDelete, setOwnerToDelete] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const loadOwners = useCallback((signal) => {
    const requestId = ++requestSequence.current
    return listPropietarios({ page, pageSize: PAGE_SIZE, search, filters, signal })
      .then((result) => {
        if (signal?.aborted || requestId !== requestSequence.current) return
        if (normalizePage(result.total_pages)) return
        setData(result)
        setError('')
        setLoadedQuery(queryKey)
      })
      .catch((requestError) => {
        if (!signal?.aborted && requestId === requestSequence.current && requestError.name !== 'AbortError') {
          setData(null)
          setError(requestError.message)
          setLoadedQuery(queryKey)
        }
      })
  }, [page, search, filters, queryKey, normalizePage])

  useEffect(() => {
    const controller = new AbortController()
    loadOwners(controller.signal)
    return () => controller.abort()
  }, [loadOwners])

  const handleDelete = async () => {
    if (!ownerToDelete) return
    setIsDeleting(true)
    setError('')
    try {
      await deletePropietario(ownerToDelete.id)
      setOwnerToDelete(null)
      setNotice('El propietario se eliminó correctamente.')
      await loadOwners()
    } catch (requestError) {
      setOwnerToDelete(null)
      setError(requestError.message)
    } finally {
      setIsDeleting(false)
    }
  }

  const owners = data?.items ?? []
  const isLoading = loadedQuery !== queryKey
  const hasNoResults = !isLoading && !error && owners.length === 0

  return (
    <PageContainer>
      <PageHeading
        action={
          <Link className={styles.primaryLink} to="/propietarios/nuevo">
            <Plus aria-hidden="true" />
            Nuevo propietario
          </Link>
        }
        description="Administrá sus datos de contacto y consultá los inmuebles asociados."
        eyebrow="Administración"
        title="Propietarios"
      />

      <div className={styles.feedbackStack}>
        {notice ? <AlertMessage tone="success">{notice}</AlertMessage> : null}
        {!isLoading && error ? <AlertMessage>{error}</AlertMessage> : null}
      </div>

      <ListFilterPanel key={panelKey} title="Filtros de propietarios" fields={FILTER_FIELDS}
        search={search} searchLabel="Buscar propietario" searchPlaceholder="Nombre, DNI o email"
        values={filters} hasSearch={Boolean(search)} onApply={applyFilters} onClear={clearFilters}
        description="Buscá por nombre, DNI o email y combiná la búsqueda con los inmuebles asociados." />

      {isLoading ? (
        <LoadingState label="Cargando propietarios" lines={6} />
      ) : null}

      {hasNoResults ? (
        <EmptyState
          action={
            hasFilters ? (
              <Button
                onClick={clearFilters}
                variant="secondary"
              >
                Limpiar búsqueda y filtros
              </Button>
            ) : (
              <Link className={styles.primaryLink} to="/propietarios/nuevo">
                <Plus aria-hidden="true" />
                Registrar el primero
              </Link>
            )
          }
          description={
            hasFilters
              ? 'No hay propietarios que cumplan todos los criterios. Probá modificarlos o limpiarlos.'
              : 'Registrá un propietario para comenzar a asociar sus inmuebles.'
          }
          icon={Users}
          title={hasFilters ? 'Sin resultados' : 'Todavía no hay propietarios'}
        />
      ) : null}

      {!isLoading && !error && owners.length ? (
        <section className={styles.listPanel} aria-labelledby="owners-list-title">
          <div className={styles.listSummary}>
            <div>
              <h2 id="owners-list-title">
                {hasFilters ? 'Resultados de la búsqueda' : 'Propietarios registrados'}
              </h2>
              <p>{data.total} {hasFilters ? 'coincidencias' : 'registros en total'}</p>
            </div>
          </div>

          <div className={styles.tableRegion}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>DNI</th>
                  <th>Email</th>
                  <th>Inmuebles</th>
                  <th><span className="aari-sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {owners.map((owner) => (
                  <tr key={owner.id}>
                    <td data-label="Nombre">
                      <Link className={styles.ownerLink} to={`/propietarios/${owner.id}`}>
                        {owner.nombre_completo}
                      </Link>
                    </td>
                    <td data-label="DNI">{owner.dni}</td>
                    <td data-label="Email">
                      <a className={styles.emailLink} href={`mailto:${owner.email}`}>
                        {owner.email}
                      </a>
                    </td>
                    <td data-label="Inmuebles">
                      <span className={styles.propertyCount}>
                        <Building2 aria-hidden="true" />
                        {owner.cantidad_inmuebles}
                      </span>
                    </td>
                    <td className={styles.actionsCell}>
                      <Link
                        aria-label={`Ver detalle de ${owner.nombre_completo}`}
                        className={styles.iconLink}
                        to={`/propietarios/${owner.id}`}
                      >
                        <Eye aria-hidden="true" />
                      </Link>
                      <Link
                        aria-label={`Editar ${owner.nombre_completo}`}
                        className={styles.iconLink}
                        to={`/propietarios/${owner.id}/editar`}
                      >
                        <Pencil aria-hidden="true" />
                      </Link>
                      <IconButton
                        label={`Eliminar ${owner.nombre_completo}`}
                        onClick={() => setOwnerToDelete(owner)}
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
            <nav className={styles.pagination} aria-label="Paginación de propietarios">
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
                disabled={page >= data.total_pages}
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
        confirmLabel="Eliminar propietario"
        description={
          ownerToDelete
            ? `Vas a eliminar a ${ownerToDelete.nombre_completo}. Esta acción no se puede deshacer.`
            : ''
        }
        isBusy={isDeleting}
        onCancel={() => setOwnerToDelete(null)}
        onConfirm={handleDelete}
        open={Boolean(ownerToDelete)}
        title="¿Eliminar propietario?"
      />
    </PageContainer>
  )
}

export default PropietariosListPage
