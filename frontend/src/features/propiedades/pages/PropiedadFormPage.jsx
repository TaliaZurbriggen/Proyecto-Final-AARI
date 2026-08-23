import { useEffect, useState } from 'react'
import { ArrowLeft, Save, UserPlus } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router'
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
import { listPropietarios } from '../../propietarios/api/propietariosApi.js'
import { ApiError } from '../../../services/apiClient.js'
import {
  createPropiedad,
  getPropiedad,
  updatePropiedad,
} from '../api/propiedadesApi.js'
import { PROVINCIAS_ARGENTINAS } from '../provincias.js'
import { normalizePropiedad, validatePropiedad } from '../validation.js'
import styles from './Propiedades.module.css'

const emptyValues = {
  direccion: '',
  provincia: '',
  localidad: '',
  barrio: '',
  tipo: '',
  piso: '',
  numero: '',
  propietario_id: '',
}

function PropiedadFormPage() {
  const { propiedadId } = useParams()
  const navigate = useNavigate()
  const isEditing = Boolean(propiedadId)
  const [values, setValues] = useState(emptyValues)
  const [owners, setOwners] = useState([])
  const [errors, setErrors] = useState({})
  const [loadError, setLoadError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let isActive = true
    const ownerRequest = listPropietarios({
      pageSize: 100,
      signal: controller.signal,
    })
    const propertyRequest = isEditing
      ? getPropiedad(propiedadId, { signal: controller.signal })
      : Promise.resolve(null)

    Promise.all([ownerRequest, propertyRequest])
      .then(([ownerPage, property]) => {
        if (!isActive) return
        const availableOwners = [...ownerPage.items]
        if (
          property &&
          !availableOwners.some((owner) => owner.id === property.propietario.id)
        ) {
          availableOwners.push(property.propietario)
        }
        setOwners(availableOwners)
        if (property) {
          setValues({
            direccion: property.direccion,
            provincia: property.provincia,
            localidad: property.localidad,
            barrio: property.barrio ?? '',
            tipo: property.tipo,
            piso: property.piso == null ? '' : String(property.piso),
            numero: property.numero ?? '',
            propietario_id: property.propietario.id,
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
  }, [isEditing, propiedadId])

  const handleChange = (event) => {
    const { name, value } = event.target
    setValues((current) => ({
      ...current,
      [name]: value,
      ...(name === 'tipo' && value !== 'departamento'
        ? { piso: '', numero: '' }
        : {}),
    }))
    if (errors[name]) {
      setErrors((current) => ({ ...current, [name]: undefined }))
    }
  }

  const handleBlur = (event) => {
    const field = event.target.name
    const validationErrors = validatePropiedad(values)
    setErrors((current) => ({
      ...current,
      [field]: validationErrors[field],
    }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationErrors = validatePropiedad(values)
    setErrors(validationErrors)
    setSubmitError('')
    if (Object.keys(validationErrors).length) {
      const [firstInvalidField] = Object.keys(validationErrors)
      event.currentTarget.elements.namedItem(firstInvalidField)?.focus()
      return
    }

    setIsSubmitting(true)
    try {
      const payload = normalizePropiedad(values)
      const property = isEditing
        ? await updatePropiedad(propiedadId, payload)
        : await createPropiedad(payload)
      navigate(`/propiedades/${property.id}`, {
        replace: true,
        state: {
          notice: isEditing
            ? 'Los datos de la propiedad se actualizaron correctamente.'
            : 'La propiedad se registró correctamente.',
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
        setSubmitError('No pudimos guardar la propiedad. Intentá nuevamente.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <PageContainer className={styles.formPage}>
        <LoadingState label="Cargando datos de la propiedad" lines={6} />
      </PageContainer>
    )
  }

  return (
    <PageContainer className={styles.formPage}>
      <Link
        className={styles.backLink}
        to={isEditing ? `/propiedades/${propiedadId}` : '/propiedades'}
      >
        <ArrowLeft aria-hidden="true" />
        Volver
      </Link>
      <PageHeading
        description={
          isEditing
            ? 'Actualizá la ubicación, el tipo o el propietario asociado.'
            : 'Completá la información necesaria para incorporar el inmueble.'
        }
        eyebrow="Administración"
        title={isEditing ? 'Editar propiedad' : 'Registrar propiedad'}
      />

      {loadError ? <AlertMessage>{loadError}</AlertMessage> : null}

      {!loadError && owners.length === 0 ? (
        <EmptyState
          action={
            <Link className={styles.primaryLink} to="/propietarios/nuevo">
              <UserPlus aria-hidden="true" />
              Registrar propietario
            </Link>
          }
          description="Toda propiedad debe tener un propietario asociado. Registrá uno para continuar."
          icon={UserPlus}
          title="Primero necesitás un propietario"
        />
      ) : null}

      {!loadError && owners.length > 0 ? (
        <form className={styles.formPanel} noValidate onSubmit={handleSubmit}>
          <div className={styles.formIntro}>
            <div>
              <h2>Información del inmueble</h2>
              <p>Los campos marcados con asterisco son obligatorios.</p>
            </div>
          </div>

          {submitError ? <AlertMessage>{submitError}</AlertMessage> : null}

          <div className={styles.formGrid}>
            <FormField
              error={errors.direccion}
              id="direccion"
              label="Dirección"
              required
            >
              <TextInput
                autoComplete="street-address"
                maxLength={200}
                name="direccion"
                onBlur={handleBlur}
                onChange={handleChange}
                placeholder="Ej. Av. San Martín 120"
                value={values.direccion}
              />
            </FormField>

            <FormField
              error={errors.provincia}
              id="provincia"
              label="Provincia"
              required
            >
              <SelectInput
                autoComplete="address-level1"
                name="provincia"
                onBlur={handleBlur}
                onChange={handleChange}
                value={values.provincia}
              >
                <option value="">Seleccionar provincia</option>
                {PROVINCIAS_ARGENTINAS.map((province) => (
                  <option key={province} value={province}>
                    {province}
                  </option>
                ))}
              </SelectInput>
            </FormField>

            <FormField
              error={errors.localidad}
              id="localidad"
              label="Localidad"
              required
            >
              <TextInput
                autoComplete="address-level2"
                maxLength={100}
                name="localidad"
                onBlur={handleBlur}
                onChange={handleChange}
                placeholder="Ej. San Francisco"
                value={values.localidad}
              />
            </FormField>

            <FormField
              error={errors.barrio}
              hint="Opcional. Dejalo vacío si no corresponde o no lo conocés."
              id="barrio"
              label="Barrio"
            >
              <TextInput
                autoComplete="address-level3"
                maxLength={100}
                name="barrio"
                onBlur={handleBlur}
                onChange={handleChange}
                placeholder="Ej. Centro"
                value={values.barrio}
              />
            </FormField>

            <FormField error={errors.tipo} id="tipo" label="Tipo" required>
              <SelectInput
                name="tipo"
                onBlur={handleBlur}
                onChange={handleChange}
                value={values.tipo}
              >
                <option value="">Seleccionar tipo</option>
                <option value="departamento">Departamento</option>
                <option value="casa">Casa</option>
                <option value="local">Local</option>
                <option value="otro">Otro</option>
              </SelectInput>
            </FormField>

            <FormField
              error={errors.propietario_id}
              hint="Podés cambiar la asociación mientras la propiedad no tenga restricciones."
              id="propietario_id"
              label="Propietario"
              required
            >
              <SelectInput
                name="propietario_id"
                onBlur={handleBlur}
                onChange={handleChange}
                value={values.propietario_id}
              >
                <option value="">Seleccionar propietario</option>
                {owners.map((owner) => (
                  <option key={owner.id} value={owner.id}>
                    {owner.nombre_completo} · DNI {owner.dni ?? 'sin informar'}
                  </option>
                ))}
              </SelectInput>
            </FormField>

            {values.tipo === 'departamento' ? (
              <>
                <FormField
                  error={errors.piso}
                  hint="Opcional. Ingresá 0 para planta baja."
                  id="piso"
                  label="Piso"
                >
                  <TextInput
                    inputMode="numeric"
                    name="piso"
                    onBlur={handleBlur}
                    onChange={handleChange}
                    placeholder="Ej. 2"
                    step="1"
                    type="number"
                    value={values.piso}
                  />
                </FormField>

                <FormField
                  error={errors.numero}
                  hint="Opcional. Puede ser un número o una letra."
                  id="numero"
                  label="Unidad / departamento"
                >
                  <TextInput
                    maxLength={30}
                    name="numero"
                    onBlur={handleBlur}
                    onChange={handleChange}
                    placeholder="Ej. B"
                    value={values.numero}
                  />
                </FormField>
              </>
            ) : null}
          </div>

          <div className={styles.formActions}>
            <Link
              className={styles.secondaryLink}
              to={isEditing ? `/propiedades/${propiedadId}` : '/propiedades'}
            >
              Cancelar
            </Link>
            <Button
              disabled={isSubmitting}
              leadingIcon={<Save />}
              type="submit"
            >
              {isSubmitting ? 'Guardando…' : 'Guardar propiedad'}
            </Button>
          </div>
        </form>
      ) : null}
    </PageContainer>
  )
}

export default PropiedadFormPage
