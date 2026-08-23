import { useCallback, useEffect, useState } from 'react'
import { Building2, Eye, Pencil, Plus, Trash2, Users } from 'lucide-react'
import { Link, useLocation, useSearchParams } from 'react-router'
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

function PropietariosListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const page = Math.max(Number(searchParams.get('page')) || 1, 1)
  const search = searchParams.get('search') ?? ''
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(location.state?.notice ?? '')
  const [loadedQuery, setLoadedQuery] = useState('')
  const [ownerToDelete, setOwnerToDelete] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const queryKey = `${page}:${search}`
  const loadOwners = useCallback((signal) => {
    return listPropietarios({ page, pageSize: PAGE_SIZE, search, signal })
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
      })
  }, [page, search])

  useEffect(() => {
    const controller = new AbortController()
    loadOwners(controller.signal)
    return () => controller.abort()
  }, [loadOwners])

  const goToPage = (nextPage) => {
    const params = new URLSearchParams(searchParams)
    params.set('page', String(nextPage))
    setSearchParams(params)
  }

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
        {error ? <AlertMessage>{error}</AlertMessage> : null}
      </div>

      {isLoading ? (
        <LoadingState label="Cargando propietarios" lines={6} />
      ) : null}

      {hasNoResults ? (
        <EmptyState
          action={
            search ? (
              <Button
                onClick={() => setSearchParams({})}
                variant="secondary"
              >
                Limpiar búsqueda
              </Button>
            ) : (
              <Link className={styles.primaryLink} to="/propietarios/nuevo">
                <Plus aria-hidden="true" />
                Registrar el primero
              </Link>
            )
          }
          description={
            search
              ? `No hay coincidencias para “${search}”. Probá con otro nombre, DNI o email.`
              : 'Registrá un propietario para comenzar a asociar sus inmuebles.'
          }
          icon={Users}
          title={search ? 'Sin resultados' : 'Todavía no hay propietarios'}
        />
      ) : null}

      {!isLoading && !error && owners.length ? (
        <section className={styles.listPanel} aria-labelledby="owners-list-title">
          <div className={styles.listSummary}>
            <div>
              <h2 id="owners-list-title">
                {search ? 'Resultados de la búsqueda' : 'Propietarios registrados'}
              </h2>
              <p>{data.total} registros en total</p>
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
