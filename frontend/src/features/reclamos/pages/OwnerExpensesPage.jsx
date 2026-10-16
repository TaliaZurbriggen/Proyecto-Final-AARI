import { useCallback } from 'react'
import { Link, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { listOwnerExpenses } from '../api/expenseAuthorizationsApi.js'
import { claimStatusTone, formatClaimNumber } from '../presentation.js'
import { useHistoryResource } from '../useHistoryResource.js'
import styles from './OwnerExpenses.module.css'

export default function OwnerExpensesPage() {
  const [params, setParams] = useSearchParams()
  const raw = Number(params.get('page') || 1)
  const page = Number.isInteger(raw) && raw > 0 && raw <= 1000000 ? raw : 1
  const load = useCallback((signal) => listOwnerExpenses(page, { signal }), [page])
  const { data, error, isLoading } = useHistoryResource(`owner:${page}`, load)
  return <PageContainer>
    <PageHeading title="Autorizaciones de gastos" eyebrow="Portal del propietario"
      description="Revisá los gastos extraordinarios de tus propiedades y decidí cómo continuar." />
    {isLoading && <LoadingState label="Cargando autorizaciones" />}
    {error && <AlertMessage>{error}</AlertMessage>}
    {data?.items.length === 0 && <EmptyState title="No hay gastos extraordinarios para mostrar"
      description="Cuando un reclamo requiera tu autorización aparecerá acá." />}
    <div className={styles.list}>
      {data?.items.map((claim) => <article className={styles.card} key={claim.id}>
        <div className={styles.heading}><h2>Reclamo {formatClaimNumber(claim.numero)}</h2>
          <StatusBadge tone={claimStatusTone(claim.estado)}>{claim.estado}</StatusBadge></div>
        <p>{claim.propiedad.direccion} · {claim.propiedad.localidad}</p>
        <p className={styles.description}>{claim.descripcion}</p>
        <Link className={styles.link} to={`/propietario/reclamos/${claim.id}/autorizar`}>
          {claim.puede_decidir ? 'Revisar y decidir' : 'Ver decisión y seguimiento'}
        </Link>
      </article>)}
    </div>
    {data && data.total_pages > 1 && <nav aria-label="Páginas de autorizaciones" className={styles.actions}>
      <Button variant="secondary" disabled={page <= 1 || isLoading} onClick={() => setParams({ page: String(page - 1) })}>Anterior</Button>
      <span>Página {page} de {data.total_pages}</span>
      <Button variant="secondary" disabled={page >= data.total_pages || isLoading} onClick={() => setParams({ page: String(page + 1) })}>Siguiente</Button>
    </nav>}
  </PageContainer>
}
