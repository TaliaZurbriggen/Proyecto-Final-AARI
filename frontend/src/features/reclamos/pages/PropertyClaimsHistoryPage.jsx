import { useCallback } from 'react'
import { ArrowLeft, ClipboardList, FilterX } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage, Button, EmptyState, FormField, LoadingState,
  SelectInput, StatusBadge, TextInput,
} from '../../../components/ui/index.js'
import { listPropertyClaims } from '../api/propertyClaimsApi.js'
import { claimPropertyLabel } from '../validation.js'
import { claimStatusTone, formatClaimDate, formatClaimNumber } from '../presentation.js'
import { CLAIM_STATES, EXPENSE_LABELS, expenseLabel, propertyHistoryPath } from '../propertyHistory.js'
import { useHistoryResource } from '../useHistoryResource.js'
import styles from './PropertyHistory.module.css'

function PropertyClaimsHistoryPage({ tenantView = false }) {
  const { propiedadId } = useParams()
  const [params, setParams] = useSearchParams()
  const rawPage = Number(params.get('page') || 1)
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1
  const state = params.get('estado') || ''
  const expense = params.get('tipo_gasto') || ''
  const from = params.get('fecha_desde') || ''
  const until = params.get('fecha_hasta') || ''
  const query = new URLSearchParams({ page: String(page) })
  if (state) query.set('estado', state)
  if (expense) query.set('tipo_gasto', expense)
  if (from) query.set('fecha_desde', from)
  if (until) query.set('fecha_hasta', until)
  const queryString = query.toString()
  const dateError = from && until && from > until
    ? 'La fecha desde no puede ser posterior a la fecha hasta.' : ''
  const load = useCallback(
    (signal) => listPropertyClaims(propiedadId, queryString, { signal }),
    [propiedadId, queryString],
  )
  const { data, error, isLoading } = useHistoryResource(
    `${propiedadId}:${queryString}`, load, !dateError,
  )
  const base = propertyHistoryPath(propiedadId, tenantView)
  const hasFilters = Boolean(state || expense || from || until)
  const updateFilter = (name, value) => {
    const next = new URLSearchParams(params)
    if (value) next.set(name, value)
    else next.delete(name)
    next.delete('page')
    setParams(next, { replace: true })
  }
  const changePage = (nextPage) => {
    const next = new URLSearchParams(params)
    next.set('page', String(nextPage))
    setParams(next)
  }

  return (
    <PageContainer>
      <Link className={styles.backLink} to={tenantView ? '/inquilino/reclamos' : `/propiedades/${propiedadId}`}>
        <ArrowLeft aria-hidden="true" />
        {tenantView ? 'Volver a mis reclamos' : 'Volver a la propiedad'}
      </Link>
      <PageHeading
        eyebrow={tenantView ? 'Mis reclamos por propiedad' : 'Trazabilidad de la propiedad'}
        title="Historial de reclamos"
        description={data
          ? claimPropertyLabel(data.propiedad)
          : 'Consultá los reclamos y su evolución, con filtros por fecha, estado y tipo de gasto.'}
      />
      {tenantView ? <p className={styles.scopeNotice}>Este historial incluye únicamente los reclamos que vos presentaste.</p> : null}

      <section className={styles.filterPanel} aria-label="Filtros del historial">
        <FormField id="history-state" label="Estado">
          <SelectInput value={state} onChange={(event) => updateFilter('estado', event.target.value)}>
            <option value="">Todos los estados</option>
            {CLAIM_STATES.map((value) => <option key={value}>{value}</option>)}
          </SelectInput>
        </FormField>
        <FormField id="history-expense" label="Tipo de gasto">
          <SelectInput value={expense} onChange={(event) => updateFilter('tipo_gasto', event.target.value)}>
            <option value="">Todos los tipos</option>
            {Object.entries(EXPENSE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </SelectInput>
        </FormField>
        <FormField id="history-from" label="Fecha de ingreso desde">
          <TextInput type="date" value={from} onChange={(event) => updateFilter('fecha_desde', event.target.value)} />
        </FormField>
        <FormField id="history-until" label="Fecha de ingreso hasta" error={dateError}>
          <TextInput type="date" value={until} onChange={(event) => updateFilter('fecha_hasta', event.target.value)} />
        </FormField>
        <Button disabled={!hasFilters} leadingIcon={<FilterX />} onClick={() => setParams({})} variant="secondary">
          Limpiar filtros
        </Button>
      </section>
      {error ? <AlertMessage>{error}</AlertMessage> : null}
      {isLoading ? <LoadingState label="Cargando el historial de reclamos" lines={6} /> : null}

      {data ? (
        <section className={styles.listPanel} aria-label="Resultados del historial">
          <div className={styles.summary} role="status">
            <h2>{hasFilters ? 'Resultados filtrados' : 'Reclamos de la propiedad'}</h2>
            <p>{data.total} {data.total === 1 ? 'reclamo' : 'reclamos'} · 20 por página</p>
          </div>
          {data.items.length ? (
            <div className={styles.tableRegion}>
              <table className={styles.table}>
                <caption className="aari-sr-only">Reclamos ordenados del más reciente al más antiguo</caption>
                <thead><tr><th scope="col">Número</th><th scope="col">Descripción</th><th scope="col">Estado</th><th scope="col">Tipo de gasto</th><th scope="col">Fecha de ingreso</th></tr></thead>
                <tbody>
                  {data.items.map((claim) => (
                    <tr key={claim.id}>
                      <td data-label="Número"><Link className={styles.claimLink} to={`${base}/${claim.id}?${queryString}`} aria-label={`Ver reclamo ${formatClaimNumber(claim.numero)}`}>{formatClaimNumber(claim.numero)}</Link></td>
                      <td data-label="Descripción"><p className={styles.description}>{claim.descripcion}</p></td>
                      <td data-label="Estado"><StatusBadge tone={claimStatusTone(claim.estado)}>{claim.estado}</StatusBadge></td>
                      <td data-label="Tipo de gasto">{expenseLabel(claim.tipo_gasto)}</td>
                      <td data-label="Fecha de ingreso"><time dateTime={claim.creado_en}>{formatClaimDate(claim.creado_en, { short: true })}</time></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={ClipboardList}
              title={data.total && page > 1 ? 'Esta página no tiene resultados' : hasFilters ? 'Sin coincidencias' : 'Todavía no hay reclamos'}
              description={hasFilters ? 'Probá con otros filtros o limpiá la selección para ver el historial.' : 'Los reclamos disponibles aparecerán acá con su estado y fecha de ingreso.'}
              action={page > 1 ? <Button variant="secondary" onClick={() => changePage(1)}>Volver a la primera página</Button> : hasFilters ? <Button variant="secondary" onClick={() => setParams({})}>Limpiar selección</Button> : undefined}
            />
          )}
          {data.total_pages > 1 || page > 1 ? (
            <nav className={styles.pagination} aria-label="Paginación del historial">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => changePage(Math.min(page - 1, data.total_pages))}>Anterior</Button>
              <span>Página {page} de {data.total_pages}</span>
              <Button size="sm" variant="secondary" disabled={page >= data.total_pages} onClick={() => changePage(page + 1)}>Siguiente</Button>
            </nav>
          ) : null}
        </section>
      ) : null}
    </PageContainer>
  )
}

export default PropertyClaimsHistoryPage
