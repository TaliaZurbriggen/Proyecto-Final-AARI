import { useEffect, useState } from 'react'
import { ArrowLeft, Building2, Save } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  EmptyState,
  FormField,
  LoadingState,
  SelectInput,
  TextInput,
} from '../../../components/ui/index.js'
import { ApiError } from '../../../services/apiClient.js'
import { listAllPropiedades } from '../../propiedades/api/propiedadesApi.js'
import {
  createInquilino,
  getInquilino,
  updateInquilino,
} from '../api/inquilinosApi.js'
import { normalizeInquilino, validateInquilino } from '../validation.js'
import styles from './Inquilinos.module.css'

const emptyValues = {
  nombre_completo: '',
  dni: '',
  email: '',
  telefono: '',
  propiedad_id: '',
}

function propertyLabel(property) {
  const unit = property.tipo === 'departamento'
    ? [
        property.piso === 0 ? 'PB' : property.piso != null ? `Piso ${property.piso}` : null,
        property.numero ? `Unidad ${property.numero}` : null,
      ].filter(Boolean).join(' · ')
    : ''
  return `${property.direccion}${unit ? ` · ${unit}` : ''} — ${property.localidad}`
}

function InquilinoFormPage() {
  const { inquilinoId } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const isEditing = Boolean(inquilinoId)
  const requestedPropertyId = searchParams.get('propiedad_id') ?? ''
  const [values, setValues] = useState(emptyValues)
  const [properties, setProperties] = useState([])
  const [errors, setErrors] = useState({})
  const [loadError, setLoadError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let isActive = true
    const propertiesRequest = listAllPropiedades({ signal: controller.signal })
    const tenantRequest = isEditing
      ? getInquilino(inquilinoId, { signal: controller.signal })
      : Promise.resolve(null)

    Promise.all([propertiesRequest, tenantRequest])
      .then(([allProperties, tenant]) => {
        if (!isActive) return
        const currentPropertyId = tenant?.propiedad?.id
        const availableProperties = allProperties.filter(
          (property) => !property.tiene_inquilino_activo || property.id === currentPropertyId,
        )
        setProperties(availableProperties)
        if (tenant) {
          setValues({
            nombre_completo: tenant.nombre_completo,
            dni: tenant.dni,
            email: tenant.email,
            telefono: tenant.telefono,
            propiedad_id: currentPropertyId ?? '',
          })
        } else if (
          requestedPropertyId
          && availableProperties.some((property) => property.id === requestedPropertyId)
        ) {
          setValues((current) => ({ ...current, propiedad_id: requestedPropertyId }))
        }
      })
      .catch((error) => {
        if (isActive && error.name !== 'AbortError') setLoadError(error.message)
      })
      .finally(() => {
        if (isActive) setIsLoading(false)
      })

    return () => {
      isActive = false
      controller.abort()
    }
  }, [inquilinoId, isEditing, requestedPropertyId])

  const handleChange = (event) => {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    if (errors[name]) {
      setErrors((current) => ({ ...current, [name]: undefined }))
    }
  }

  const handleBlur = (event) => {
    const field = event.target.name
    const validationErrors = validateInquilino(values, {
      propertyRequired: !isEditing,
    })
    setErrors((current) => ({ ...current, [field]: validationErrors[field] }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationErrors = validateInquilino(values, {
      propertyRequired: !isEditing,
    })
    setErrors(validationErrors)
    setSubmitError('')
    if (Object.keys(validationErrors).length) {
      const [firstInvalidField] = Object.keys(validationErrors)
      event.currentTarget.elements.namedItem(firstInvalidField)?.focus()
      return
    }

    setIsSubmitting(true)
    try {
      const payload = normalizeInquilino(values)
      const tenant = isEditing
        ? await updateInquilino(inquilinoId, payload)
        : await createInquilino(payload)
      navigate(`/inquilinos/${tenant.id}`, {
        replace: true,
        state: {
          notice: isEditing
            ? 'Los datos del inquilino se actualizaron correctamente.'
            : 'El inquilino se registró y quedó asociado a la propiedad.',
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
        setSubmitError('No pudimos guardar el inquilino. Intentá nuevamente.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <PageContainer className={styles.formPage}>
        <LoadingState label="Cargando datos del inquilino" lines={6} />
      </PageContainer>
    )
  }

  const canCreate = isEditing || properties.length > 0

  return (
    <PageContainer className={styles.formPage}>
      <Link
        className={styles.backLink}
        to={isEditing ? `/inquilinos/${inquilinoId}` : '/inquilinos'}
      >
        <ArrowLeft aria-hidden="true" />
        Volver
      </Link>
      <PageHeading
        description={
          isEditing
            ? 'Actualizá sus datos o cambiá la propiedad asociada.'
            : 'Completá los datos y elegí una propiedad que todavía no tenga inquilino.'
        }
        eyebrow="Administración"
        title={isEditing ? 'Editar inquilino' : 'Registrar inquilino'}
      />

      {loadError ? <AlertMessage>{loadError}</AlertMessage> : null}

      {!loadError && !canCreate ? (
        <EmptyState
          action={
            <Link className={styles.primaryLink} to="/propiedades/nueva">
              <Building2 aria-hidden="true" />
              Registrar propiedad
            </Link>
          }
          description="Para registrar un inquilino necesitás al menos una propiedad sin inquilino activo."
          icon={Building2}
          title="No hay propiedades disponibles"
        />
      ) : null}

      {!loadError && canCreate ? (
        <form className={styles.formPanel} noValidate onSubmit={handleSubmit}>
          <div className={styles.formIntro}>
            <div>
              <h2>Información personal y asociación</h2>
              <p>Los campos marcados con asterisco son obligatorios.</p>
            </div>
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
                placeholder="Ej. Lucía Pérez"
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

            <FormField
              error={errors.propiedad_id}
              hint={
                isEditing
                  ? 'Podés dejarlo sin propiedad y asociarlo más adelante.'
                  : 'Solo se muestran propiedades sin un inquilino activo.'
              }
              id="propiedad_id"
              label="Propiedad"
              required={!isEditing}
            >
              <SelectInput
                name="propiedad_id"
                onBlur={handleBlur}
                onChange={handleChange}
                value={values.propiedad_id}
              >
                <option value="">
                  {isEditing ? 'Sin propiedad asignada' : 'Seleccionar propiedad'}
                </option>
                {properties.map((property) => (
                  <option key={property.id} value={property.id}>
                    {propertyLabel(property)}
                  </option>
                ))}
              </SelectInput>
            </FormField>
          </div>

          <div className={styles.formActions}>
            <Link
              className={styles.secondaryLink}
              to={isEditing ? `/inquilinos/${inquilinoId}` : '/inquilinos'}
            >
              Cancelar
            </Link>
            <Button disabled={isSubmitting} leadingIcon={<Save />} type="submit">
              {isSubmitting ? 'Guardando…' : 'Guardar inquilino'}
            </Button>
          </div>
        </form>
      ) : null}
    </PageContainer>
  )
}

export default InquilinoFormPage
