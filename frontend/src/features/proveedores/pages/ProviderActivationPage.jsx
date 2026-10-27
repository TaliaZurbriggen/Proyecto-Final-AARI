import { useEffect, useState } from 'react'
import { Building2, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router'
import { AlertMessage, Button, FormField, TextInput } from '../../../components/ui/index.js'
import { useAuth } from '../../auth/authContext.js'
import { activateProvider } from '../api/providerAccessApi.js'
import styles from '../../auth/pages/LoginPage.module.css'

function ProviderActivationPage() {
  const { user, logout, isLoading } = useAuth()
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (window.location.hash) window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
  }, [])

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (password.length < 8 || !/\d/.test(password) || new TextEncoder().encode(password).length > 72) {
      setError('Elegí una contraseña de al menos 8 caracteres, con un número y hasta 72 bytes.')
      return
    }
    if (password !== confirmation) { setError('La confirmación no coincide con la contraseña.'); return }
    setBusy(true)
    try {
      await activateProvider({ token, password_nueva: password, confirmacion_password: confirmation })
      setDone(true)
      setPassword('')
      setConfirmation('')
    } catch (requestError) { setError(requestError.message) }
    finally { setBusy(false) }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="activation-title">
        <div className={styles.brand}><span className={styles.brandMark} aria-hidden="true"><Building2 /></span><div><strong>AARI</strong><span>Tu espacio de trabajo</span></div></div>
        <div className={styles.heading}><p className={styles.eyebrow}>Acceso de proveedores</p><h1 id="activation-title">{done ? 'Tu cuenta está activa' : 'Activá tu cuenta'}</h1><p>{done ? 'Ya podés ingresar con tu correo y la contraseña que elegiste.' : 'Elegí tu contraseña para consultar tus solicitudes dentro de AARI.'}</p></div>
        {error ? <AlertMessage>{error}</AlertMessage> : null}
        {isLoading ? <p>Comprobando tu sesión…</p> : user ? <div className={styles.form}><AlertMessage tone="info">Tenés una sesión abierta. Cerrala antes de activar otro acceso.</AlertMessage><Button onClick={logout} variant="secondary">Cerrar sesión actual</Button></div> : done ? <Link to="/login">Ir a iniciar sesión</Link> : !/^[A-Za-z0-9_-]{43,128}$/.test(token) ? <><AlertMessage>El enlace está incompleto o no es válido. Solicitá una nueva invitación a la inmobiliaria.</AlertMessage><Link to="/login">Volver al inicio de sesión</Link></> : <form className={styles.form} noValidate onSubmit={submit}>
          <FormField id="provider-new-password" label="Nueva contraseña" hint="Al menos 8 caracteres y un número." required><TextInput autoComplete="new-password" disabled={busy} maxLength={72} onChange={(event) => setPassword(event.target.value)} type="password" value={password} /></FormField>
          <FormField id="provider-confirm-password" label="Confirmá tu contraseña" required><TextInput autoComplete="new-password" disabled={busy} maxLength={72} onChange={(event) => setConfirmation(event.target.value)} type="password" value={confirmation} /></FormField>
          <Button disabled={busy || !password || !confirmation} leadingIcon={<ShieldCheck />} type="submit">{busy ? 'Activando…' : 'Activar mi cuenta'}</Button>
        </form>}
      </section>
    </main>
  )
}

export default ProviderActivationPage
