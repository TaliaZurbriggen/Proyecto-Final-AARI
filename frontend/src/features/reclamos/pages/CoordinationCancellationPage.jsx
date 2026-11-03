import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { cancelCoordination, getCoordinationCancellation } from '../api/coordinationCancellationsApi.js'
import { useHistoryResource } from '../useHistoryResource.js'
import { formatClaimDate, formatClaimNumber } from '../presentation.js'
import styles from './CoordinationCancellationPage.module.css'

export default function CoordinationCancellationPage({ ownerView = false }) {
  const { reclamoId } = useParams()
  return <Cancellation key={reclamoId} claimId={reclamoId} ownerView={ownerView} />
}

function Cancellation({ claimId, ownerView }) {
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [result, setResult] = useState(null)
  const sending = useRef(false)
  const attempt = useRef(null)
  const savedHeading = useRef(null)
  const retryButton = useRef(null)
  const refreshing = useRef(false)
  const load = useCallback((signal) => getCoordinationCancellation(claimId, { signal }), [claimId])
  const { data, error, isLoading } = useHistoryResource(`${claimId}:${revision}`, load)
  const choice = `/${ownerView ? 'propietario' : 'inquilino'}/reclamos/${claimId}/tipo-proveedor`
  useEffect(() => { if (result) savedHeading.current?.focus() }, [result])
  useEffect(() => {
    if (!isLoading && refreshing.current) {
      if (error) retryButton.current?.focus()
      else if (result) savedHeading.current?.focus()
      refreshing.current = false
    }
  }, [isLoading, error, result])
  const confirm = async () => {
    if (!data?.puede_cancelar || result || sending.current || error || isLoading) return
    if (!attempt.current) attempt.current = {
      request_id: crypto.randomUUID(), eleccion_id: data.eleccion_id,
      expected_updated_at: data.updated_at, confirmar: true,
    }
    sending.current = true
    setBusy(true)
    setFailure('')
    try {
      setResult(await cancelCoordination(claimId, attempt.current))
      setUncertain(false)
      setRevision((n) => n + 1)
    } catch (e) {
      setFailure(e.message)
      if (e.status && e.status < 500) {
        attempt.current = null
        setUncertain(false)
        setRevision((n) => n + 1)
      } else setUncertain(true)
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  return <PageContainer className={styles.page}>
    <PageHeading eyebrow="Coordinación del reclamo" title="Cancelar y elegir otro proveedor"
      description="El reclamo y su historial se conservan. Podrás comenzar una nueva elección de proveedor." />
    {isLoading && <LoadingState label={result ? 'Actualizando el reclamo' : 'Cargando coordinación'} />}
    {error && <>
      <AlertMessage tone={result ? 'warning' : 'error'}>{result
        ? `La cancelación está guardada, pero no pudimos actualizar el reclamo. ${error}` : error}</AlertMessage>
      <Button ref={retryButton} variant="secondary" onClick={() => { refreshing.current = true; setRevision((n) => n + 1) }}>Reintentar consulta</Button>
    </>}
    {failure && <AlertMessage>{failure}</AlertMessage>}
    {data && !error && !isLoading && <section className={styles.summary} aria-label="Reclamo actual">
      <h2>Reclamo {formatClaimNumber(data.numero)}</h2>
      <p>{data.descripcion}</p><StatusBadge>{data.estado}</StatusBadge>
    </section>}
    {result ? <section className={styles.summary} aria-label="Cancelación registrada">
      <h2 ref={savedHeading} tabIndex={-1}>Coordinación cancelada</h2>
      <p>{result.actor_nombre} · {formatClaimDate(result.creada_en)}</p>
      <AlertMessage tone="success">La cancelación quedó registrada. Los avisos se procesan por separado; esto no confirma su recepción.</AlertMessage>
      <p>Estado al cancelar: {result.estado_resultante}.</p>
      <Link className={styles.link} to={choice}>Volver a elegir proveedor</Link>
    </section> : data && !error && !isLoading && <section className={styles.summary} aria-labelledby="cancel-confirmation">
      {data.puede_cancelar ? <>
        <h2 id="cancel-confirmation">¿Confirmás que querés cancelar y elegir otro proveedor?</h2>
        <p>El intento actual dejará de aceptar respuestas y confirmaciones. Conservaremos los presupuestos, las conversaciones y las decisiones anteriores como historial.</p>
        <p>Una nueva elección no contrata un proveedor ni programa una visita automáticamente.</p>
        {uncertain && <AlertMessage tone="warning">Todavía no pudimos confirmar la respuesta. Reintentá la misma cancelación para comprobarla sin duplicarla.</AlertMessage>}
        <div className={styles.actions}>
          <Button variant="danger" disabled={busy} onClick={confirm}>{busy ? 'Cancelando…' : uncertain ? 'Reintentar cancelación' : 'Sí, cancelar y volver a elegir'}</Button>
          {!busy && !uncertain && <Link className={styles.link} to={choice}>No, continuar con este intento</Link>}
        </div>
      </> : <><h2 id="cancel-confirmation">Cancelación no disponible</h2>
        <AlertMessage tone="warning">{data.motivo_bloqueo}</AlertMessage>
        <Link className={styles.link} to={choice}>Volver al reclamo</Link></>}
    </section>}
    {data?.historial?.length > 0 && !error && !isLoading && <section className={styles.summary} aria-label="Historial de cancelaciones">
      <h2>Cancelaciones anteriores</h2>
      <ol className={styles.history}>{data.historial.map((item) => <li key={item.id}>
        <p>{formatClaimDate(item.timestamp)}{item.actor_nombre ? ` · ${item.actor_nombre}` : ''}</p>
        {item.proveedor && <p>Proveedor: {item.proveedor}</p>}
      </li>)}</ol>
    </section>}
  </PageContainer>
}
