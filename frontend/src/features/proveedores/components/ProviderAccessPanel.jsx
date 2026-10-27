import { useEffect, useRef, useState } from 'react'
import { Mail, RefreshCw, ShieldCheck } from 'lucide-react'
import { AlertMessage, Button, ConfirmDialog, FormField, LoadingState, StatusBadge, TextInput } from '../../../components/ui/index.js'
import { getProviderAccess, inviteProvider } from '../api/providerAccessApi.js'
import styles from '../pages/ProviderPortal.module.css'

const states = {
  sin_acceso: 'Acceso no habilitado', pendiente: 'Pendiente de activación',
  vencido: 'Invitación vencida', activo: 'Cuenta activa', desactivado: 'Acceso desactivado',
}

function ProviderAccessPanel({ providerId, active }) {
  const [access, setAccess] = useState(null)
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [emailError, setEmailError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [confirm, setConfirm] = useState(false)
  const requestId = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    let mounted = true
    getProviderAccess(providerId, { signal: controller.signal })
      .then((result) => {
        if (!mounted) return
        setAccess(result)
        setEmail(result.email ?? '')
        setError('')
      })
      .catch((requestError) => {
        if (mounted && requestError.name !== 'AbortError') {
          setAccess(null)
          setError(requestError.message)
        }
      })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false; controller.abort() }
  }, [providerId, active, refresh])

  const deliver = async () => {
    setConfirm(false)
    setBusy(true)
    setError('')
    requestId.current ??= crypto.randomUUID()
    try {
      const result = await inviteProvider(providerId, {
        email: email.trim().toLowerCase(), request_id: requestId.current,
      })
      setAccess(result)
      setEmail(result.email ?? '')
      requestId.current = null
    } catch (requestError) {
      if (requestError.body?.detail?.field === 'email') setEmailError(requestError.message)
      else setError(requestError.message)
    } finally { setBusy(false) }
  }

  const submit = (event) => {
    event.preventDefault()
    const normalized = email.trim()
    if (normalized.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
      setEmailError('Ingresá un correo válido para enviar la invitación.')
      return
    }
    setEmailError('')
    if (access?.estado !== 'sin_acceso') setConfirm(true)
    else deliver()
  }

  return (
    <section className={styles.panel} aria-labelledby="provider-access-title">
      <div className={styles.panelHeading}>
        <div><p className={styles.eyebrow}>Cuenta del prestador</p><h2 id="provider-access-title">Acceso a AARI</h2></div>
        {access ? <StatusBadge tone={access.estado === 'activo' ? 'success' : 'neutral'}>{states[access.estado] ?? 'Estado no disponible'}</StatusBadge> : <ShieldCheck aria-hidden="true" />}
      </div>
      <div className={styles.panelBody}>
        {loading ? <LoadingState label="Consultando acceso del proveedor" /> : <>
          <p className={styles.muted}>El proveedor podrá ingresar con su propia cuenta. La invitación le permite elegir su contraseña; no enviamos contraseñas por correo.</p>
          {error ? <AlertMessage>{error}</AlertMessage> : null}
          {access?.envio_estado === 'fallido' ? <AlertMessage>{access.ultimo_error || 'No se pudo enviar la invitación. Generá una nueva para reintentar.'}</AlertMessage> : null}
          {access?.envio_estado === 'enviado' && access.estado !== 'activo' ? <p className={styles.deliveryNotice} role="status">El servicio de correo aceptó la invitación. Esto no confirma su entrega ni su lectura.</p> : null}
          {access?.envio_estado === 'pendiente' ? <p className={styles.muted}>El envío aún no tiene resultado confirmado. Actualizá el estado o generá otra invitación.</p> : null}
          {access?.vence_en ? <p className={styles.muted}>Vence: {new Date(access.vence_en).toLocaleString('es-AR', { timeZone: 'America/Argentina/Buenos_Aires' })} (Argentina).</p> : null}
          {access ? <form className={styles.accessForm} noValidate onSubmit={submit}>
            <FormField error={emailError} hint={access.estado === 'activo' ? 'El correo de una cuenta activa no se cambia desde esta sección.' : 'Debe ser propio del proveedor y no estar usado por otra cuenta de AARI.'} id="provider-access-email" label="Correo de acceso" required>
              <TextInput autoComplete="email" disabled={busy || !access.puede_invitar || !active} maxLength={254} onChange={(event) => { setEmail(event.target.value); setEmailError(''); requestId.current = null }} type="email" value={email} />
            </FormField>
            <div className={styles.actions}>
              <Button disabled={busy} leadingIcon={<RefreshCw />} onClick={() => setRefresh((value) => value + 1)} type="button" variant="secondary">Actualizar estado</Button>
              {access.puede_invitar && active ? <Button disabled={busy} leadingIcon={<Mail />} type="submit">{busy ? 'Enviando…' : access.estado === 'sin_acceso' ? 'Habilitar y enviar invitación' : 'Generar nueva invitación'}</Button> : null}
            </div>
          </form> : <Button onClick={() => setRefresh((value) => value + 1)} variant="secondary">Reintentar consulta de acceso</Button>}
          {!active ? <p className={styles.muted}>El proveedor está inactivo: no puede ingresar ni recibir nuevas invitaciones.</p> : null}
        </>}
      </div>
      <ConfirmDialog open={confirm} title="¿Generar una nueva invitación?" description="El enlace anterior dejará de funcionar. Enviaremos uno nuevo al correo indicado, sin crear otra cuenta." confirmLabel="Generar y enviar" isBusy={busy} onCancel={() => setConfirm(false)} onConfirm={deliver} />
    </section>
  )
}

export default ProviderAccessPanel
