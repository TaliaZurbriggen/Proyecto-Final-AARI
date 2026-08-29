import { useState } from 'react'
import { Building2, LogIn } from 'lucide-react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import AlertMessage from '../../../components/ui/AlertMessage.jsx'
import Button from '../../../components/ui/Button.jsx'
import FormField from '../../../components/ui/FormField.jsx'
import TextInput from '../../../components/ui/TextInput.jsx'
import { useAuth } from '../authContext.js'
import styles from './LoginPage.module.css'

function LoginPage() {
  const { isLoading, login, user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (!isLoading && user?.rol === 'administrador') {
    return <Navigate replace to="/propietarios" />
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setIsSubmitting(true)
    try {
      await login({ email, password })
      const destination = location.state?.from?.pathname ?? '/propietarios'
      navigate(destination, { replace: true })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="login-title">
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">
            <Building2 />
          </span>
          <div>
            <strong>AARI</strong>
            <span>Gestión inmobiliaria</span>
          </div>
        </div>

        <div className={styles.heading}>
          <p className={styles.eyebrow}>Acceso al sistema</p>
          <h1 id="login-title">Iniciá sesión</h1>
          <p>Ingresá con las credenciales proporcionadas por la inmobiliaria.</p>
        </div>

        {error ? <AlertMessage>{error}</AlertMessage> : null}

        <form className={styles.form} onSubmit={handleSubmit}>
          <FormField id="login-email" label="Email" required>
            <TextInput
              autoComplete="username"
              disabled={isSubmitting}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="nombre@inmobiliaria.com"
              type="email"
              value={email}
            />
          </FormField>
          <FormField id="login-password" label="Contraseña" required>
            <TextInput
              autoComplete="current-password"
              disabled={isSubmitting}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </FormField>
          <Button
            disabled={isSubmitting || !email.trim() || !password}
            leadingIcon={<LogIn />}
            size="lg"
            type="submit"
          >
            {isSubmitting ? 'Ingresando…' : 'Ingresar'}
          </Button>
        </form>
      </section>
    </main>
  )
}

export default LoginPage
