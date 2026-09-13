import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { AlertMessage, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { listContracts } from '../api/contratosApi.js'
import { contractTone, dateLabel } from '../validation.js'
import styles from '../pages/Contratos.module.css'

export default function ContractPanel({ inquilinoId = '', propiedadId = '', canCreate = false, onCount }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const query = new URLSearchParams()
  if (inquilinoId) query.set('inquilino_id', inquilinoId)
  if (propiedadId) query.set('propiedad_id', propiedadId)
  useEffect(() => {
    const controller = new AbortController()
    listContracts({ inquilinoId, propiedadId, pageSize: 3, signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) { setResult(data); onCount?.(data.total) } })
      .catch(err => { if (!controller.signal.aborted) setError(err.message) })
    return () => controller.abort()
  }, [inquilinoId, propiedadId, onCount])
  return <section className={`${styles.panel} ${styles.contextPanel}`} aria-label="Contratos de alquiler">
    <div className={styles.panelHeading}><h2>Contratos de alquiler</h2>{canCreate && <Link to={`/contratos/nuevo?${query}`}>Cargar contrato</Link>}</div>
    {error ? <div className={styles.content}><AlertMessage>{error}</AlertMessage></div> : !result ? <div className={styles.content}><LoadingState label="Cargando contratos asociados" /></div> : <>
      {result.items.length ? result.items.map(item => <div key={item.id} className={styles.card}>
        <div className={styles.cardMain}><Link to={`/contratos/${item.id}`}>{item.direccion}</Link><p>{dateLabel(item.fecha_inicio)} — {dateLabel(item.fecha_finalizacion ?? item.fecha_fin)}</p></div>
        <StatusBadge tone={contractTone(item.vigencia)}>{item.vigencia}</StatusBadge>
      </div>) : <div className={styles.content}><p className={styles.muted}>Todavía no hay contratos asociados. El historial se conservará aunque cambie la ocupación.</p></div>}
      {result.total > 3 && <div className={styles.footer}><Link to={`/contratos?${query}`}>Ver historial completo ({result.total})</Link></div>}
    </>}
  </section>
}
