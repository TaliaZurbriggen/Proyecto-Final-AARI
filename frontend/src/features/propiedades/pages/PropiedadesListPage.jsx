import { useCallback, useEffect, useState } from 'react'
import { Building2, Eye, Pencil, Plus, Trash2 } from 'lucide-react'
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
import { deletePropiedad, listPropiedades } from '../api/propiedadesApi.js'
import styles from './Propiedades.module.css'

const PAGE_SIZE = 10
const TYPE_LABELS = {
  departamento: 'Departamento',
  casa: 'Casa',
  local: 'Local',
  otro: 'Otro',
}

function unitSummary(property) {
  const hasFloor = property.piso !== null && property.piso !== undefined
  return [
    hasFloor
      ? property.piso === 0
        ? 'Planta baja (piso 0)'
        : `Piso ${property.piso}`
      : null,
    property.numero ? `Unidad ${property.numero}` : null,
  ]
    .filter(Boolean)
    .join(' · ')
}

function PropiedadesListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const page = Math.max(Number(searchParams.get('page')) || 1, 1)
  const search = searchParams.get('search') ?? ''
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(location.state?.notice ?? '')
  const [loadedQuery, setLoadedQuery] = useState('')
  const [propertyToDelete, setPropertyToDelete] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const queryKey = `${page}:${search}`
  const loadProperties = useCallback(
    (signal) =>
      listPropiedades({ page, pageSize: PAGE_SIZE, search, signal })
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
    loadProperties(controller.signal)
    return () => controller.abort()
  }, [loadProperties])

  const goToPage = (nextPage) => {
    const params = new URLSearchParams(searchParams)
    params.set('page', String(nextPage))
    setSearchParams(params)
  }

  const requestDelete = (property) => {
    setNotice('')
    if (property.cantidad_reclamos > 0) {
      setError(
        'No se puede eliminar la propiedad porque tiene reclamos históricos asociados.',
      )
      return
    }
    if (property.tiene_inquilino_activo) {
      setError('No se puede eliminar la propiedad porque tiene un inquilino activo.')
      return
    }
    setError('')
    setPropertyToDelete(property)
  }

  const handleDelete = async () => {
    if (!propertyToDelete) return
    setIsDeleting(true)
    try {
      await deletePropiedad(propertyToDelete.id)
      setPropertyToDelete(null)
      setNotice('La propiedad se eliminó correctamente.')
      await loadProperties()
    } catch (requestError) {
      setPropertyToDelete(null)
      setError(requestError.message)
    } finally {
      setIsDeleting(false)
    }
  }

  const properties = data?.items ?? []
  const isLoading = loadedQuery !== queryKey
  const hasNoResults = !isLoading && !error && properties.length === 0

  return (
    <PageContainer>
      <PageHeading
        action={
          <Link className={styles.primaryLink} to="/propiedades/nueva">
            <Plus aria-hidden="true" />
            Nueva propiedad
          </Link>
        }
        description="Administrá los inmuebles, su ubicación y el propietario asociado."
        eyebrow="Administración"
        title="Propiedades"
      />

      <div className={styles.feedbackStack}>
        {notice ? <AlertMessage tone="success">{notice}</AlertMessage> : null}
        {error ? <AlertMessage>{error}</AlertMessage> : null}
      </div>

      {isLoading ? <LoadingState label="Cargando propiedades" lines={6} /> : null}

      {hasNoResults ? (
        <EmptyState
          action={
            search ? (
              <Button onClick={() => setSearchParams({})} variant="secondary">
                Limpiar búsqueda
              </Button>
            ) : (
              <Link className={styles.primaryLink} to="/propiedades/nueva">
                <Plus aria-hidden="true" />
                Registrar la primera
              </Link>
            )
          }
          description={
            search
              ? `No hay coincidencias para “${search}”. Probá con otra dirección o ubicación.`
              : 'Registrá una propiedad para comenzar a asociar inquilinos y reclamos.'
          }
          icon={Building2}
          title={search ? 'Sin resultados' : 'Todavía no hay propiedades'}
        />
      ) : null}

      {!isLoading && properties.length ? (
        <section className={styles.listPanel} aria-labelledby="properties-list-title">
          <div className={styles.listSummary}>
            <div>
              <h2 id="properties-list-title">
                {search ? 'Resultados de la búsqueda' : 'Propiedades registradas'}
              </h2>
              <p>{data.total} registros en total</p>
            </div>
          </div>

          <div className={styles.tableRegion}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Dirección</th>
                  <th>Ubicación</th>
                  <th>Tipo</th>
                  <th>Propietario</th>
                  <th><span className="aari-sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {properties.map((property) => (
                  <tr key={property.id}>
                    <td data-label="Dirección">
                      <Link className={styles.propertyLink} to={`/propiedades/${property.id}`}>
                        {property.direccion}
                      </Link>
                      {property.tipo === 'departamento' && unitSummary(property) ? (
                        <small className={styles.secondaryCopy}>
                          {unitSummary(property)}
                        </small>
                      ) : null}
                    </td>
                    <td data-label="Ubicación">
                      {property.localidad}, {property.provincia}
                      {property.barrio ? (
                        <small className={styles.secondaryCopy}>
                          Barrio {property.barrio}
                        </small>
                      ) : null}
                    </td>
                    <td data-label="Tipo">
                      <StatusBadge tone="info">{TYPE_LABELS[property.tipo]}</StatusBadge>
                    </td>
                    <td data-label="Propietario">
                      <Link
                        className={styles.ownerLink}
                        to={`/propietarios/${property.propietario.id}`}
                      >
                        {property.propietario.nombre_completo}
                      </Link>
                    </td>
                    <td className={styles.actionsCell}>
                      <Link
                        aria-label={`Ver ${property.direccion}`}
                        className={styles.iconLink}
                        to={`/propiedades/${property.id}`}
                      >
                        <Eye aria-hidden="true" />
                      </Link>
                      <Link
                        aria-label={`Editar ${property.direccion}`}
                        className={styles.iconLink}
                        to={`/propiedades/${property.id}/editar`}
                      >
                        <Pencil aria-hidden="true" />
                      </Link>
                      <IconButton
                        label={`Eliminar ${property.direccion}`}
                        onClick={() => requestDelete(property)}
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
            <nav className={styles.pagination} aria-label="Paginación de propiedades">
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
        confirmLabel="Eliminar propiedad"
        description={
          propertyToDelete
            ? `Vas a eliminar ${propertyToDelete.direccion}. Esta acción no se puede deshacer.`
            : ''
        }
        isBusy={isDeleting}
        onCancel={() => setPropertyToDelete(null)}
        onConfirm={handleDelete}
        open={Boolean(propertyToDelete)}
        title="¿Eliminar propiedad?"
      />
    </PageContainer>
  )
}

export default PropiedadesListPage
