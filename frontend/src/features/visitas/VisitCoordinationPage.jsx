import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { MessageSquare, RefreshCw } from 'lucide-react'
import { PageContainer, PageHeading } from '../../components/layout/index.js'
import { AlertMessage, Button, FormField, LoadingState, TextInput } from '../../components/ui/index.js'
import { useConversationDock } from '../conversaciones/conversationContext.js'
import { argentineTime, getVisit, visitAction, visitDate, visitLabels } from './visitsApi.js'
import VisitFollowup from './VisitFollowup.jsx'
import styles from './Visits.module.css'

export default function VisitCoordinationPage() {
  const { reclamoId } = useParams()
  return <VisitDetail key={reclamoId} claim={reclamoId} />
}

function VisitDetail({ claim }) {
  const [data, setData] = useState(null), [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [uncertain, setUncertain] = useState(false)
  const lock = useRef(false), pending = useRef(null), alive = useRef(false), request = useRef(null), heading = useRef(null)
  const dock = useConversationDock()
  const load = useCallback(async (preserveError = false) => {
    if (lock.current) return
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    try {
      const result = await getVisit(claim, { signal: controller.signal })
      if (alive.current && !controller.signal.aborted) { setData(result); if (!preserveError) setError('') }
    } catch (failure) {
      if (alive.current && failure.name !== 'AbortError' && !controller.signal.aborted) { setError(failure.message); setData(null) }
    } finally { if (alive.current && !controller.signal.aborted) setLoading(false) }
  }, [claim])
  useEffect(() => {
    alive.current = true
    void Promise.resolve().then(load)
    const timer = setInterval(() => { if (document.visibilityState !== 'hidden') load() }, 8000)
    return () => { alive.current = false; pending.current?.abort(); clearInterval(timer) }
  }, [load])

  const send = async (action, values = {}) => {
    if (lock.current || (!data && !request.current)) return
    lock.current = true
    pending.current?.abort()
    setBusy(true); setError('')
    if (!request.current) request.current = { action, body: { ...values, request_id: crypto.randomUUID(), coordinacion_id: data.id, version_esperada: data.version } }
    try {
      const result = await visitAction(claim, request.current.action, request.current.body)
      if (!alive.current) return
      setData(result); setUncertain(false); request.current = null
      heading.current?.focus()
      window.dispatchEvent(new Event('aari:visita-cambio'))
    } catch (failure) {
      if (!alive.current) return
      setError(failure.message)
      if ([400, 403, 404, 409, 422].includes(failure.status)) { request.current = null; setUncertain(false) }
      else setUncertain(true)
    } finally {
      lock.current = false
      if (alive.current) { setBusy(false); if (!request.current) load(true) }
    }
  }
  return <PageContainer className={styles.page}>
    <Link className={styles.back} to="/visitas">Volver a mis visitas</Link>
    <PageHeading eyebrow="Coordinación de visita" title={data ? `Reclamo #${String(data.numero).padStart(6, '0')}` : 'Coordinar visita'} description="Acordá el encuentro desde AARI. Todos los horarios corresponden a Argentina." />
    {error ? <AlertMessage>{error}</AlertMessage> : null}
    {uncertain ? <div className={styles.notice}><AlertMessage tone="warning">No sabemos si la acción quedó guardada. Conservamos el mismo envío para evitar duplicarla. No cambies los datos hasta comprobar el resultado.</AlertMessage><Button disabled={busy} onClick={() => send()}>Reintentar el mismo envío</Button></div> : null}
    {loading ? <LoadingState label="Consultando coordinación" /> : data ? <>
      <section className={styles.card} aria-labelledby="visit-current"><div className={styles.heading}><h2 ref={heading} tabIndex={-1} id="visit-current">{visitLabels[data.etapa]}</h2><Button variant="secondary" leadingIcon={<RefreshCw />} disabled={busy} onClick={() => load()}>Actualizar</Button></div>
        <p><strong>{data.proveedor}</strong> · {data.ubicacion}</p><p className={styles.muted}>Urgencia del reclamo: {data.urgencia}. La coordinación no cambia el presupuesto aprobado.</p>
        {data.vence_en && data.etapa !== 'confirmada' ? <p>Plazo para acordar: <strong>{visitDate(data.vence_en)}</strong>. Los mensajes no amplían este plazo.</p> : null}
        {data.etapa === 'confirmada' ? <div className={styles.notice}><AlertMessage tone="success">Visita confirmada: {visitDate(data.fecha_confirmada)} (Argentina). La reparación todavía no está marcada como resuelta.</AlertMessage></div> : null}
        {data.etapa === 'confirmada' && data.puede_conversar && data.hilo_id && dock?.enabled ? <Button
          variant="secondary" leadingIcon={<MessageSquare />} onClick={() => dock.openThread(data.hilo_id)}>
          Abrir conversación de coordinación
        </Button> : null}
        {!data.acciones.length && data.etapa !== 'confirmada' ? <p className={styles.muted}>{data.motivo_solo_lectura}</p> : null}
      </section>
      {data.acciones.includes('disponibilidad') ? <AvailabilityForm disabled={busy || uncertain} onSubmit={(values) => send('disponibilidad', values)} /> : null}
      {data.opciones.length > 0 && data.etapa !== 'confirmada' ? <section className={styles.card}><h2>Horarios propuestos por el inquilino</h2><ul className={styles.options}>{data.opciones.map((option) => <li key={option.id}>{visitDate(option.desde)} a {visitDate(option.hasta)}</li>)}</ul>
        {data.acciones.includes('confirmar') && data.etapa === 'esperando_confirmacion' ? <DirectConfirmation options={data.opciones} disabled={busy || uncertain} onSubmit={(values) => send('confirmar', values)} /> : null}
        {data.acciones.includes('sin-coincidencia') ? <div className={styles.notice}><p>¿Ninguna opción te sirve? Podés abrir una conversación con el inquilino para buscar otro horario.</p><Button variant="secondary" disabled={busy || uncertain} onClick={() => send('sin-coincidencia')}>No puedo en estos horarios</Button></div> : null}
      </section> : null}
      {data.etapa === 'negociando' ? <section className={styles.card}><h2>Busquen otro horario</h2><p>Conversen y registren una propuesta. La visita sólo queda programada cuando la otra persona la confirma.</p>
        {data.hilo_id && dock?.enabled ? <Button className={styles.conversationAction} variant="secondary" leadingIcon={<MessageSquare />} onClick={() => dock.openThread(data.hilo_id)}>Abrir conversación de coordinación</Button> : <p className={styles.muted}>Mensajes todavía no está disponible. Podés actualizar o registrar la propuesta desde acá.</p>}
        {data.propuesta ? <div className={styles.notice}><h3>Propuesta pendiente de acuerdo</h3><p>{visitDate(data.propuesta.fecha)} (Argentina)</p><p>{data.propuesta.propia ? 'Esperando la confirmación de la otra persona.' : 'La otra persona propuso este horario.'}</p>{data.acciones.includes('confirmar') ? <Button disabled={busy || uncertain} onClick={() => send('confirmar', { propuesta_version: data.propuesta.version })}>Confirmar esta propuesta</Button> : null}</div> : null}
        {data.acciones.includes('proponer') ? <ProposalForm disabled={busy || uncertain} onSubmit={(values) => send('proponer', values)} /> : null}
      </section> : null}
      {data.etapa === 'sin_acuerdo' ? <AlertMessage tone="warning">No se confirmó la visita en plazo. El responsable debe revisar cómo continuar. El historial se conserva; cancelar o elegir otro proveedor corresponde a ese recorrido.</AlertMessage> : null}
      <VisitFollowup data={data} disabled={busy || uncertain} send={send} />
    </> : <div className={styles.actions}><Button variant="secondary" onClick={() => load()}>Volver a consultar</Button></div>}
  </PageContainer>
}

const emptySlot = () => ({ date: '', start: '', end: '', id: crypto.randomUUID() })
function AvailabilityForm({ disabled, onSubmit }) {
  const [slots, setSlots] = useState(() => [emptySlot(), emptySlot(), emptySlot()]), [error, setError] = useState('')
  const form = useRef(null)
  const change = (id, name, value) => { setSlots((old) => old.map((slot) => slot.id === id ? { ...slot, [name]: value } : slot)); setError('') }
  const submit = (event) => {
    event.preventDefault()
    const invalid = slots.find((slot) => !slot.date || !slot.start || !slot.end || slot.start >= slot.end || new Date(argentineTime(slot.date, slot.start)) <= new Date())
    if (invalid || new Set(slots.map((slot) => slot.date)).size !== slots.length) {
      setError('Completá al menos tres fechas distintas y futuras. La hora hasta debe ser posterior a la hora desde.'); form.current?.querySelector('input')?.focus(); return
    }
    onSubmit({ opciones: slots.map((slot) => ({ desde: argentineTime(slot.date, slot.start), hasta: argentineTime(slot.date, slot.end) })) })
  }
  return <form ref={form} className={styles.card} onSubmit={submit} noValidate><h2>¿Cuándo podés recibir al proveedor?</h2><p>Elegí al menos tres días diferentes e indicá el intervalo en que estarás disponible.</p>{error ? <AlertMessage>{error}</AlertMessage> : null}
    {slots.map((slot, index) => <fieldset className={styles.slot} key={slot.id} disabled={disabled}><legend>Opción {index + 1}</legend><div className={styles.fields}>
      <FormField id={`${slot.id}-day`} label="Fecha" required><TextInput type="date" value={slot.date} onChange={(e) => change(slot.id, 'date', e.target.value)} /></FormField>
      <FormField id={`${slot.id}-start`} label="Desde" required><TextInput type="time" value={slot.start} onChange={(e) => change(slot.id, 'start', e.target.value)} /></FormField>
      <FormField id={`${slot.id}-end`} label="Hasta" required><TextInput type="time" value={slot.end} onChange={(e) => change(slot.id, 'end', e.target.value)} /></FormField></div>
      {slots.length > 3 ? <Button variant="ghost" onClick={() => setSlots((old) => old.filter((s) => s.id !== slot.id))}>Quitar opción {index + 1}</Button> : null}</fieldset>)}
    <div className={styles.actions}>{slots.length < 10 ? <Button variant="secondary" disabled={disabled} onClick={() => setSlots((old) => [...old, emptySlot()])}>Agregar otra fecha</Button> : null}<Button type="submit" disabled={disabled}>Enviar horarios al proveedor</Button></div></form>
}

function DirectConfirmation({ options, disabled, onSubmit }) {
  const [chosen, setChosen] = useState(''), [time, setTime] = useState(''), [error, setError] = useState('')
  const submit = (event) => {
    event.preventDefault()
    const option = options.find((o) => o.id === chosen)
    const day = option ? new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(option.desde)) : ''
    const value = day && time ? argentineTime(day, time) : ''
    if (!option || !value || new Date(value) < new Date(option.desde) || new Date(value) >= new Date(option.hasta) || new Date(value) <= new Date()) { setError('Seleccioná una opción y una hora futura dentro del intervalo.'); return }
    setError(''); onSubmit({ fecha: value })
  }
  return <form onSubmit={submit} className={styles.notice} noValidate><h3>Confirmá cuándo vas a ir</h3><FormField id="visit-option" label="Día e intervalo" required><select className={styles.input} disabled={disabled} value={chosen} onChange={(e) => { setChosen(e.target.value); setError('') }}><option value="">Elegí una opción</option>{options.map((o) => <option key={o.id} value={o.id}>{visitDate(o.desde)} a {visitDate(o.hasta)}</option>)}</select></FormField>
    <FormField id="visit-time" label="Hora de llegada" error={error} required><TextInput type="time" value={time} disabled={disabled} onChange={(e) => { setTime(e.target.value); setError('') }} /></FormField><div className={styles.actions}><Button type="submit" disabled={disabled}>Confirmar visita</Button></div></form>
}

function ProposalForm({ disabled, onSubmit }) {
  const [day, setDay] = useState(''), [time, setTime] = useState(''), [error, setError] = useState('')
  const submit = (e) => {
    e.preventDefault()
    const value = day && time ? argentineTime(day, time) : ''
    if (!value || new Date(value) <= new Date()) { setError('Completá una fecha y hora futuras.'); return }
    setError(''); onSubmit({ fecha: value })
  }
  return <form className={styles.notice} onSubmit={submit} noValidate><h3>Proponer fecha y hora</h3><p>La otra persona debe aceptarla. No se confirma automáticamente.</p><div className={styles.proposal}>
    <FormField id="visit-proposal-day" label="Fecha" required><TextInput type="date" value={day} disabled={disabled} onChange={(e) => setDay(e.target.value)} /></FormField>
    <FormField id="visit-proposal-time" label="Hora" error={error} required><TextInput type="time" value={time} disabled={disabled} onChange={(e) => setTime(e.target.value)} /></FormField></div><div className={styles.actions}><Button type="submit" disabled={disabled}>Enviar propuesta para confirmar</Button></div></form>
}
