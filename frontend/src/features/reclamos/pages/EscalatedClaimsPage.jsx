import { useCallback } from 'react'
import { ClipboardList, RefreshCw } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, LoadingState, SearchInput, StatusBadge } from '../../../components/ui/index.js'
import { listEscalatedClaims } from '../api/escaladosApi.js'
import { escalationReason } from '../escalados.js'
import { formatClaimDate, formatClaimNumber, claimStatusTone } from '../presentation.js'
import { claimPropertyLabel } from '../validation.js'
import { useHistoryResource } from '../useHistoryResource.js'
import styles from './Escalados.module.css'

function EscalatedClaimsPage({ operatorView = false }) {
  const [params, setParams] = useSearchParams()
  const rawPage = Number(params.get('page') || 1)
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 && rawPage <= 1000000 ? rawPage : 1
  const search = params.get('search') || ''
  const query = new URLSearchParams({ page: String(page), search }).toString()
  const refresh = params.get('refresh') || '0'
  const load = useCallback((signal) => listEscalatedClaims(query, { signal }), [query])
  const { data, error, isLoading } = useHistoryResource(`${query}:${refresh}`, load)
  const base = operatorView ? '/operador/escalados' : '/escalados'
  const update = (name, value) => {
    const next = new URLSearchParams(params)
    next.set(name, String(value))
    if (name === 'search') next.delete('page')
    setParams(next, { replace: name !== 'page' })
  }

  return (
    <PageContainer>
      <PageHeading eyebrow="Intervención de la inmobiliaria" title="Casos escalados"
        description="Revisá los casos pendientes de clasificación. Los más antiguos aparecen primero."
        action={<Button variant="secondary" leadingIcon={<RefreshCw />} disabled={isLoading}
          onClick={() => update('refresh', Number(refresh) + 1)}>Actualizar</Button>} />
      <div className={styles.toolbar}>
        <SearchInput label="Buscar casos escalados" placeholder="Número, descripción o dirección"
          maxLength={200} value={search} onChange={(event) => update('search', event.target.value)}
          onClear={() => update('search', '')} />
        <p>Clasificar un caso no significa cerrar la reparación.</p>
      </div>
      {error ? <AlertMessage>{error}</AlertMessage> : null}
      {isLoading ? <LoadingState label="Cargando casos escalados" lines={5} /> : null}
      {data && !error ? (
        <section className={styles.panel} aria-label="Cola de revisión">
          <div className={styles.panelHeading}><h2>Pendientes de revisión</h2><span>{data.total} {data.total === 1 ? 'caso' : 'casos'}</span></div>
          {data.items.length ? <div className={styles.tableRegion}><table className={styles.table}>
            <caption className="aari-sr-only">Casos pendientes, del más antiguo al más reciente</caption>
            <thead><tr><th>Número y estado</th><th>Reclamo y propiedad</th><th>Ingresado</th><th>Escalado</th><th>Motivo de revisión</th></tr></thead>
            <tbody>{data.items.map((claim) => <tr key={claim.id}>
              <td data-label="Número y estado"><Link aria-label={`Revisar reclamo ${formatClaimNumber(claim.numero)}`}
                to={`${base}/${claim.id}?${query}`} className={styles.claimLink}>{formatClaimNumber(claim.numero)}</Link>
                <StatusBadge tone={claimStatusTone(claim.estado)}>{claim.estado}</StatusBadge></td>
              <td data-label="Reclamo y propiedad"><p className={styles.description}>{claim.descripcion}</p><small>{claimPropertyLabel(claim.propiedad)}</small></td>
              <td data-label="Ingresado">{formatClaimDate(claim.creado_en, { short: true })}</td>
              <td data-label="Escalado">{claim.escalado_en ? formatClaimDate(claim.escalado_en, { short: true }) : 'Sin escalado previo'}</td>
              <td data-label="Motivo de revisión">{escalationReason(claim.motivo_escalado)}</td>
            </tr>)}</tbody>
          </table></div> : <EmptyState icon={ClipboardList} title={search ? 'Sin coincidencias' : 'No hay casos en esta página'}
            description={search ? 'Probá con otra búsqueda.' : 'Los reclamos que necesiten clasificación manual aparecerán acá.'}
            action={page > 1 ? <Button variant="secondary" onClick={() => update('page', 1)}>Volver a la primera página</Button> : undefined} />}
          {data.total_pages > 1 || page > 1 ? <nav className={styles.pagination} aria-label="Paginación de casos escalados">
            <Button variant="secondary" disabled={page <= 1} onClick={() => update('page', Math.min(page - 1, data.total_pages))}>Anterior</Button>
            <span>Página {page} de {data.total_pages}</span>
            <Button variant="secondary" disabled={page >= data.total_pages} onClick={() => update('page', page + 1)}>Siguiente</Button>
          </nav> : null}
        </section>
      ) : null}
    </PageContainer>
  )
}

export default EscalatedClaimsPage
