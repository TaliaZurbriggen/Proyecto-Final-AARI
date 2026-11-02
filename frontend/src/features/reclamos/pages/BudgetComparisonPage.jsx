import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { getQuoteSelection, selectQuote } from '../api/quoteSelectionsApi.js'
import { useHistoryResource } from '../useHistoryResource.js'
import { formatClaimDate, formatClaimNumber } from '../presentation.js'
import { quoteAmount } from '../../proveedores/quotePresentation.js'
import styles from './BudgetComparisonPage.module.css'

export default function BudgetComparisonPage({ ownerView = false }) {
  const { reclamoId } = useParams()
  return <Comparison key={reclamoId} claimId={reclamoId} ownerView={ownerView} />
}

function Comparison({ claimId, ownerView }) {
  const [revision, setRevision] = useState(0)
  const [confirming, setConfirming] = useState(null)
  const [result, setResult] = useState(null)
  const [failure, setFailure] = useState('')
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const attempt = useRef(null)
  const sending = useRef(false)
  const confirmHeading = useRef(null)
  const savedHeading = useRef(null)
  useEffect(() => { if (confirming) confirmHeading.current?.focus() }, [confirming])
  const load = useCallback((signal) => getQuoteSelection(claimId, { signal }), [claimId])
  const { data, error, isLoading } = useHistoryResource(`${claimId}:${revision}`, load)
  const back = `/${ownerView ? 'propietario' : 'inquilino'}/reclamos/${claimId}/tipo-proveedor`
  const decision = result || data?.decision
  useEffect(() => { if (decision) savedHeading.current?.focus() }, [decision])
  const canChoose = data?.puede_elegir && !decision && !isLoading && !error
  const confirm = async () => {
    if (!confirming || !canChoose || sending.current) return
    if (!attempt.current) attempt.current = {
      request_id: crypto.randomUUID(), ronda_id: data.ronda_id, expected_updated_at: data.updated_at,
      modalidad: 'fidelizado', presupuesto_id: confirming.id,
    }
    sending.current = true
    setBusy(true)
    setFailure('')
    try {
      setResult(await selectQuote(claimId, attempt.current))
      setUncertain(false)
      setConfirming(null)
      setRevision((n) => n + 1)
    } catch (e) {
      setFailure(e.message)
      if (e.status && e.status < 500) {
        setUncertain(false)
        attempt.current = null
        setConfirming(null)
        setRevision((n) => n + 1)
      } else setUncertain(true)
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  const choose = (item) => {
    if (attempt.current || !canChoose || sending.current) return
    setFailure('')
    setConfirming(item)
  }
  const cancel = () => {
    if (!sending.current && !attempt.current) setConfirming(null)
  }
  return <PageContainer className={styles.page}>
    <Link to={back} className={styles.back}>Volver a la elección de proveedor</Link>
    <PageHeading eyebrow="Revisá las propuestas" title="Elegí un presupuesto"
      description="Compará el alcance informado y confirmá cómo querés continuar. La visita se coordina después." />
    {isLoading && <LoadingState label={decision ? 'Actualizando estado del reclamo' : 'Cargando presupuestos'} />}
    {failure && <AlertMessage>{failure}</AlertMessage>}
    {error && <>
      <AlertMessage tone={decision ? 'warning' : 'error'}>{decision
        ? `La selección está guardada, pero no pudimos actualizar el estado del reclamo. ${error}`
        : error}</AlertMessage>
      <Button variant="secondary" onClick={() => setRevision((n) => n + 1)}>{decision ? 'Reintentar actualización' : 'Volver a intentar'}</Button>
    </>}
    {data && !error && !isLoading && <section className={styles.summary} aria-label="Reclamo">
      <h2>Reclamo {formatClaimNumber(data.numero)}</h2><p>{data.descripcion}</p>
      <StatusBadge>{data.estado}</StatusBadge>
    </section>}
    {decision ? <section className={styles.summary} aria-label="Selección registrada">
        <h2 ref={savedHeading} tabIndex={-1}>Presupuesto seleccionado</h2>
        <p>{decision.actor_nombre} · {formatClaimDate(decision.decidido_en)}</p>
        <p>Estado al confirmar la selección: {decision.estado_resultante}</p>
        <h3>{decision.proveedor_nombre}</h3><p>{quoteAmount(decision)}</p><AlertMessage tone="success">La elección quedó guardada. El aviso al proveedor se procesa por separado; esto no confirma su recepción ni programa una visita.</AlertMessage>
        {decision.tipo_importe === 'minimo' && <p>Elegiste un importe mínimo: es un piso, no un precio final ni un máximo autorizado.</p>}
        {!error && !isLoading && data?.decision?.id === decision.id
          && data.coordinacion_url === `/visitas/${claimId}`
          && ['Proveedor seleccionado', 'Visita programada'].includes(data.estado)
          ? <><p>{ownerView ? 'El inquilino acuerda el horario con el proveedor. Podés consultar cómo avanza.' : 'El agente solicitará tus horarios para recibir al proveedor. Podés consultar la coordinación desde acá.'}</p>
            <Link className={styles.ownLink} to={data.coordinacion_url}>Ver coordinación</Link></> : null}
      </section> : data && !error && !isLoading && <>
        <AlertMessage tone="info">Un importe “desde…” es un mínimo, no un precio final ni un máximo autorizado. Las monedas se muestran por separado, sin conversión ni selección automática.</AlertMessage>
        {data.recepcion_abierta && <p>Todavía pueden llegar otras propuestas. Si confirmás una elección, finalizará la recepción de este intento.</p>}
        {!canChoose && <AlertMessage tone="warning">Esta etapa no admite una nueva selección. El contexto o los permisos pudieron cambiar; consultá a la inmobiliaria.</AlertMessage>}
        {confirming ? <section className={styles.summary} aria-labelledby="confirm-budget">
          <h2 id="confirm-budget" tabIndex={-1} ref={confirmHeading}>Revisá tu elección antes de confirmar</h2>
          <h3>{confirming.proveedor}</h3><p className={styles.amount}>{quoteAmount(confirming)}</p><p>{confirming.descripcion}</p>
              {confirming.tipo_importe === 'minimo' && <p>Este importe es mínimo. No se está aceptando un precio final ni un máximo autorizado.</p>}
              <p>Confirmar no programa una fecha de visita ni realiza un pago.</p>
          {uncertain && <p>La respuesta del servidor no pudo confirmarse. Reintentá la misma elección; conservamos el identificador para no duplicarla.</p>}
          <div className={styles.actions}><Button disabled={busy || !canChoose} onClick={confirm}>{busy ? 'Guardando…' : 'Confirmar elección'}</Button>
            <Button variant="secondary" disabled={busy || uncertain} onClick={cancel}>Volver a comparar</Button></div>
        </section> : <>
          {data.items.length ? <div className={styles.quotes}>{data.items.map((item) => <article key={item.id} className={styles.quote}>
            <h2>{item.proveedor}</h2><StatusBadge>{item.tipo_importe === 'minimo' ? 'Importe mínimo' : 'Importe exacto'}</StatusBadge>
            <p className={styles.amount}>{quoteAmount(item)}</p><p className={styles.description}>{item.descripcion}</p>
            <dl><dt>Especialidades</dt><dd>{item.especialidades.join(', ') || 'Sin información'}</dd>
              <dt>Cobertura</dt><dd>{item.zonas.map((z) => `${z.localidad}, ${z.provincia}`).join(' · ') || 'Sin información'}</dd></dl>
            <Button className={styles.quoteAction} disabled={!canChoose || !item.puede_elegir} onClick={() => choose(item)}>Revisar propuesta de {item.proveedor}</Button>
            {!item.puede_elegir && <p>Esta propuesta ya no está habilitada para elegir.</p>}
          </article>)}</div> : <EmptyState title="Todavía no hay presupuestos disponibles" description="Las respuestas aparecerán acá cuando los proveedores las confirmen. No se elige un proveedor automáticamente." />}
          <section className={styles.summary} aria-label="Alternativa de proveedor propio"><h2>¿No te convence ninguna propuesta?</h2>
            <p id="own-provider-help">Podés registrar un contacto propio. Abrir el formulario no modifica el reclamo ni cierra la recepción; la derivación ocurre sólo al confirmar sus datos.</p>
            {data.puede_cargar_propio
              ? <Link className={styles.ownLink} to={`/${ownerView ? 'propietario' : 'inquilino'}/reclamos/${claimId}/proveedor-externo`}>Quiero cargar un proveedor propio</Link>
              : <><Button variant="secondary" disabled aria-describedby="own-provider-help">Quiero cargar un proveedor propio</Button><p>La etapa actual no permite registrar un contacto propio.</p></>}</section>
          <Button variant="secondary" onClick={() => setRevision((n) => n + 1)}>Actualizar presupuestos</Button>
        </>}
      </>}
  </PageContainer>
}
