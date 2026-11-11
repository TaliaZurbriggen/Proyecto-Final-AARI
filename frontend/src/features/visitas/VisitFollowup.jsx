import { useState } from 'react'
import { AlertMessage, Button, FormField, SelectInput, TextInput } from '../../components/ui/index.js'
import { argentineTime, visitDate } from './visitsApi.js'
import styles from './Visits.module.css'

const statusLabels = { aceptada: 'Aceptada', rechazada: 'Rechazada', retirada: 'Retirada', vencida: 'Vencida' }
const roleLabels = { inquilino: 'Inquilino', proveedor: 'Proveedor' }
const decisionLabels = { aceptar: 'Aceptar nuevo horario', rechazar: 'Rechazar propuesta', retirar: 'Retirar propuesta' }
const absenceLabels = { no_realizada: 'La visita no se realizó', contraparte_ausente: 'La otra parte no asistió' }

export default function VisitFollowup({ data, disabled, send }) {
  const followup = data.seguimiento
  if (!followup) return null
  const { propuesta_pendiente: pending, decisiones, reprogramaciones, ausencias } = followup

  return <>
    {pending ? <section className={styles.card} aria-labelledby="visit-reschedule-pending">
      <h2 id="visit-reschedule-pending">Cambio de horario pendiente</h2>
      <dl className={styles.proposal}>
        <div><dt>Horario vigente</dt><dd>{visitDate(pending.fecha_anterior)}</dd></div>
        <div><dt>Horario propuesto</dt><dd>{visitDate(pending.fecha_propuesta)}</dd></div>
      </dl>
      <p>{roleLabels[pending.solicitante_rol]} · {pending.motivo}</p>
      <p className={styles.muted}>La propuesta vence el {visitDate(pending.vence_en)}.</p>
      {decisiones.length ? <div className={styles.actions}>
        {decisiones.map((decision) => <Button key={decision} disabled={disabled}
          variant={decision === 'aceptar' ? 'primary' : 'secondary'}
          onClick={() => send('decidir-reprogramacion', { propuesta_id: pending.id, decision })}>
          {decisionLabels[decision]}
        </Button>)}
      </div> : null}
    </section> : null}
    {data.acciones.includes('reprogramar') ? <RescheduleForm disabled={disabled} current={data.fecha_confirmada}
      submit={(values) => send('reprogramar', values)} /> : null}
    {data.acciones.includes('informar-ausencia') ? <AbsenceForm disabled={disabled}
      submit={(values) => send('informar-ausencia', values)} /> : null}
    {reprogramaciones.length || ausencias.length ? <section className={styles.card} aria-labelledby="visit-followup-history">
      <h2 id="visit-followup-history">Historial de la visita</h2>
      {reprogramaciones.length ? <>
        <h3>Reprogramaciones</h3>
        <ul className={styles.history}>{reprogramaciones.map((entry) => <li key={entry.id}>
          <strong>{statusLabels[entry.estado]}</strong> · {visitDate(entry.decidida_en)}
          <p>{visitDate(entry.fecha_anterior)} → {visitDate(entry.fecha_propuesta)}</p>
          <p>{roleLabels[entry.solicitante_rol]} propuso el {visitDate(entry.creada_en)}. {entry.motivo}</p>
          {entry.decision_rol ? <p>Decisión de {roleLabels[entry.decision_rol].toLowerCase()}.</p> : null}
        </li>)}</ul>
      </> : null}
      {ausencias.length ? <>
        <h3>Reportes de ausencia</h3>
        <ul className={styles.history}>{ausencias.map((report) => <li key={report.id}>
          <strong>{roleLabels[report.autor_rol]} · {absenceLabels[report.tipo]}</strong>
          <p>Visita del {visitDate(report.fecha_visita)} · Reporte del {visitDate(report.creada_en)}</p>
          <p>{report.observaciones}</p>
        </li>)}</ul>
      </> : null}
    </section> : null}
  </>
}

function RescheduleForm({ disabled, current, submit }) {
  const [error, setError] = useState('')
  function onSubmit(event) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const fecha = argentineTime(fields.get('day'), fields.get('time'))
    const motivo = fields.get('reason').trim()
    if (!motivo || !(new Date(fecha) > new Date()) || Date.parse(fecha) === Date.parse(current)) {
      setError('Ingresá un horario futuro, distinto del confirmado, y un motivo.')
      return
    }
    setError('')
    submit({ fecha, motivo })
  }
  return <form className={styles.card} onSubmit={onSubmit} aria-labelledby="visit-reschedule-title">
    <h2 id="visit-reschedule-title">Proponer otro horario</h2>
    <p>El horario actual se mantiene hasta que la otra persona acepte.</p>
    {error ? <AlertMessage>{error}</AlertMessage> : null}
    <div className={styles.proposal}>
      <FormField id="reschedule-day" label="Nueva fecha" required><TextInput name="day" type="date" disabled={disabled} /></FormField>
      <FormField id="reschedule-time" label="Nueva hora" required><TextInput name="time" type="time" disabled={disabled} /></FormField>
    </div>
    <div className={styles.notice}>
      <FormField id="reschedule-reason" label="Motivo" required>
        <textarea className={styles.input} name="reason" rows={2} maxLength={500} disabled={disabled} />
      </FormField>
    </div>
    <div className={styles.actions}><Button type="submit" disabled={disabled}>Enviar propuesta</Button></div>
  </form>
}

function AbsenceForm({ disabled, submit }) {
  const [error, setError] = useState('')
  function onSubmit(event) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const observaciones = fields.get('observations').trim()
    if (!observaciones) { setError('Escribí qué pasó durante la visita.'); return }
    setError('')
    submit({ tipo: fields.get('kind'), observaciones })
  }
  return <form className={styles.card} onSubmit={onSubmit} aria-labelledby="visit-absence-title">
    <h2 id="visit-absence-title">Informar qué pasó en la visita</h2>
    {error ? <AlertMessage>{error}</AlertMessage> : null}
    <div className={styles.notice}>
      <FormField id="absence-kind" label="Resultado informado" required>
        <SelectInput name="kind" defaultValue="" disabled={disabled}>
          <option value="" disabled>Elegí un resultado</option>
          {Object.entries(absenceLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectInput>
      </FormField>
      <FormField id="absence-observations" label="Observaciones" required>
        <textarea className={styles.input} name="observations" rows={3} maxLength={500} disabled={disabled} />
      </FormField>
    </div>
    <div className={styles.actions}><Button type="submit" disabled={disabled}>Registrar reporte</Button></div>
  </form>
}
