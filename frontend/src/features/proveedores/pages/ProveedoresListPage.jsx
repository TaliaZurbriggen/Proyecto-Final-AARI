import { useCallback, useEffect, useState } from 'react'
import { Eye, Pencil, Plus, SlidersHorizontal, UsersRound } from 'lucide-react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  EmptyState,
  LoadingState,
  SelectInput,
  StatusBadge,
  TextInput,
} from '../../../components/ui/index.js'
import { PROVINCIAS_ARGENTINAS } from '../../propiedades/provincias.js'
import { listEspecialidades, listProveedores } from '../api/proveedoresApi.js'
import styles from './Proveedores.module.css'

const PAGE_SIZE = 10

function coverageSummary(coverages) {
  if (!coverages.length) return 'Sin cobertura informada'
  const first = coverages[0]
  const scope = first.cubre_toda_localidad
    ? 'Toda la localidad'
    : first.barrios.join(', ')
  const suffix = coverages.length > 1 ? ` · +${coverages.length - 1} zonas` : ''
  return `${first.localidad}, ${first.provincia} · ${scope}${suffix}`
}

function ProveedoresListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const page = Math.max(Number(searchParams.get('page')) || 1, 1)
  const search = searchParams.get('search') ?? ''
  const especialidadId = searchParams.get('especialidad_id') ?? ''
  const provincia = searchParams.get('provincia') ?? ''
  const localidad = searchParams.get('localidad') ?? ''
  const barrio = searchParams.get('barrio') ?? ''
  const activo = searchParams.get('activo') ?? ''
  const [filters, setFilters] = useState({
    especialidadId,
    provincia,
    localidad,
    barrio,
    activo,
  })
  const [data, setData] = useState(null)
  const [specialties, setSpecialties] = useState([])
  const [error, setError] = useState('')
  const [notice] = useState(location.state?.notice ?? '')
  const [loadedQuery, setLoadedQuery] = useState('')
  const queryKey = [page, search, especialidadId, provincia, localidad, barrio, activo].join(':')

  const loadProviders = useCallback(
    (signal) => {
      return Promise.all([
        listProveedores({ page, pageSize: PAGE_SIZE, search, especialidadId, provincia, localidad, barrio, activo, signal }),
        listEspecialidades({ signal }),
      ])
        .then(([result, specialtyItems]) => {
          setData(result)
          setSpecialties(specialtyItems)
          setError('')
          setLoadedQuery(queryKey)
        })
        .catch((requestError) => {
          if (requestError.name !== 'AbortError') {
            setError(requestError.message)
            setLoadedQuery(queryKey)
          }
        })
    },
    [page, search, especialidadId, provincia, localidad, barrio, activo, queryKey],
  )

  useEffect(() => {
    const controller = new AbortController()
    loadProviders(controller.signal)
    return () => controller.abort()
  }, [loadProviders])

  const applyFilters = (event) => {
    event.preventDefault()
    const params = new URLSearchParams()
    if (search.trim()) params.set('search', search.trim())
    Object.entries(filters).forEach(([key, value]) => {
      if (value.trim()) {
        const paramName = key === 'especialidadId' ? 'especialidad_id' : key
        params.set(paramName, value.trim())
      }
    })
    setSearchParams(params)
  }

  const clearFilters = () => {
    setFilters({ especialidadId: '', provincia: '', localidad: '', barrio: '', activo: '' })
    setSearchParams({})
  }

  const goToPage = (nextPage) => {
    const params = new URLSearchParams(searchParams)
    params.set('page', String(nextPage))
    setSearchParams(params)
  }

  const providers = data?.items ?? []
  const isLoading = loadedQuery !== queryKey
  const hasFilters = Boolean(search || especialidadId || provincia || localidad || barrio || activo)

  return (
    <PageContainer>
      <PageHeading
        action={
          <Link className={styles.primaryLink} to="/proveedores/nuevo">
            <Plus aria-hidden="true" />
            Nuevo proveedor
          </Link>
        }
        description="Administrá prestadores, especialidades, cobertura y disponibilidad general."
        eyebrow="Administración"
        title="Proveedores"
      />

      <div className={styles.feedbackStack}>
        {notice ? <AlertMessage tone="success">{notice}</AlertMessage> : null}
        {error ? <AlertMessage>{error}</AlertMessage> : null}
      </div>

      <form className={styles.filtersPanel} onSubmit={applyFilters}>
        <div className={styles.filtersHeading}>
          <SlidersHorizontal aria-hidden="true" />
          <div>
            <h2>Filtrar proveedores</h2>
            <p>Combiná especialidad, ubicación y estado.</p>
          </div>
        </div>
        <div className={styles.filtersGrid}>
          <label>
            <span>Especialidad</span>
            <SelectInput value={filters.especialidadId} onChange={(event) => setFilters((current) => ({ ...current, especialidadId: event.target.value }))}>
              <option value="">Todas</option>
              {specialties.map((specialty) => <option key={specialty.id} value={specialty.id}>{specialty.nombre}</option>)}
            </SelectInput>
          </label>
          <label>
            <span>Provincia</span>
            <SelectInput value={filters.provincia} onChange={(event) => setFilters((current) => ({ ...current, provincia: event.target.value }))}>
              <option value="">Todas</option>
              {PROVINCIAS_ARGENTINAS.map((province) => <option key={province}>{province}</option>)}
            </SelectInput>
          </label>
          <label>
            <span>Localidad</span>
            <TextInput placeholder="Ej. San Francisco" value={filters.localidad} onChange={(event) => setFilters((current) => ({ ...current, localidad: event.target.value }))} />
          </label>
          <label>
            <span>Barrio</span>
            <TextInput placeholder="Ej. Centro" value={filters.barrio} onChange={(event) => setFilters((current) => ({ ...current, barrio: event.target.value }))} />
          </label>
          <label>
            <span>Estado</span>
            <SelectInput value={filters.activo} onChange={(event) => setFilters((current) => ({ ...current, activo: event.target.value }))}>
              <option value="">Todos</option>
              <option value="true">Activos</option>
              <option value="false">Inactivos</option>
            </SelectInput>
          </label>
        </div>
        <div className={styles.filterActions}>
          <Button disabled={!hasFilters && !Object.values(filters).some(Boolean)} onClick={clearFilters} variant="secondary">Limpiar</Button>
          <Button type="submit">Aplicar filtros</Button>
        </div>
      </form>

      {isLoading ? <LoadingState label="Cargando proveedores" lines={6} /> : null}

      {!isLoading && !error && providers.length === 0 ? (
        <EmptyState
          action={hasFilters ? <Button onClick={clearFilters} variant="secondary">Limpiar filtros</Button> : <Link className={styles.primaryLink} to="/proveedores/nuevo"><Plus aria-hidden="true" />Registrar el primero</Link>}
          description={hasFilters ? 'No encontramos proveedores que cumplan todos los criterios.' : 'Registrá prestadores para poder asignarlos a los reclamos.'}
          icon={UsersRound}
          title={hasFilters ? 'Sin resultados' : 'Todavía no hay proveedores'}
        />
      ) : null}

      {!isLoading && providers.length ? (
        <section className={styles.listPanel} aria-labelledby="providers-list-title">
          <div className={styles.listSummary}>
            <div><h2 id="providers-list-title">Proveedores registrados</h2><p>{data.total} registros en total</p></div>
          </div>
          <div className={styles.tableRegion}>
            <table className={styles.table}>
              <thead><tr><th>Proveedor</th><th>Especialidades</th><th>Cobertura</th><th>Estado</th><th><span className="aari-sr-only">Acciones</span></th></tr></thead>
              <tbody>
                {providers.map((provider) => (
                  <tr key={provider.id}>
                    <td data-label="Proveedor"><Link className={styles.providerLink} to={`/proveedores/${provider.id}`}>{provider.nombre_razon_social}</Link><small className={styles.secondaryCopy}>{provider.telefono}{provider.matricula ? ` · Matrícula ${provider.matricula}` : ''}</small></td>
                    <td data-label="Especialidades"><div className={styles.badgeList}>{provider.especialidades.slice(0, 2).map((specialty) => <span key={specialty.id}>{specialty.nombre}</span>)}{provider.especialidades.length > 2 ? <span>+{provider.especialidades.length - 2}</span> : null}</div></td>
                    <td data-label="Cobertura">{coverageSummary(provider.coberturas)}</td>
                    <td data-label="Estado"><StatusBadge tone={provider.activo ? 'success' : 'neutral'}>{provider.activo ? 'Activo' : 'Inactivo'}</StatusBadge></td>
                    <td className={styles.actionsCell}><Link aria-label={`Ver ${provider.nombre_razon_social}`} className={styles.iconLink} to={`/proveedores/${provider.id}`}><Eye aria-hidden="true" /></Link><Link aria-label={`Editar ${provider.nombre_razon_social}`} className={styles.iconLink} to={`/proveedores/${provider.id}/editar`}><Pencil aria-hidden="true" /></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total_pages > 1 ? <nav className={styles.pagination} aria-label="Paginación de proveedores"><Button disabled={page === 1} onClick={() => goToPage(page - 1)} size="sm" variant="secondary">Anterior</Button><span>Página {page} de {data.total_pages}</span><Button disabled={page === data.total_pages} onClick={() => goToPage(page + 1)} size="sm" variant="secondary">Siguiente</Button></nav> : null}
        </section>
      ) : null}
    </PageContainer>
  )
}

export default ProveedoresListPage
