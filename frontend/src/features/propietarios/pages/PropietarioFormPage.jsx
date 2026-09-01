import { useEffect, useState } from 'react'
import { ArrowLeft, Save } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  FormField,
  LoadingState,
  TextInput,
} from '../../../components/ui/index.js'
import { ApiError } from '../../../services/apiClient.js'
import { accessNotice } from '../../access/accessNotice.js'
import {
  createPropietario,
  getPropietario,
  updatePropietario,
} from '../api/propietariosApi.js'
import { normalizePropietario, validatePropietario } from '../validation.js'
import styles from './Propietarios.module.css'

const emptyValues = {
  nombre_completo: '',
  dni: '',
  email: '',
  telefono: '',
}

function PropietarioFormPage() {
  const { propietarioId } = useParams()
  const navigate = useNavigate()
  const isEditing = Boolean(propietarioId)
  const [values, setValues] = useState(emptyValues)
  const [errors, setErrors] = useState({})
  const [loadError, setLoadError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [isLoading, setIsLoading] = useState(isEditing)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (!isEditing) return undefined
    const controller = new AbortController()
    let isActive = true
    getPropietario(propietarioId, { signal: controller.signal })
      .then((owner) => {
        if (isActive) {
          setValues({
            nombre_completo: owner.nombre_completo,
            dni: owner.dni,
            email: owner.email,
            telefono: owner.telefono,
          })
        }
      })
      .catch((error) => {
        if (isActive && error.name !== 'AbortError') {
          setLoadError(error.message)
        }
      })
      .finally(() => {
        if (isActive) setIsLoading(false)
      })
    return () => {
      isActive = false
      controller.abort()
    }
  }, [isEditing, propietarioId])

  const handleChange = (event) => {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    if (errors[name]) {
      setErrors((current) => ({ ...current, [name]: undefined }))
    }
  }

  const handleBlur = (event) => {
    const field = event.target.name
    const validationErrors = validatePropietario(values)
    setErrors((current) => ({
      ...current,
      [field]: validationErrors[field],
    }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationErrors = validatePropietario(values)
    setErrors(validationErrors)
    setSubmitError('')
    if (Object.keys(validationErrors).length) {
      const [firstInvalidField] = Object.keys(validationErrors)
      event.currentTarget.elements.namedItem(firstInvalidField)?.focus()
      return
    }

    setIsSubmitting(true)
    try {
      const payload = normalizePropietario(values)
      const owner = isEditing
        ? await updatePropietario(propietarioId, payload)
        : await createPropietario(payload)
      navigate(`/propietarios/${owner.id}`, {
        replace: true,
        state: {
          notice: accessNotice(owner.acceso, {
            entityLabel: 'propietario',
            isEditing,
          }),
        },
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
        setSubmitError('No pudimos guardar los datos. Intentá nuevamente.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <PageContainer className={styles.formPage}>
        <LoadingState label="Cargando datos del propietario" lines={5} />
      </PageContainer>
    )
  }

  return (
    <PageContainer className={styles.formPage}>
      <Link className={styles.backLink} to={isEditing ? `/propietarios/${propietarioId}` : '/propietarios'}>
        <ArrowLeft aria-hidden="true" />
        Volver
      </Link>
      <PageHeading
        description={
          isEditing
            ? 'Modificá la información de contacto y guardá los cambios.'
            : 'Completá los datos para poder asociar inmuebles a esta persona.'
        }
        eyebrow="Administración"
        title={isEditing ? 'Editar propietario' : 'Registrar propietario'}
      />

      {loadError ? <AlertMessage>{loadError}</AlertMessage> : null}

      {!loadError ? (
        <form className={styles.formPanel} noValidate onSubmit={handleSubmit}>
          <div className={styles.formIntro}>
            <h2>Información de contacto</h2>
            <p>Los campos marcados con asterisco son obligatorios.</p>
          </div>

          {submitError ? <AlertMessage>{submitError}</AlertMessage> : null}

          <div className={styles.formGrid}>
            <FormField
              error={errors.nombre_completo}
              id="nombre_completo"
              label="Nombre completo"
              required
            >
              <TextInput
                autoComplete="name"
                maxLength={120}
                name="nombre_completo"
                onBlur={handleBlur}
                onChange={handleChange}
                placeholder="Ej. Ana Martínez"
                value={values.nombre_completo}
              />
            </FormField>

            <FormField
              error={errors.dni}
              hint="Ingresalo sin puntos ni espacios."
              id="dni"
              label="DNI"
              required
            >
              <TextInput
                autoComplete="off"
                inputMode="numeric"
                maxLength={8}
                name="dni"
                onBlur={handleBlur}
                onChange={handleChange}
                placeholder="Ej. 30123456"
                value={values.dni}
              />
            </FormField>

            <FormField
              error={errors.email}
              hint="Será único y se utilizará para el futuro acceso al sistema."
              id="email"
              label="Email"
              required
            >
              <TextInput
                autoComplete="email"
                maxLength={254}
                name="email"
                onBlur={handleBlur}
                onChange={handleChange}
                placeholder="nombre@dominio.com"
                type="email"
                value={values.email}
              />
            </FormField>

            <FormField
              error={errors.telefono}
              id="telefono"
              label="Teléfono"
              required
            >
              <TextInput
                autoComplete="tel"
                maxLength={30}
                name="telefono"
                onBlur={handleBlur}
                onChange={handleChange}
                placeholder="Ej. +54 9 3564 555555"
                type="tel"
                value={values.telefono}
              />
            </FormField>
          </div>

          <div className={styles.formActions}>
            <Link
              className={styles.secondaryLink}
              to={isEditing ? `/propietarios/${propietarioId}` : '/propietarios'}
            >
              Cancelar
            </Link>
            <Button
              disabled={isSubmitting}
              leadingIcon={<Save />}
              type="submit"
            >
              {isSubmitting ? 'Guardando…' : 'Guardar propietario'}
            </Button>
          </div>
        </form>
      ) : null}
    </PageContainer>
  )
}

export default PropietarioFormPage
