import { useCallback, useRef, useState } from 'react'
import { ArrowLeft, Check, RefreshCw } from 'lucide-react'
import { Link, useLocation, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, FormField, LoadingState, SelectInput, StatusBadge } from '../../../components/ui/index.js'
import { escalatedPhotoUrl, getEscalatedClaim, resolveEscalatedClaim } from '../api/escaladosApi.js'
import { escalationReason, MANUAL_OPTIONS, validateManualDecision } from '../escalados.js'
import { formatClaimDate, formatClaimNumber, urgencyLabel, claimStatusTone } from '../presentation.js'
import { claimPropertyLabel } from '../validation.js'
import { useHistoryResource } from '../useHistoryResource.js'
import styles from './Escalados.module.css'

function ClaimPhoto({ claimId, photo, index }) {
  const [unavailable, setUnavailable] = useState(false)
  const url = escalatedPhotoUrl(claimId, photo.id)
  return <a href={url} target="_blank" rel="noreferrer">
    {unavailable ? <span>No se pudo cargar la foto. Abrila para volver a intentar.</span>
      : <img src={url} alt={`Foto ${index + 1} del reclamo`} onError={() => setUnavailable(true)} />}
    <span>Abrir foto {index + 1}</span>
  </a>
}

function EscalatedClaimDetailPage({ operatorView = false }) {
  const { reclamoId } = useParams()
  const location = useLocation()
  const [refresh, setRefresh] = useState(0)
  const load = useCallback((signal) => getEscalatedClaim(reclamoId, { signal }), [reclamoId])
  const { data: claim, error, isLoading } = useHistoryResource(`${reclamoId}:${refresh}`, load)
  const [expense, setExpense] = useState('')
  const [reason, setReason] = useState('')
  const [errors, setErrors] = useState({})
  const [saveError, setSaveError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const submitting = useRef(false)
  const base = operatorView ? '/operador/escalados' : '/escalados'
  const selection = MANUAL_OPTIONS[expense]
  const canSubmit = !Object.keys(validateManualDecision(expense, reason)).length

  const submit = async (event) => {
    event.preventDefault()
    if (submitting.current || !claim?.puede_resolver || conflict) return
    const validation = validateManualDecision(expense, reason)
    setErrors(validation)
    if (Object.keys(validation).length) return
    submitting.current = true
    setSaving(true)
    setSaveError('')
    try {
      await resolveEscalatedClaim(reclamoId, {
        tipo_gasto: expense, fundamento: reason.trim(), expected_updated_at: claim.updated_at,
      })
      setSaved(true)
      setRefresh((value) => value + 1)
    } catch (failure) {
      setSaveError(failure.message)
      setConflict(failure.status === 409)
      const detail = failure.body?.detail
      if (Array.isArray(detail)) {
        setErrors(Object.fromEntries(detail.filter((item) => item.loc?.[0] === 'body')
          .map((item) => [item.loc.at(-1), 'Revisá este campo antes de confirmar.'])))
      } else if (detail?.field) setErrors({ [detail.field]: detail.message })
    } finally {
      submitting.current = false
      setSaving(false)
    }
  }
  const reload = () => {
    setConflict(false)
    setSaveError('')
    setExpense('')
    setReason('')
    setErrors({})
    setRefresh((value) => value + 1)
  }

  return (
    <PageContainer className={styles.detailPage}>
      <Link className={styles.backLink} to={`${base}${location.search}`}><ArrowLeft aria-hidden="true" />Volver a casos escalados</Link>
      {saved ? <AlertMessage tone="success">La clasificación manual quedó guardada. El reclamo continúa con la gestión del responsable; la reparación todavía no está resuelta.</AlertMessage> : null}
      {error ? <AlertMessage>{error}</AlertMessage> : null}
      {isLoading ? <LoadingState label="Cargando el caso para revisión" lines={6} /> : null}
      {claim && !error ? <>
        <PageHeading eyebrow="Revisión de la inmobiliaria" title={`Reclamo ${formatClaimNumber(claim.numero)}`}
          description={claimPropertyLabel(claim.propiedad)} action={<StatusBadge tone={claimStatusTone(claim.estado)}>{claim.estado}</StatusBadge>} />
        <div className={styles.detailGrid}>
          <section className={styles.panel} aria-labelledby="case-information">
            <div className={styles.panelHeading}><h2 id="case-information">Información del caso</h2></div>
            <div className={styles.panelBody}>
              <p className={styles.fullDescription}>{claim.descripcion}</p>
              <dl className={styles.metadata}>
                <div><dt>Inquilino</dt><dd>{claim.inquilino_nombre}</dd></div>
                <div><dt>Urgencia declarada</dt><dd>{urgencyLabel(claim.urgencia)}</dd></div>
                <div><dt>Fecha de ingreso</dt><dd>{formatClaimDate(claim.creado_en)}</dd></div>
                <div><dt>Motivo de revisión</dt><dd>{escalationReason(claim.motivo_escalado
                  ?? claim.decisiones.at(-1)?.resultado_anterior.motivo_escalado)}</dd></div>
              </dl>
              {claim.fundamento_clasificacion ? <div><h3>Fundamento registrado</h3><p>{claim.fundamento_clasificacion}</p></div> : null}
              {claim.confianza_clasificacion != null ? <p className={styles.hint}>Confianza del agente: {Math.round(claim.confianza_clasificacion * 100)} %.</p> : null}
              {claim.fotos.length ? <div><h3>Fotos del reclamo</h3><div className={styles.photos}>
                {claim.fotos.map((photo, index) => <ClaimPhoto key={photo.id} claimId={claim.id} photo={photo} index={index} />)}
              </div></div> : <p className={styles.hint}>Este reclamo no tiene fotos adjuntas.</p>}
            </div>
          </section>
          <section className={styles.panel} aria-labelledby="case-history">
            <div className={styles.panelHeading}><h2 id="case-history">Historial del reclamo</h2></div>
            <div className={styles.panelBody}>
              {claim.historial.length ? <ol className={styles.timeline}>{[...claim.historial].reverse().map((item, index) => <li key={`${item.timestamp}:${index}`}>
                <strong>{item.estado_nuevo}</strong><time dateTime={item.timestamp}>{formatClaimDate(item.timestamp)}</time><small>Origen: {item.origen}</small>
              </li>)}</ol> : <p className={styles.hint}>Todavía no hay transiciones registradas.</p>}
              {claim.decisiones.map((decision) => <div key={decision.id} className={styles.audit}>
                <h3>Decisión manual: {MANUAL_OPTIONS[decision.tipo_gasto]?.label}</h3>
                <p>{decision.fundamento}</p><small>{decision.usuario_nombre} · {decision.rol} · {formatClaimDate(decision.decidido_en)}</small>
                <details><summary>Ver resultado anterior del agente</summary>
                  <p>{escalationReason(decision.resultado_anterior.motivo_escalado)}</p>
                  <p>{decision.resultado_anterior.fundamento || 'Sin fundamento disponible.'}</p>
                  {decision.resultado_anterior.confianza != null ? <p>Confianza original: {Math.round(decision.resultado_anterior.confianza * 100)} %.</p> : null}
                </details>
              </div>)}
            </div>
          </section>
        </div>
        {claim.puede_resolver && !saved ? <form className={styles.panel} onSubmit={submit} noValidate>
          <div className={styles.panelHeading}><div><h2>Clasificación manual</h2><p>Tomá una decisión con la información del caso. No volveremos a consultar al modelo.</p></div></div>
          <div className={styles.panelBody}>
            {saveError ? <AlertMessage>{saveError}</AlertMessage> : null}
            {conflict ? <Button variant="secondary" leadingIcon={<RefreshCw />} onClick={reload}>Actualizar el caso</Button> : null}
            <FormField id="manual-expense" label="Tipo de gasto" required error={errors.tipo_gasto}>
              <SelectInput value={expense} disabled={saving || conflict} onChange={(event) => setExpense(event.target.value)}>
                <option value="">Seleccioná una clasificación</option>
                {Object.entries(MANUAL_OPTIONS).map(([value, option]) => <option key={value} value={value}>{option.label}</option>)}
              </SelectInput>
            </FormField>
            <FormField id="manual-reason" label="Fundamento de la decisión" required error={errors.fundamento}
              hint="Entre 10 y 1000 caracteres. Explicá por qué corresponde esta clasificación.">
              <textarea className={styles.textarea} value={reason} maxLength={1000} disabled={saving || conflict}
                onChange={(event) => setReason(event.target.value)} />
            </FormField>
            {selection ? <p className={styles.nextStep}>Se clasificará como {selection.label.toLowerCase()} y se notificará al {selection.actor} para continuar la gestión.</p> : null}
            {claim.motivo_escalado === 'riesgo_seguridad' ? <AlertMessage tone="warning">Clasificar el gasto no elimina el riesgo de seguridad. La inmobiliaria debe atender la urgencia antes de continuar con trabajos.</AlertMessage> : null}
          </div>
          <div className={styles.formActions}><Button type="submit" leadingIcon={<Check />} disabled={!canSubmit || saving || conflict}>{saving ? 'Guardando decisión…' : 'Confirmar clasificación'}</Button></div>
        </form> : !saved ? <AlertMessage tone="warning">Este caso ya fue clasificado o avanzó de etapa. No se puede reemplazar su gestión desde esta pantalla.</AlertMessage> : null}
      </> : null}
    </PageContainer>
  )
}

export default EscalatedClaimDetailPage
