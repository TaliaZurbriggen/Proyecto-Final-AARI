import { useCallback, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { AlertMessage, Button, EmptyState, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { listQuoteRequests } from '../api/quotePortalApi.js'
import { quoteDate, quoteLabels, quoteListFilter, quoteListFilters } from '../quotePresentation.js'
import styles from '../pages/ProviderPortal.module.css'
import { useHistoryResource } from '../../reclamos/useHistoryResource.js'

function ProviderQuoteRequests() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('page') ?? '1'
  const page = /^\d+$/.test(raw) && Number(raw) >= 1 && Number(raw) <= 2147483647 ? Number(raw) : 1
  const estado = quoteListFilter(params.get('estado'))
  const [refresh, setRefresh] = useState(0)
  const load = useCallback((signal) => listQuoteRequests(page, estado, { signal }), [page, estado])
  const { data, error, isLoading: loading } = useHistoryResource(`${estado}:${page}:${refresh}`, load)
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / 10))
  const movePage = (next) => setParams({ page: String(Math.max(1, Math.min(next, pages))), estado })
  const empty = {
    pendientes: ['No tenés solicitudes pendientes', 'Las solicitudes que puedas responder aparecerán acá. Podés consultar tus presupuestos confirmados en Enviadas.'],
    enviadas: ['Todavía no enviaste presupuestos', 'Cuando confirmes un presupuesto, la solicitud aparecerá en esta vista.'],
    todas: ['Todavía no tenés solicitudes', 'Acá podrás consultar también las solicitudes vencidas y canceladas.'],
  }[estado]
  return <section className={styles.panel} aria-labelledby="requests-title">
    <div className={styles.requestToolbar}>
      <h2 id="requests-title">Solicitudes de presupuesto</h2>
      <div className={styles.filters} role="group" aria-label="Filtrar solicitudes">
        {Object.entries(quoteListFilters).map(([value, label]) => <Button key={value} aria-pressed={estado === value}
          variant={estado === value ? 'primary' : 'secondary'} onClick={() => setParams({ page: '1', estado: value })}>{label}</Button>)}
      </div>
      <Button className={styles.refreshAction} leadingIcon={<RefreshCw />} onClick={() => setRefresh((x) => x + 1)} variant="secondary">Actualizar</Button>
    </div>
    <div className={styles.panelBody}>
      {loading ? <LoadingState label="Cargando solicitudes" /> : error ? <AlertMessage>{error}</AlertMessage> : data?.items.length ? <>
        <ul className={styles.requestList}>{data.items.map((item) => <li key={item.id}>
          <div className={styles.requestInfo}>
            <div className={styles.requestHeader}>
              <h3 id={`quote-request-${item.id}`}>Reclamo #{String(item.numero).padStart(6, '0')}</h3>
              <StatusBadge tone={item.estado === 'respondida' ? 'success' : 'neutral'}>{quoteLabels[item.estado]}</StatusBadge>
            </div>
            <p>{item.descripcion}</p>
            <p className={styles.muted}>{item.ubicacion}</p>
            <p className={styles.muted}>Vence: {quoteDate(item.vence_en)} (Argentina)</p>
          </div>
          <Link className={styles.viewRequest} aria-describedby={`quote-request-${item.id}`}
            to={`/proveedor/solicitudes/${item.id}?${new URLSearchParams({ page: String(page), estado })}`}>
            Ver solicitud
          </Link>
        </li>)}</ul>
      </> : <EmptyState title={page > 1 ? 'No hay solicitudes en esta página' : empty[0]} description={empty[1]} />}
      {!loading && !error && data && (pages > 1 || page > 1) ? (
        <nav className={styles.pagination} aria-label="Paginación de solicitudes">
          <Button disabled={page === 1} onClick={() => movePage(page - 1)} variant="secondary">Ver anteriores</Button>
          <Button disabled={page >= pages} onClick={() => movePage(page + 1)} variant="secondary">Ver siguientes</Button>
          {page > pages ? <Button onClick={() => movePage(1)} variant="secondary">Volver a la primera página</Button> : null}
        </nav>
      ) : null}
    </div>
  </section>
}
export default ProviderQuoteRequests
