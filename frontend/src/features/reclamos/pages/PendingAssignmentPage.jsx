import { useCallback } from 'react'
import { ClipboardList, RefreshCw } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, LoadingState, SearchInput } from '../../../components/ui/index.js'
import { listPendingAssignment } from '../api/providerCandidatesApi.js'
import { assignmentReturnQuery, candidateOutcome, positivePage } from '../providerCandidates.js'
import { formatClaimDate, formatClaimNumber } from '../presentation.js'
import { claimPropertyLabel } from '../validation.js'
import { useHistoryResource } from '../useHistoryResource.js'
import buttonStyles from '../../../components/ui/Button.module.css'
import styles from './Escalados.module.css'

function PendingAssignmentPage({ operatorView = false }) {
  const [params, setParams] = useSearchParams()
  const query = assignmentReturnQuery(params)
  const page = positivePage(params.get('page'))
  const search = params.get('search') || ''
  const refresh = params.get('refresh') || '0'
  const base = operatorView ? '/operador/pendientes-asignacion' : '/pendientes-asignacion'
  const load = useCallback((signal) => listPendingAssignment(query, { signal }), [query])
  const { data, error, isLoading } = useHistoryResource(`${query}:${refresh}`, load)
  const update = (name, value) => {
    const next = new URLSearchParams(params)
    next.set(name, String(value))
    if (name === 'search') next.delete('page')
    setParams(next, { replace: name !== 'page' })
  }
  return <PageContainer>
    <PageHeading eyebrow="Coordinación de proveedores" title="Proveedores por reclamo"
      description="Consultá los candidatos de los reclamos abiertos, sin esperar una autorización ni asignar un proveedor."
      action={<Button variant="secondary" leadingIcon={<RefreshCw />} disabled={isLoading}
        onClick={() => update('refresh', Number(refresh) + 1)}>Actualizar</Button>} />
    <div className={styles.toolbar}>
      <SearchInput label="Buscar pendientes de asignación" placeholder="Número, descripción o dirección"
        maxLength={200} value={search} onChange={(event) => update('search', event.target.value)}
        onClear={() => update('search', '')} />
      <p>Un candidato no tiene un turno reservado ni un presupuesto aprobado.</p>
    </div>
    {error ? <AlertMessage>{error}</AlertMessage> : null}
    {isLoading ? <LoadingState label="Cargando pendientes de asignación" lines={4} /> : null}
    {data && !error ? <section className={styles.panel} aria-label="Cola de asignación">
      <div className={styles.panelHeading}><h2>Reclamos para buscar proveedores</h2><span>{data.total} casos</span></div>
      {data.items.length ? <div className={styles.tableRegion}><table className={styles.table}>
        <caption className="aari-sr-only">Reclamos pendientes de proveedores, del más antiguo al más reciente</caption>
        <thead><tr><th>Número</th><th>Reclamo y propiedad</th><th>Especialidad</th><th>Ingresado</th><th>Última búsqueda</th><th>Acciones</th></tr></thead>
        <tbody>{data.items.map((claim) => <tr key={claim.id}>
          <td data-label="Número">{formatClaimNumber(claim.numero)}</td>
          <td data-label="Reclamo y propiedad"><p className={styles.description}>{claim.descripcion}</p><small>{claimPropertyLabel(claim.propiedad)}</small></td>
          <td data-label="Especialidad">{claim.especialidad?.nombre || 'Pendiente de indicar'}</td>
          <td data-label="Ingresado">{formatClaimDate(claim.creado_en, { short: true })}</td>
          <td data-label="Última búsqueda">{candidateOutcome[claim.ultimo_resultado] || 'Sin búsqueda registrada'}
            {claim.aviso_operador === 'sin_destinatario' ? <small>Sin destinatario para el aviso</small> : null}</td>
          <td data-label="Acciones" className={styles.actionsCell}><Link
            to={`${base}/${claim.id}?${query}`}
            aria-label={`Revisar proveedores del reclamo ${formatClaimNumber(claim.numero)}`}
            className={`${buttonStyles.button} ${buttonStyles.primary} ${buttonStyles.md} ${styles.resolveLink}`}>
            Revisar proveedores
          </Link></td>
        </tr>)}</tbody>
      </table></div> : <EmptyState icon={ClipboardList} title={search ? 'Sin coincidencias' : 'No hay pendientes en esta página'}
        description={search ? 'Probá otra búsqueda.' : 'Aquí aparecen los reclamos abiertos desde su recepción; no necesitan una autorización previa.'}
        action={page > 1 ? <Button variant="secondary" onClick={() => update('page', 1)}>Volver a la primera página</Button> : undefined} />}
      {data.total_pages > 1 || page > 1 ? <nav className={styles.pagination} aria-label="Paginación de pendientes">
        <Button variant="secondary" disabled={page <= 1} onClick={() => update('page', Math.max(1, Math.min(page - 1, data.total_pages)))}>Anterior</Button>
        <span>Página {page} de {data.total_pages}</span>
        <Button variant="secondary" disabled={page >= data.total_pages} onClick={() => update('page', page + 1)}>Siguiente</Button>
      </nav> : null}
    </section> : null}
  </PageContainer>
}

export default PendingAssignmentPage
