import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, Send } from 'lucide-react'
import { Link, useLocation, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, FormField, LoadingState, SelectInput, StatusBadge, TextInput } from '../../../components/ui/index.js'
import { getQuoteRequest, submitQuote } from '../api/quotePortalApi.js'
import { positiveAmount, quoteAmount, quoteDate, quoteLabels, quoteListFilter } from '../quotePresentation.js'
import styles from './ProviderPortal.module.css'
import { useHistoryResource } from '../../reclamos/useHistoryResource.js'
import { ConversationLauncher, QuestionsButton } from '../../conversaciones/ConversationDock.jsx'

function ProviderQuoteDetailPage() {
  const { requestId } = useParams()
  return <QuoteDetail key={requestId} requestId={requestId} />
}

function QuoteDetail({ requestId }) {
  const location = useLocation()
  const [request, setRequest] = useState(null)
  const [error, setError] = useState('')
  const [fields, setFields] = useState({ monto: '', moneda: '', tipo_importe: '', descripcion: '' })
  const [errors, setErrors] = useState({})
  const [preview, setPreview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const key = useRef(null)
  const locked = useRef(false)
  const rawPage = new URLSearchParams(location.search).get('page') ?? '1'
  const backPage = /^\d+$/.test(rawPage) && Number(rawPage) >= 1 && Number(rawPage) <= 2147483647 ? rawPage : '1'
  const backState = quoteListFilter(new URLSearchParams(location.search).get('estado'))
  const load = useCallback((signal) => getQuoteRequest(requestId, { signal }), [requestId])
  const { data: loaded, error: loadError, isLoading: loading } = useHistoryResource(`${requestId}:${refresh}`, load)
  const detail = request || loaded
  useEffect(() => {
    const update = (event) => { if (event.detail === requestId) { setError(''); setRefresh((value) => value + 1) } }
    window.addEventListener('aari:consultas-cambiaron', update)
    return () => window.removeEventListener('aari:consultas-cambiaron', update)
  }, [requestId])
  const change = (e) => { setFields({ ...fields, [e.target.name]: e.target.value }); setErrors({ ...errors, [e.target.name]: '' }); setPreview(false); key.current = null }
  const review = (e) => {
    e.preventDefault()
    if (detail?.consulta_tecnica && !detail.consulta_tecnica.consultas_cerradas_en) {
      setError('Finalizá las consultas con el inquilino antes de enviar el presupuesto.')
      return
    }
    const invalid = {}
    if (!positiveAmount(fields.monto)) invalid.monto = 'Ingresá un importe positivo, sin separadores de miles y con hasta dos decimales.'
    if (!fields.moneda) invalid.moneda = 'Elegí la moneda.'
    if (!fields.tipo_importe) invalid.tipo_importe = 'Indicá si el importe es exacto o mínimo.'
    if (fields.descripcion.trim().length < 10) invalid.descripcion = 'Describí el trabajo con al menos 10 caracteres.'
    setErrors(invalid)
    setPreview(!Object.keys(invalid).length)
  }
  const send = async () => {
    if (locked.current) return
    locked.current = true
    setBusy(true)
    setError('')
    key.current ??= crypto.randomUUID()
    try {
      const updated = await submitQuote(requestId, { ...fields, monto: positiveAmount(fields.monto), descripcion: fields.descripcion.trim(), request_id: key.current })
      setRequest(updated)
      setPreview(false)
    } catch (e) { setError(e.message); setPreview(false); if (e.status === 409) setRefresh((n) => n + 1) }
    finally { setBusy(false); locked.current = false }
  }
  return <PageContainer>
    <Link className={styles.requestLink} to={`/proveedor?${new URLSearchParams({ page: backPage, estado: backState })}`}><ArrowLeft aria-hidden="true" />Volver a mis solicitudes</Link>
    {loading ? <LoadingState label="Cargando solicitud" /> : (error || loadError) && !detail ? <div className={styles.panelBody}><AlertMessage>{error || loadError}</AlertMessage><Button onClick={() => setRefresh((n) => n + 1)} variant="secondary">Reintentar</Button></div> : detail ? <QuoteContent request={detail} error={error} busy={busy} fields={fields} errors={errors} change={change} review={review} send={send} preview={preview} setPreview={setPreview} /> : null}
  </PageContainer>
}

function QuoteContent({ request, error, busy, fields, errors, change, review, send, preview, setPreview }) {
  const questionsOpen = request.consulta_tecnica && !request.consulta_tecnica.consultas_cerradas_en
  return <>
      <PageHeading eyebrow="Solicitud de presupuesto" title={`Reclamo #${String(request.numero).padStart(6, '0')}`} description={request.ubicacion} />
      <section className={styles.panel}><div className={styles.panelHeading}><h2>Trabajo solicitado</h2><StatusBadge tone={request.estado === 'respondida' ? 'success' : 'neutral'}>{quoteLabels[request.estado]}</StatusBadge></div><div className={styles.panelBody}><p>{request.descripcion}</p><p className={styles.muted}>Plazo hasta: {quoteDate(request.vence_en)} (Argentina). La solicitud no confirma una contratación ni una visita.</p></div></section>
      {error ? <AlertMessage>{error}</AlertMessage> : null}
      <QuestionsButton request={request} />
      {request.presupuesto ? <section className={styles.panel}><div className={styles.panelHeading}><h2>Tu presupuesto enviado</h2></div><div className={styles.panelBody}><strong>{quoteAmount(request.presupuesto)}</strong>{request.presupuesto.tipo_importe === 'minimo' ? <p className={styles.muted}>Importe mínimo: el precio final puede ser mayor. No es un máximo autorizado.</p> : <p className={styles.muted}>Importe exacto informado por el proveedor.</p>}<p>{request.presupuesto.descripcion}</p><p className={styles.muted}>Enviado: {quoteDate(request.presupuesto.recibido_en)}. No se puede sobrescribir desde esta pantalla.</p></div></section> : request.puede_responder ? <section className={styles.panel}><div className={styles.panelHeading}><h2>Prepará tu presupuesto</h2></div><form className={styles.panelBody} noValidate onSubmit={review}>
        <div className={styles.quoteGrid}>
          <FormField id="quote-kind" label="Tipo de importe" error={errors.tipo_importe} required><SelectInput name="tipo_importe" value={fields.tipo_importe} onChange={change} disabled={busy}><option value="">Seleccioná una opción</option><option value="exacto">Importe exacto</option><option value="minimo">Desde / importe mínimo</option></SelectInput></FormField>
          <FormField id="quote-currency" label="Moneda" error={errors.moneda} required><SelectInput name="moneda" value={fields.moneda} onChange={change} disabled={busy}><option value="">Seleccioná moneda</option><option value="ARS">Pesos argentinos (ARS)</option><option value="USD">Dólares (USD)</option></SelectInput></FormField>
          <FormField id="quote-amount" label={fields.tipo_importe === 'minimo' ? 'Importe mínimo' : 'Importe'} hint="Sin puntos de miles. Ejemplo: 10000 o 10000,50." error={errors.monto} required><TextInput inputMode="decimal" name="monto" value={fields.monto} onChange={change} maxLength={13} disabled={busy} /></FormField>
        </div>
        {fields.tipo_importe === 'minimo' ? <p className={styles.deliveryNotice}>Se mostrará como «Desde». Es un piso del costo, no el precio final ni un máximo.</p> : null}
        <FormField id="quote-description" label="Descripción y alcance del trabajo" error={errors.descripcion} required><textarea className={styles.quoteText} name="descripcion" rows={4} maxLength={2000} value={fields.descripcion} onChange={change} disabled={busy} /></FormField>
        {preview ? <div className={styles.quotePreview} aria-live="polite"><h3>Revisá antes de confirmar</h3><strong>{quoteAmount({ ...fields, monto: positiveAmount(fields.monto) })}</strong><p>{fields.descripcion.trim()}</p><p className={styles.muted}>Quedará registrado para la inmobiliaria y el responsable. No confirma contratación. El importe no se sobrescribirá después del envío.</p><div className={styles.actions}><Button disabled={busy} onClick={() => setPreview(false)} variant="secondary">Corregir</Button><Button disabled={busy || questionsOpen} onClick={send} leadingIcon={<Send />}>{busy ? 'Enviando…' : 'Confirmar presupuesto'}</Button></div></div> : <div className={styles.actions}><Button type="submit" disabled={busy || questionsOpen}>Revisar presupuesto</Button></div>}
      </form></section> : <AlertMessage tone="info">Esta solicitud ya no está habilitada para responder. Podés consultar su información sin reabrir el intento.</AlertMessage>}
      {request.conversacion_habilitada ? <ConversationLauncher requestId={request.id} /> : null}
    </>
}
export default ProviderQuoteDetailPage
