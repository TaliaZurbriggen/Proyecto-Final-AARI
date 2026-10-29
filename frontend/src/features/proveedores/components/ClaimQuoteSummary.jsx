import { useCallback, useState } from 'react'
import { AlertMessage, Button, LoadingState } from '../../../components/ui/index.js'
import { useHistoryResource } from '../../reclamos/useHistoryResource.js'
import { getClaimQuotes } from '../api/quotePortalApi.js'
import { quoteAmount, quoteDate, quoteLabels } from '../quotePresentation.js'
import styles from '../pages/ProviderPortal.module.css'
import { ConversationLauncher } from '../../conversaciones/ConversationDock.jsx'

// Sólo lectura: comparar/seleccionar corresponde a HU20, no a HU19.
export default function ClaimQuoteSummary({ claimId }) {
  const [revision, setRevision] = useState(0)
  const load = useCallback((signal) => getClaimQuotes(claimId, { signal }), [claimId])
  const { data, error, isLoading } = useHistoryResource(`${claimId}:${revision}`, load)
  return <section className={styles.panel} aria-label="Presupuestos del reclamo">
    <div className={styles.panelHeading}><h2>Presupuestos solicitados</h2><Button variant="secondary" onClick={() => setRevision((n) => n + 1)}>Actualizar presupuestos</Button></div>
    <div className={styles.panelBody}>
      {isLoading ? <LoadingState label="Consultando presupuestos" /> : error ? <AlertMessage>{error}</AlertMessage> : data?.items?.length ? <>
        <p className={styles.muted}>Recibir un presupuesto no confirma una contratación. Un importe mínimo es un piso del costo, no un precio final ni un máximo autorizado.</p>
        <ul className={styles.requestList}>{data.items.map((item) => <li key={item.id}><div><strong>{item.proveedor}</strong>{item.presupuesto ? <><p>{quoteAmount(item.presupuesto)} · {item.presupuesto.tipo_importe === 'minimo' ? 'Importe mínimo' : 'Importe exacto'}</p><p>{item.presupuesto.descripcion}</p></> : <p>{quoteLabels[item.estado]}</p>}<p className={styles.muted}>Plazo: {quoteDate(item.vence_en)} (Argentina)</p></div>
          {item.conversacion_habilitada ? <ConversationLauncher requestId={item.id} label={`Ver avisos de ${item.proveedor}`} /> : null}
        </li>)}</ul>
      </> : <p className={styles.muted}>Aún no hay solicitudes publicadas para esta elección. La inmobiliaria revisará los proveedores sin acceso activado.</p>}
    </div>
  </section>
}
