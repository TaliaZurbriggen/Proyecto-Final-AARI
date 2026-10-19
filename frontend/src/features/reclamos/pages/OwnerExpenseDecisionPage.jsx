import { useCallback, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, ConfirmDialog, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { decideOwnerExpense, getOwnerExpense } from '../api/expenseAuthorizationsApi.js'
import { claimStatusTone, formatClaimDate, formatClaimNumber } from '../presentation.js'
import { useHistoryResource } from '../useHistoryResource.js'
import styles from './OwnerExpenses.module.css'

export default function OwnerExpenseDecisionPage() {
  const { reclamoId } = useParams()
  return <DecisionContent key={reclamoId} reclamoId={reclamoId} />
}

function DecisionContent({ reclamoId }) {
  const navigate = useNavigate()
  const [revision, setRevision] = useState(0)
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [decisionError, setDecisionError] = useState('')
  const [result, setResult] = useState(null)
  const [lockedAction, setLockedAction] = useState('')
  const attempt = useRef(null)
  const load = useCallback((signal) => getOwnerExpense(reclamoId, { signal }), [reclamoId])
  const { data: claim, error, isLoading } = useHistoryResource(`${reclamoId}:${revision}`, load)
  const decide = async (action) => {
    if (!claim || busy) return
    // Mantener el UUID ante respuesta perdida: un reintento no crea otra decisión.
    if (!attempt.current) {
      attempt.current = { action, body: {
        request_id: crypto.randomUUID(), expected_updated_at: claim.updated_at,
      } }
      setLockedAction(action)
    }
    if (attempt.current.action !== action) return
    setBusy(true)
    setDecisionError('')
    try {
      const saved = await decideOwnerExpense(reclamoId, action, attempt.current.body)
      if (saved.decision === 'autorizar' && saved.siguiente_paso === 'eleccion_proveedor') {
        navigate(`/propietario/reclamos/${reclamoId}/tipo-proveedor`, { replace: true })
        return
      }
      setResult(saved)
      setConfirm('')
      setRevision((value) => value + 1)
    } catch (failure) {
      setDecisionError(failure.message)
      setConfirm('')
      if (failure.status) {
        attempt.current = null
        setLockedAction('')
        setRevision((value) => value + 1)
      }
    } finally { setBusy(false) }
  }
  const saved = result || claim?.decision
  return <PageContainer>
    <Link className={styles.link} to="/propietario/reclamos">Volver a autorizaciones</Link>
    <PageHeading title={claim ? `Reclamo ${formatClaimNumber(claim.numero)}` : 'Revisar gasto extraordinario'}
      eyebrow="Decisión del propietario" description="Sólo el titular de la propiedad puede autorizar o rechazar esta intervención." />
    {isLoading && <LoadingState label="Cargando detalle del gasto" />}
    {error && <AlertMessage>{error}</AlertMessage>}
    {decisionError && <AlertMessage>{decisionError}</AlertMessage>}
    {claim && <div className={styles.grid}>
      <section className={styles.card} aria-labelledby="expense-detail">
        <div className={styles.heading}><h2 id="expense-detail">Gasto extraordinario</h2>
          <StatusBadge tone={claimStatusTone(saved?.estado || claim.estado)}>{saved?.estado || claim.estado}</StatusBadge></div>
        <p>{claim.propiedad.direccion} · {claim.propiedad.localidad} · {claim.propiedad.provincia}</p>
        <p className={styles.description}>{claim.descripcion}</p>
        <h3>Clasificación informada</h3><p>{claim.fundamento || 'No se informó un fundamento.'}</p>
        <p>Plazo para decidir: {formatClaimDate(claim.respuesta_vence_en)}</p>
        {saved ? <AlertMessage tone={saved.decision === 'autorizar' ? 'success' : 'warning'}>
          {saved.decision === 'autorizar'
            ? 'Autorización registrada. Ya podés continuar con la elección de proveedor.'
            : 'Rechazo registrado. El ciclo de esta solicitud quedó cerrado.'}
          {' '}Se generaron los avisos correspondientes; su entrega se procesa por separado.
        </AlertMessage> : claim.puede_decidir ? <div className={styles.actions}>
          <Button disabled={busy || isLoading || Boolean(lockedAction && lockedAction !== 'autorizar')}
            onClick={() => decide('autorizar')}>{busy ? 'Guardando…' : 'Autorizar intervención'}</Button>
          <Button variant="danger" disabled={busy || isLoading || Boolean(lockedAction && lockedAction !== 'rechazar')}
            onClick={() => setConfirm('rechazar')}>Rechazar intervención</Button>
        </div> : <AlertMessage tone="warning">La solicitud ya no admite decisiones. Puede haber vencido o cambiado de estado. La inmobiliaria debe revisar cómo continuar.</AlertMessage>}
        {saved?.decision === 'autorizar' && <Link className={styles.link}
          to={`/propietario/reclamos/${reclamoId}/tipo-proveedor`}>Continuar con la elección de proveedor</Link>}
      </section>
      <section className={styles.card} aria-labelledby="expense-history">
        <h2 id="expense-history">Historial del reclamo</h2>
        {saved && <p>Decisión registrada por {saved.propietario_nombre} · {formatClaimDate(saved.decidido_en)}</p>}
        <ol className={styles.history}>{[...claim.historial].reverse().map((entry, index) =>
          <li key={`${entry.timestamp}:${index}`}><strong>{entry.estado_nuevo}</strong>
            <p>{formatClaimDate(entry.timestamp)} · {entry.origen}</p></li>)}</ol>
      </section>
    </div>}
    <ConfirmDialog open={Boolean(confirm)} title="¿Rechazar esta intervención?"
      description="El reclamo quedará rechazado y se notificará al inquilino y al operador. Esta decisión no se puede cambiar desde esta pantalla."
      confirmLabel="Confirmar rechazo" busyLabel="Guardando…" isBusy={busy}
      onCancel={() => setConfirm('')} onConfirm={() => decide('rechazar')} />
  </PageContainer>
}
