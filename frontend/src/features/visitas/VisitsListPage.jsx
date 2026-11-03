import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, LoadingState, StatusBadge } from '../../components/ui/index.js'
import { useAuth } from '../auth/authContext.js'
import { homePathForRole } from '../auth/routing.js'
import { listVisits, visitDate, visitLabels } from './visitsApi.js'
import styles from './Visits.module.css'

export default function VisitsListPage() {
  const { user } = useAuth()
  const [query, setQuery] = useSearchParams()
  const raw = Number(query.get('page') || 1)
  const page = Number.isInteger(raw) && raw >= 1 && raw <= 2147483647 ? raw : 1
  const [data, setData] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    listVisits(page, { signal: controller.signal }).then((result) => {
      if (!controller.signal.aborted) { setData(result); setError(''); if (result.page !== page) setQuery({ page: String(result.page) }, { replace: true }) }
    }).catch((failure) => { if (!controller.signal.aborted) { setData(null); setError(failure.message) } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [page, setQuery])
  const go = (next) => { setLoading(true); setData(null); setQuery({ page: String(next) }) }
  return <PageContainer className={styles.page}><Link className={styles.back} to={homePathForRole(user?.rol)}>Volver a mi inicio</Link>
    <PageHeading title="Mis visitas" eyebrow="Coordinación" description="Consultá los horarios pendientes de acuerdo y las visitas confirmadas." />
    {error ? <AlertMessage>{error}</AlertMessage> : null}
    {loading ? <LoadingState label="Consultando visitas" /> : data?.items.length ? <>
      {data.items.map((item) => <section className={styles.card} key={item.id}><div className={styles.heading}><h2>Reclamo #{String(item.numero).padStart(6, '0')}</h2><StatusBadge tone={item.etapa === 'confirmada' ? 'success' : 'neutral'}>{visitLabels[item.etapa]}</StatusBadge></div><p>{item.proveedor}</p>{item.etapa === 'confirmada' ? <p>{visitDate(item.fecha_confirmada)} (Argentina)</p> : null}<Link className={styles.back} to={`/visitas/${item.reclamo_id}`}>Ver coordinación</Link></section>)}
      {data.total > data.page_size ? <nav className={styles.actions} aria-label="Páginas de visitas"><Button variant="secondary" disabled={data.page <= 1} onClick={() => go(data.page - 1)}>Anterior</Button><span>Página {data.page} de {Math.ceil(data.total / data.page_size)}</span><Button variant="secondary" disabled={data.page * data.page_size >= data.total} onClick={() => go(data.page + 1)}>Siguiente</Button></nav> : null}
    </> : !error ? <EmptyState title="Todavía no tenés visitas para coordinar" description="Aparecerán cuando se confirme la selección de un presupuesto y el agente prepare la coordinación." /> : null}
  </PageContainer>
}
