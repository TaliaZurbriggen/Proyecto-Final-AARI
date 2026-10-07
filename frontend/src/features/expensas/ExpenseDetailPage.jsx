import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, Save } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../components/layout/index.js'
import { AlertMessage, Button, FormField, LoadingState, StatusBadge } from '../../components/ui/index.js'
import { useHistoryResource } from '../reclamos/useHistoryResource.js'
import { claimPropertyLabel } from '../reclamos/validation.js'
import { formatClaimDate, formatClaimNumber } from '../reclamos/presentation.js'
import { addExpenseNote, deliveryLabels, deliveryTone, getExpense } from './api.js'
import styles from './Expensas.module.css'

function ExpenseNotes({ claimId, initialNotes }) {
  const [notes, setNotes] = useState(initialNotes)
  const [content, setContent] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const controller = useRef(null)
  useEffect(() => () => controller.current?.abort(), [])
  const submit = async (event) => {
    event.preventDefault()
    if (saving) return
    if (!content.trim()) { setError('Escribí una nota antes de guardarla.'); return }
    const abort = new AbortController()
    controller.current = abort
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const note = await addExpenseNote(claimId, content.trim(), { signal: abort.signal })
      if (!abort.signal.aborted) { setNotes((current) => [note, ...current]); setContent(''); setSaved(true) }
    } catch (cause) {
      if (!abort.signal.aborted) setError(cause.message)
    } finally {
      if (!abort.signal.aborted) setSaving(false)
    }
  }
  return <section className={styles.card} aria-labelledby="notes-title">
    <h2 id="notes-title">Notas internas</h2>
    <p>Solo administración y operación pueden leerlas. Las notas se conservan con autor y fecha; no se envían al inquilino.</p>
    <form onSubmit={submit} className={styles.noteForm}>
      <FormField id="expense-note" label="Nueva nota interna" error={error} hint={`${content.length}/1000 caracteres`}>
        <textarea className={styles.textarea} rows={4} maxLength={1000} value={content} disabled={saving}
          onChange={(event) => { setContent(event.target.value); setError(''); setSaved(false) }} />
      </FormField>
      <Button type="submit" leadingIcon={<Save />} disabled={saving || !content.trim()}>{saving ? 'Guardando…' : 'Guardar nota'}</Button>
      {saved ? <p role="status">Nota interna guardada.</p> : null}
    </form>
    {notes.length ? <ol className={styles.notes}>{notes.map((note) => <li key={note.id}>
      <p className={styles.multiline}>{note.contenido}</p><p className={styles.muted}>{note.autor} · <time dateTime={note.creado_en}>{formatClaimDate(note.creado_en)}</time></p>
    </li>)}</ol> : <p>Todavía no hay notas internas.</p>}
  </section>
}

export default function ExpenseDetailPage() {
  const { reclamoId } = useParams()
  const [params] = useSearchParams()
  const load = useCallback((signal) => getExpense(reclamoId, { signal }), [reclamoId])
  const { data, error, isLoading } = useHistoryResource(reclamoId, load)
  return <PageContainer>
    <Link className={styles.backLink} to={`/expensas${params.size ? `?${params}` : ''}`}><ArrowLeft aria-hidden="true" /> Volver a expensas</Link>
    {isLoading ? <LoadingState label="Cargando detalle de expensa" lines={5} /> : null}
    {error ? <AlertMessage>{error}</AlertMessage> : null}
    {data ? <>
      <PageHeading eyebrow="Evaluación de la inmobiliaria" title={`Expensa ${formatClaimNumber(data.numero)}`} description={claimPropertyLabel(data.propiedad)} />
      <section className={styles.card} aria-labelledby="delivery-title">
        <h2 id="delivery-title">Situación del reporte</h2>
        <StatusBadge tone={deliveryTone(data.entrega_estado)}>{deliveryLabels[data.entrega_estado]}</StatusBadge>
        <p>Estado del reclamo: <strong>{data.estado}</strong> · {data.intentos}/3 intentos</p>
        {data.error_entrega ? <AlertMessage>{data.error_entrega} No se confirmó una nueva derivación.</AlertMessage> : null}
        <p className={styles.muted}>Enviado significa que SMTP aceptó el mensaje, no que llegó a la bandeja o fue leído.</p>
      </section>
      <section className={styles.card} aria-labelledby="report-title">
        <h2 id="report-title">Reporte para evaluación</h2>
        <p className={styles.multiline}>{data.reporte?.descripcion ?? data.descripcion}</p>
        {data.reporte ? <dl className={styles.reportFields}>
          <dt>Unidad al generar el reporte</dt><dd>{claimPropertyLabel(data.reporte.propiedad)}</dd>
          <dt>Ingreso</dt><dd>{formatClaimDate(data.reporte.ingresado_en)}</dd>
          <dt>Clasificación</dt><dd>{formatClaimDate(data.reporte.clasificado_en)}</dd>
          <dt>Contacto del inquilino</dt><dd>{data.reporte.inquilino.nombre} · {data.reporte.inquilino.email}</dd>
          <dt>Urgencia informada</dt><dd>{data.reporte.urgencia}</dd>
          <dt>Origen</dt><dd>{data.reporte.origen}</dd>
          <dt>Fundamento</dt><dd className={styles.multiline}>{data.reporte.fundamento}</dd>
          <dt>Confianza</dt><dd>{data.reporte.confianza == null ? 'No corresponde a esta decisión' : `${Math.round(data.reporte.confianza * 100)} %`}</dd>
        </dl> : <p>Registro histórico sin reporte estructurado HU14. No se generaron correos retroactivos.</p>}
        <p className={styles.notice}>La clasificación solicita evaluación: no autoriza gastos, no asigna proveedor ni confirma resolución.</p>
      </section>
      <section className={styles.card} aria-labelledby="audit-title">
        <h2 id="audit-title">Auditoría de envíos a la inmobiliaria</h2>
        {data.envios.length ? <ul className={styles.notes}>{data.envios.map((delivery) => <li key={delivery.id}>
          <p>{delivery.canal} · {delivery.destinatario} · {deliveryLabels[delivery.estado] ?? delivery.estado}</p>
          <p>{delivery.intentos}/3 intentos · {delivery.enviado_en ? `Aceptado el ${formatClaimDate(delivery.enviado_en)}` : 'Sin aceptación registrada'}</p>
          {delivery.error ? <p>{delivery.error}</p> : null}
        </li>)}</ul> : <p>No hay envíos registrados para esta expensa.</p>}
      </section>
      <ExpenseNotes key={reclamoId} claimId={reclamoId} initialNotes={data.notas} />
    </> : null}
  </PageContainer>
}
