import { useCallback, useRef, useState } from 'react'
import { Building2, UserRoundCheck } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { chooseProviderType, getProviderChoice } from '../api/providerChoicesApi.js'
import { claimStatusTone, formatClaimDate, formatClaimNumber } from '../presentation.js'
import { useHistoryResource } from '../useHistoryResource.js'
import styles from './ProviderChoicePage.module.css'
import ClaimQuoteSummary from '../../proveedores/components/ClaimQuoteSummary.jsx'

export default function ProviderChoicePage({ ownerView = false }) {
  const { reclamoId } = useParams()
  return <ChoiceContent key={reclamoId} reclamoId={reclamoId} ownerView={ownerView} />
}

function ChoiceContent({ reclamoId, ownerView }) {
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [choiceError, setChoiceError] = useState('')
  const [result, setResult] = useState(null)
  const [lockedChoice, setLockedChoice] = useState('')
  const attempt = useRef(null)
  const load = useCallback((signal) => getProviderChoice(reclamoId, { signal }), [reclamoId])
  const { data: claim, error, isLoading } = useHistoryResource(`${reclamoId}:${revision}`, load)
  const choose = async (choice) => {
    if (!claim || busy) return
    if (!attempt.current) {
      attempt.current = { choice, body: { tipo_proveedor: choice, solicitud_id: claim.solicitud_id,
        request_id: crypto.randomUUID(), expected_updated_at: claim.updated_at } }
      setLockedChoice(choice)
    }
    if (attempt.current.choice !== choice) return
    setBusy(true)
    setChoiceError('')
    try {
      setResult(await chooseProviderType(reclamoId, attempt.current.body))
      setRevision((value) => value + 1)
    } catch (failure) {
      setChoiceError(failure.message)
      if (failure.status) {
        attempt.current = null
        setLockedChoice('')
        setRevision((value) => value + 1)
      }
    } finally { setBusy(false) }
  }
  const saved = result || claim?.decision
  return <PageContainer className={styles.page}>
    <Link className={styles.back} to={ownerView ? '/propietario/reclamos' : `/inquilino/reclamos/${reclamoId}`}>
      {ownerView ? 'Volver a autorizaciones' : 'Volver al reclamo'}
    </Link>
    <PageHeading eyebrow="Cómo continuar" title="Elegí el tipo de proveedor"
      description="Vos decidís si preferís trabajar con la red de la inmobiliaria o proponer un contacto propio." />
    {isLoading && <LoadingState label="Cargando elección de proveedor" />}
    {error && <AlertMessage>{error}</AlertMessage>}
    {choiceError && <AlertMessage>{choiceError}</AlertMessage>}
    {error && <Button variant="secondary" onClick={() => setRevision((value) => value + 1)}>Volver a intentar</Button>}
    {claim && <>
      <section className={styles.summary} aria-labelledby="choice-claim">
        <div className={styles.summaryHeading}><h2 id="choice-claim">Reclamo {formatClaimNumber(claim.numero)}</h2>
          <StatusBadge tone={claimStatusTone(claim.estado)}>{claim.estado}</StatusBadge></div>
        <p>{claim.propiedad.direccion} · {claim.propiedad.localidad}</p>
        <p className={styles.description}>{claim.descripcion}</p>
        {!saved && <p>Podés elegir hasta el {formatClaimDate(claim.respuesta_vence_en)}. Te recordaremos a las 48 horas; a las 72 horas sin respuesta deberá intervenir la inmobiliaria.</p>}
      </section>
      {saved ? <section className={styles.summary} aria-labelledby="choice-result">
        <h2 id="choice-result">Elección registrada: proveedor {saved.tipo_proveedor}</h2>
        <p>{saved.actor_nombre} · {formatClaimDate(saved.decidido_en)}</p>
        <AlertMessage tone="success">{saved.tipo_proveedor === 'fidelizado'
          ? 'El agente publicará solicitudes para los proveedores compatibles con acceso activo. Consultá abajo su estado; la elección no contrata a un proveedor.'
          : claim.estado === 'Derivado a proveedor externo' ? 'El contacto ya quedó registrado y el reclamo fue derivado a un proveedor externo.'
            : 'Todavía no se registró el contacto. Cargá los datos para completar la derivación.'}</AlertMessage>
        {saved.tipo_proveedor === 'propio' || claim.estado === 'Derivado a proveedor externo' ?
          <Link className={styles.back} to={`/${ownerView ? 'propietario' : 'inquilino'}/reclamos/${reclamoId}/proveedor-externo`}>
            {claim.estado === 'Derivado a proveedor externo' ? 'Ver datos del proveedor externo' : 'Cargar datos del proveedor'}
          </Link> : null}
      </section> : claim.puede_elegir ? <div className={styles.options}>
        <article className={styles.option} aria-labelledby="trusted-provider">
          <Building2 aria-hidden="true" className={styles.icon} />
          <h2 id="trusted-provider">Proveedor fidelizado</h2>
          <p>Continuar con proveedores de la red de la inmobiliaria compatibles con el reclamo.</p>
          <p className={styles.note}>El presupuesto y la contratación se gestionan en los pasos siguientes.</p>
          <Button disabled={busy || Boolean(lockedChoice && lockedChoice !== 'fidelizado')}
            onClick={() => choose('fidelizado')}>{busy && lockedChoice === 'fidelizado' ? 'Guardando…' : 'Elegir proveedor fidelizado'}</Button>
        </article>
        <article className={styles.option} aria-labelledby="own-provider">
          <UserRoundCheck aria-hidden="true" className={styles.icon} />
          <h2 id="own-provider">Proveedor propio</h2>
          <p>Proponer una persona de tu confianza para resolver el problema.</p>
          <p className={styles.note}>Después deberás registrar sus datos; esta elección aún no deriva el reclamo.</p>
          <Button variant="secondary" disabled={busy || Boolean(lockedChoice && lockedChoice !== 'propio')}
            onClick={() => choose('propio')}>{busy && lockedChoice === 'propio' ? 'Guardando…' : 'Elegir proveedor propio'}</Button>
        </article>
      </div> : <AlertMessage tone="warning">Esta solicitud ya no admite una elección. El plazo pudo vencer o la etapa pudo cambiar; contactá a la inmobiliaria para continuar.</AlertMessage>}
      {saved?.tipo_proveedor === 'fidelizado' ? <ClaimQuoteSummary claimId={reclamoId} /> : null}
    </>}
  </PageContainer>
}
