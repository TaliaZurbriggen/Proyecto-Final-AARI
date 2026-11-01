import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, FormField, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { getExternalProvider, registerExternalProvider, validateExternalProvider } from '../api/externalProvidersApi.js'
import { useHistoryResource } from '../useHistoryResource.js'
import { formatClaimDate, formatClaimNumber } from '../presentation.js'
import styles from './ExternalProviderPage.module.css'

export function ExternalProviderRecord({ record }) {
  return <dl className={styles.record}>
    <div><dt>Nombre completo</dt><dd>{record.nombre}</dd></div>
    <div><dt>Teléfono</dt><dd>{record.telefono}</dd></div>
    <div><dt>Registrado por</dt><dd>{record.actor_nombre || 'Registro histórico sin autor informado'}</dd></div>
    <div><dt>Fecha de registro</dt><dd>{formatClaimDate(record.created_at)}</dd></div>
  </dl>
}

export function ExternalProviderHistory({ claimId }) {
  const [revision, setRevision] = useState(0)
  const load = useCallback((signal) => getExternalProvider(claimId, { signal }), [claimId])
  const { data, error, isLoading } = useHistoryResource(`${claimId}:${revision}`, load)
  return <section className={styles.card} aria-labelledby="external-history-title">
    <h2 id="external-history-title">Proveedor externo</h2>
    {isLoading ? <LoadingState label="Consultando contacto externo" /> : null}
    {error ? <><AlertMessage>{error}</AlertMessage><Button variant="secondary" onClick={() => setRevision(v => v + 1)}>Reintentar contacto</Button></> : null}
    {data?.registros?.length ? <ul className={styles.records}>{data.registros.map(record => <li key={record.id}><ExternalProviderRecord record={record} /></li>)}</ul>
      : data ? <p>No hay contactos externos registrados para este reclamo.</p> : null}
    <p className={styles.muted}>Estos contactos no forman parte del padrón de proveedores fidelizados.</p>
  </section>
}

export default function ExternalProviderPage({ ownerView = false }) {
  const { reclamoId } = useParams()
  return <ExternalProviderContent key={reclamoId} claimId={reclamoId} ownerView={ownerView} />
}

