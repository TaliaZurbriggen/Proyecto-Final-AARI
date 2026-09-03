import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, UserPlus } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, FormField, TextInput } from '../../../components/ui/index.js'
import { createOperador } from '../api/operadoresApi.js'
import { normalizeOperador, validateOperador } from '../validation.js'
import styles from './Operadores.module.css'

function OperadorFormPage() {
  const navigate = useNavigate()
  const [values, setValues] = useState({ nombre_completo: '', email: '' })
  const [errors, setErrors] = useState({})
  const [submitError, setSubmitError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const formRef = useRef(null)
  const focusAfterSubmit = useRef(null)
  useEffect(() => {
    if (!isSubmitting && focusAfterSubmit.current) {
      formRef.current?.elements.namedItem(focusAfterSubmit.current)?.focus()
      focusAfterSubmit.current = null
    }
  }, [isSubmitting])

  const handleChange = ({ target: { name, value } }) => {
    setValues((current) => ({ ...current, [name]: value }))
    setErrors((current) => ({ ...current, [name]: undefined }))
  }
  const handleBlur = ({ target: { name } }) => {
    setErrors((current) => ({ ...current, [name]: validateOperador(values)[name] }))
  }
  const handleSubmit = async (event) => {
    event.preventDefault()
    if (isSubmitting) return
    const form = event.currentTarget
    const validationErrors = validateOperador(values)
    setErrors(validationErrors)
    setSubmitError('')
    if (Object.keys(validationErrors).length) {
      form.elements.namedItem(Object.keys(validationErrors)[0])?.focus()
      return
    }
    setIsSubmitting(true)
    try {
      const operator = await createOperador(normalizeOperador(values))
      const sent = operator.acceso?.estado === 'enviado'
      navigate('/operadores', { replace: true, state: { notice: {
        tone: sent ? 'success' : 'warning',
        message: sent
          ? 'Operador creado. Se enviaron sus credenciales temporales por correo.'
          : 'Operador creado, pero el correo no está confirmado. Podés reintentar el envío desde el listado.',
      } } })
    } catch (error) {
      const field = error.body?.detail?.field
      if (field && Object.hasOwn(values, field)) {
        setErrors({ [field]: error.message })
        focusAfterSubmit.current = field
      } else {
        setSubmitError(error.message || 'No pudimos crear el operador. Intentá nuevamente.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <PageContainer className={styles.formPage}>
      <Link className={styles.backLink} to="/operadores"><ArrowLeft aria-hidden="true" />Volver</Link>
      <PageHeading eyebrow="Administración" title="Registrar operador"
        description="Invitá a una persona del equipo para gestionar los casos escalados." />
      <form ref={formRef} className={styles.panel} noValidate onSubmit={handleSubmit} aria-busy={isSubmitting}>
        <div className={styles.sectionHeading}>
          <h2>Datos de acceso</h2>
          <p>Todos los campos son obligatorios.</p>
        </div>
        <div className={styles.formBody}>
          {submitError ? <AlertMessage>{submitError}</AlertMessage> : null}
          <div className={styles.formGrid}>
            <FormField id="nombre_completo" label="Nombre completo" required error={errors.nombre_completo}>
              <TextInput name="nombre_completo" autoComplete="name" maxLength={120}
                disabled={isSubmitting} value={values.nombre_completo} onChange={handleChange} onBlur={handleBlur} />
            </FormField>
            <FormField id="email" label="Email" required error={errors.email}
              hint="Se usará para iniciar sesión y recibir las credenciales.">
              <TextInput name="email" type="email" autoComplete="email" maxLength={254}
                disabled={isSubmitting} value={values.email} onChange={handleChange} onBlur={handleBlur} />
            </FormField>
          </div>
          <AlertMessage tone="info">
            AARI generará una contraseña temporal aleatoria y la enviará por correo.
            El operador deberá cambiarla en su primer ingreso. No tendrá acceso a la administración de usuarios.
          </AlertMessage>
        </div>
        <div className={styles.formActions}>
          <Button variant="secondary" disabled={isSubmitting} onClick={() => navigate('/operadores')}>Cancelar</Button>
          <Button type="submit" disabled={isSubmitting} leadingIcon={<UserPlus />}>
            {isSubmitting ? 'Creando y enviando…' : 'Crear operador'}
          </Button>
        </div>
      </form>
    </PageContainer>
  )
}

export default OperadorFormPage
