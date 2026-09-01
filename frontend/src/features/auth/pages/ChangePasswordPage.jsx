import { useState } from 'react'
import { Building2, KeyRound, LogOut } from 'lucide-react'
import { Navigate, useNavigate } from 'react-router'
import AlertMessage from '../../../components/ui/AlertMessage.jsx'
import Button from '../../../components/ui/Button.jsx'
import FormField from '../../../components/ui/FormField.jsx'
import TextInput from '../../../components/ui/TextInput.jsx'
import { ApiError } from '../../../services/apiClient.js'
import { useAuth } from '../authContext.js'
import { homePathForRole } from '../routing.js'
import styles from './LoginPage.module.css'

const emptyValues = {
  password_actual: '',
  password_nueva: '',
  confirmacion_password: '',
}

const roleLabels = {
  administrador: 'Administración',
  inquilino: 'Inquilino',
  operador: 'Operación',
  propietario: 'Propietario',
}

function validate(values) {
  const errors = {}
  if (!values.password_actual) {
    errors.password_actual = 'Ingresá la contraseña temporal.'
  }
  if (values.password_nueva.length < 8) {
    errors.password_nueva = 'Usá al menos 8 caracteres.'
  } else if (!/\d/.test(values.password_nueva)) {
    errors.password_nueva = 'Incluí al menos un número.'
  }
  if (values.confirmacion_password !== values.password_nueva) {
    errors.confirmacion_password = 'Las contraseñas no coinciden.'
  }
  return errors
}

function ChangePasswordPage() {
  const { changePassword, logout, user } = useAuth()
  const navigate = useNavigate()
  const [values, setValues] = useState(emptyValues)
  const [errors, setErrors] = useState({})
  const [submitError, setSubmitError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  if (user && !user.primer_ingreso) {
    return <Navigate replace to={homePathForRole(user.rol)} />
  }

  const handleChange = (event) => {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    if (errors[name]) {
      setErrors((current) => ({ ...current, [name]: undefined }))
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationErrors = validate(values)
    setErrors(validationErrors)
    setSubmitError('')
    if (Object.keys(validationErrors).length) {
      event.currentTarget.elements.namedItem(Object.keys(validationErrors)[0])?.focus()
      return
    }

    setIsSubmitting(true)
    try {
      const updatedUser = await changePassword(values)
      navigate(homePathForRole(updatedUser.rol), {
        replace: true,
        state: { notice: 'Tu contraseña se actualizó correctamente.' },
      })
    } catch (error) {
      if (error instanceof ApiError) {
        const field = error.body?.detail?.field
        if (field) {
          setErrors((current) => ({ ...current, [field]: error.message }))
        } else {
          setSubmitError(error.message)
        }
      } else {
        setSubmitError('No pudimos actualizar la contraseña. Intentá nuevamente.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleLogout = async () => {
    setIsLoggingOut(true)
    try {
      await logout()
      navigate('/login', { replace: true })
    } finally {
      setIsLoggingOut(false)
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="password-title">
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
          <p className={styles.eyebrow}>Primer ingreso</p>
          <h1 id="password-title">Creá tu contraseña</h1>
          <p>
            Reemplazá la clave temporal por una contraseña de al menos 8
            caracteres y un número.
          </p>
        </div>

        <div className={styles.session} aria-label="Cuenta activa">
          <span>Estás ingresando como</span>
          <strong>{user?.email}</strong>
          <span>{roleLabels[user?.rol] ?? 'Usuario AARI'}</span>
        </div>

        {submitError ? <AlertMessage>{submitError}</AlertMessage> : null}

        <form className={styles.form} noValidate onSubmit={handleSubmit}>
          <FormField
            error={errors.password_actual}
            id="password_actual"
            label="Contraseña temporal"
            required
          >
            <TextInput
              autoComplete="current-password"
              disabled={isSubmitting}
              name="password_actual"
              onChange={handleChange}
              type="password"
              value={values.password_actual}
            />
          </FormField>
          <FormField
            error={errors.password_nueva}
            hint="Mínimo 8 caracteres y al menos un número."
            id="password_nueva"
            label="Contraseña nueva"
            required
          >
            <TextInput
              autoComplete="new-password"
              disabled={isSubmitting}
              name="password_nueva"
              onChange={handleChange}
              type="password"
              value={values.password_nueva}
            />
          </FormField>
          <FormField
            error={errors.confirmacion_password}
            id="confirmacion_password"
            label="Confirmar contraseña"
            required
          >
            <TextInput
              autoComplete="new-password"
              disabled={isSubmitting}
              name="confirmacion_password"
              onChange={handleChange}
              type="password"
              value={values.confirmacion_password}
            />
          </FormField>
          <Button
            disabled={isSubmitting || isLoggingOut}
            leadingIcon={<KeyRound />}
            size="lg"
            type="submit"
          >
            {isSubmitting ? 'Actualizando…' : 'Guardar y continuar'}
          </Button>
          <Button
            disabled={isSubmitting || isLoggingOut}
            leadingIcon={<LogOut />}
            onClick={handleLogout}
            size="lg"
            type="button"
            variant="secondary"
          >
            {isLoggingOut ? 'Cerrando sesión…' : 'No soy yo: cerrar sesión'}
          </Button>
        </form>
      </section>
    </main>
  )
}

export default ChangePasswordPage