function ExternalProviderContent({ claimId, ownerView }) {
  const [revision, setRevision] = useState(0)
  const [values, setValues] = useState({ nombre: '', telefono: '' })
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saved, setSaved] = useState(null)
  const [uncertain, setUncertain] = useState(false)
  const attempt = useRef(null)
  const locked = useRef(false)
  const heading = useRef(null)
  const load = useCallback((signal) => getExternalProvider(claimId, { signal }), [claimId])
  const { data, error, isLoading } = useHistoryResource(`${claimId}:${revision}`, load)
  const back = `/${ownerView ? 'propietario' : 'inquilino'}/reclamos/${claimId}/tipo-proveedor`
  const record = saved?.registro || data?.registro
  useEffect(() => {
    if (saved) heading.current?.focus()
  }, [saved])

  const confirm = async (event) => {
    event.preventDefault()
    if (locked.current || !data?.puede_registrar) return
    const validation = validateExternalProvider(values)
    setErrors(validation.errors)
    if (Object.keys(validation.errors).length) {
      document.getElementById(`external-${Object.keys(validation.errors)[0]}`)?.focus()
      return
    }
    setValues(validation.normalized)
    locked.current = true
    setBusy(true)
    setSaveError('')
    attempt.current ??= { ...validation.normalized, request_id: crypto.randomUUID(), eleccion_id: data.eleccion_id,
      expected_updated_at: data.updated_at }
    try {
      setSaved(await registerExternalProvider(claimId, attempt.current))
      setUncertain(false)
      setRevision(v => v + 1)
    } catch (failure) {
      setSaveError(failure.message)
      const unknown = !failure.status || failure.status >= 500
      setUncertain(unknown)
      if (!unknown) {
        attempt.current = null
        if (failure.status === 422) {
          const details = failure.body?.detail
          const fieldErrors = Array.isArray(details) ? Object.fromEntries(details.filter(item => ['nombre', 'telefono'].includes(item.loc?.at(-1))).map(item => [item.loc.at(-1), item.msg])) : {}
          setErrors(fieldErrors)
          requestAnimationFrame(() => document.getElementById(`external-${Object.keys(fieldErrors)[0]}`)?.focus())
        } else setRevision(v => v + 1)
      }
    } finally { locked.current = false; setBusy(false) }
  }
  return <PageContainer className={styles.page}><div className={styles.content}>
    <Link className={styles.back} to={back}>Volver a la elección de proveedor</Link>
    <PageHeading eyebrow="Proveedor propio" title={record ? 'Proveedor externo registrado' : 'Cargá los datos de tu proveedor'}
      description="Registrá a la persona que elegiste para atender el reclamo, sin incorporarla a la red de la inmobiliaria." />
    {isLoading && !saved ? <LoadingState label="Cargando registro de proveedor" /> : null}
    {error ? <><AlertMessage>{error}</AlertMessage><Button variant="secondary" onClick={() => setRevision(v => v + 1)}>Volver a intentar</Button></> : null}
    {data || saved ? <>
      {data ? <section className={styles.card} aria-label="Contexto del reclamo"><strong>Reclamo {formatClaimNumber(data.numero)}</strong><p>{data.descripcion}</p>
        <p className={styles.muted}>{data.propiedad.direccion} · {data.propiedad.localidad}</p><StatusBadge>{data.estado}</StatusBadge></section> : null}
      {record ? <section className={styles.card}><h2 ref={heading} tabIndex={-1}>Contacto confirmado</h2><ExternalProviderRecord record={record} />
        <div className={styles.confirmation}>
          <AlertMessage tone="success">Proveedor externo confirmado: <strong>{record.nombre}</strong> atenderá este reclamo.</AlertMessage>
        </div>
        <p className={styles.muted}>El registro se conserva en el historial y no se reemplaza desde este formulario.</p>
      </section> : data?.puede_registrar && !error ? <section className={styles.card}>
        {saveError ? <AlertMessage>{saveError}</AlertMessage> : null}
        <form onSubmit={confirm} noValidate aria-busy={busy}>
          <h2>Datos de contacto</h2>
          <div className={styles.fields}>
            <FormField id="external-nombre" label="Nombre completo" error={errors.nombre} required>
              <input className={styles.input} autoComplete="off" maxLength={120} value={values.nombre}
                disabled={busy || uncertain}
                onChange={e => { setValues({ ...values, nombre: e.target.value }); setErrors({ ...errors, nombre: '' }) }} />
            </FormField>
            <FormField id="external-telefono" label="Teléfono" error={errors.telefono} hint="Entre 8 y 15 dígitos. Podés pegarlo con espacios, guiones o código de país." required>
              <input className={styles.input} type="tel" inputMode="tel" autoComplete="off" maxLength={40} value={values.telefono}
                disabled={busy || uncertain}
                onChange={e => { setValues({ ...values, telefono: e.target.value }); setErrors({ ...errors, telefono: '' }) }} />
            </FormField>
          </div>
          <p className={styles.muted}>No se crea una cuenta ni se envía una solicitud al proveedor. La inmobiliaria podrá consultar este contacto.</p>
          {uncertain ? <div className={styles.confirmation}><AlertMessage tone="info">No pudimos confirmar si se guardó. Reintentá con los mismos datos o consultá el estado; no crearemos otro registro.</AlertMessage></div> : null}
          <div className={styles.actions}>
            <Link className={styles.back} to={back}>Cancelar</Link>
            {uncertain ? <Button variant="secondary" disabled={busy} onClick={() => setRevision(v => v + 1)}>Consultar estado</Button> : null}
            <Button type="submit" disabled={busy}>{busy ? 'Guardando…' : uncertain ? 'Reintentar confirmación' : 'Confirmar datos del proveedor'}</Button>
          </div>
        </form>
      </section> : data && !error ? <AlertMessage tone="info">{data.motivo_bloqueo}</AlertMessage> : null}
    </> : null}
  </div></PageContainer>
}
