import { useEffect, useState } from 'react'
import { ArrowLeft, MapPinPlus, Save, Trash2 } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  FormField,
  LoadingState,
  SelectInput,
  TextInput,
} from '../../../components/ui/index.js'
import { ApiError } from '../../../services/apiClient.js'
import { PROVINCIAS_ARGENTINAS } from '../../propiedades/provincias.js'
import {
  createProveedor,
  getProveedor,
  listEspecialidades,
  updateProveedor,
} from '../api/proveedoresApi.js'
import { normalizeProveedor, validateProveedor } from '../validation.js'
import styles from './Proveedores.module.css'

const newCoverage = () => ({
  key: crypto.randomUUID(),
  provincia: '',
  localidad: '',
  cubre_toda_localidad: true,
  barrios: '',
})

const emptyValues = {
  nombre_razon_social: '',
  matricula: '',
  telefono: '',
  activo: true,
  hora_inicio: '',
  hora_fin: '',
  especialidad_ids: [],
  especialidades_personalizadas: '',
  coberturas: [newCoverage()],
}

function providerToValues(provider) {
  return {
    nombre_razon_social: provider.nombre_razon_social,
    matricula: provider.matricula ?? '',
    telefono: provider.telefono,
    activo: provider.activo,
    hora_inicio: provider.hora_inicio?.slice(0, 5) ?? '',
    hora_fin: provider.hora_fin?.slice(0, 5) ?? '',
    especialidad_ids: provider.especialidades.map((specialty) => specialty.id),
    especialidades_personalizadas: '',
    coberturas: provider.coberturas.map((coverage) => ({
      key: coverage.id,
      provincia: coverage.provincia,
      localidad: coverage.localidad,
      cubre_toda_localidad: coverage.cubre_toda_localidad,
      barrios: coverage.barrios.join(', '),
    })),
  }
}

function ProveedorFormPage() {
  const { proveedorId } = useParams()
  const navigate = useNavigate()
  const isEditing = Boolean(proveedorId)
  const [values, setValues] = useState(emptyValues)
  const [specialties, setSpecialties] = useState([])
  const [errors, setErrors] = useState({})
  const [loadError, setLoadError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let isActive = true
    Promise.all([
      listEspecialidades({ signal: controller.signal }),
      isEditing ? getProveedor(proveedorId, { signal: controller.signal }) : null,
    ])
      .then(([catalog, provider]) => {
        if (!isActive) return
        const knownIds = new Set(catalog.map((specialty) => specialty.id))
        setSpecialties(catalog)
        if (provider) {
          const formValues = providerToValues(provider)
          const customNames = provider.especialidades
            .filter((specialty) => !knownIds.has(specialty.id))
            .map((specialty) => specialty.nombre)
          formValues.especialidad_ids = formValues.especialidad_ids.filter((id) => knownIds.has(id))
          formValues.especialidades_personalizadas = customNames.join(', ')
          setValues(formValues)
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
  }, [isEditing, proveedorId])

  const handleChange = (event) => {
    const { checked, name, type, value } = event.target
    setValues((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
    setErrors((current) => ({ ...current, [name]: undefined, horario: undefined }))
  }

  const toggleSpecialty = (specialtyId) => {
    setValues((current) => ({
      ...current,
      especialidad_ids: current.especialidad_ids.includes(specialtyId)
        ? current.especialidad_ids.filter((id) => id !== specialtyId)
        : [...current.especialidad_ids, specialtyId],
    }))
    setErrors((current) => ({ ...current, especialidades: undefined }))
  }

  const updateCoverage = (index, field, value) => {
    setValues((current) => ({
      ...current,
      coberturas: current.coberturas.map((coverage, coverageIndex) =>
        coverageIndex === index
          ? {
              ...coverage,
              [field]: value,
              ...(field === 'cubre_toda_localidad' && value ? { barrios: '' } : {}),
            }
          : coverage,
      ),
    }))
    setErrors((current) => ({
      ...current,
      [`cobertura-${index}-${field}`]: undefined,
      coberturas: undefined,
    }))
  }

  const removeCoverage = (index) => {
    setValues((current) => ({
      ...current,
      coberturas: current.coberturas.filter((_, coverageIndex) => coverageIndex !== index),
    }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationErrors = validateProveedor(values)
    setErrors(validationErrors)
    setSubmitError('')
    if (Object.keys(validationErrors).length) {
      document.getElementById(Object.keys(validationErrors)[0])?.focus()
      return
    }
    setIsSubmitting(true)
    try {
      const payload = normalizeProveedor(values)
      const provider = isEditing
        ? await updateProveedor(proveedorId, payload)
        : await createProveedor(payload)
      navigate(`/proveedores/${provider.id}`, {
        replace: true,
        state: {
          notice: isEditing
            ? 'Los datos del proveedor se actualizaron correctamente.'
            : 'El proveedor se registró correctamente.',
        },
      })
    } catch (error) {
      if (error instanceof ApiError && error.body?.detail?.field) {
        setErrors((current) => ({
          ...current,
          [error.body.detail.field]: error.message,
        }))
      } else {
        setSubmitError(error.message || 'No pudimos guardar el proveedor.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) return <PageContainer className={styles.formPage}><LoadingState label="Cargando datos del proveedor" lines={8} /></PageContainer>

  return (
    <PageContainer className={styles.formPage}>
      <Link className={styles.backLink} to={isEditing ? `/proveedores/${proveedorId}` : '/proveedores'}><ArrowLeft aria-hidden="true" />Volver</Link>
      <PageHeading
        description={isEditing ? 'Actualizá los datos operativos sin perder su historial.' : 'Completá los datos necesarios para incorporar un prestador.'}
        eyebrow="Administración"
        title={isEditing ? 'Editar proveedor' : 'Registrar proveedor'}
      />
      {loadError ? <AlertMessage>{loadError}</AlertMessage> : null}

      {!loadError ? <form className={styles.formPanel} noValidate onSubmit={handleSubmit}>
        <div className={styles.formIntro}><div><h2>Información del prestador</h2><p>Los campos marcados con asterisco son obligatorios.</p></div></div>
        {submitError ? <div className={styles.formAlert}><AlertMessage>{submitError}</AlertMessage></div> : null}

        <section className={styles.formSection} aria-labelledby="provider-contact-title">
          <div className={styles.subheading}><h3 id="provider-contact-title">Contacto y disponibilidad</h3><p>El teléfono se usará para la futura coordinación por WhatsApp.</p></div>
          <div className={styles.formGrid}>
            <FormField error={errors.nombre_razon_social} id="nombre_razon_social" label="Nombre o razón social" required><TextInput maxLength={150} name="nombre_razon_social" onChange={handleChange} placeholder="Ej. Servicios del Centro" value={values.nombre_razon_social} /></FormField>
            <FormField error={errors.matricula} hint="Opcional, según la actividad." id="matricula" label="Matrícula"><TextInput maxLength={80} name="matricula" onChange={handleChange} placeholder="Ej. MP 1234" value={values.matricula} /></FormField>
            <FormField error={errors.telefono} hint="Incluí código de país y área." id="telefono" label="Teléfono de WhatsApp" required><TextInput inputMode="tel" name="telefono" onChange={handleChange} placeholder="Ej. +54 9 3564 555555" value={values.telefono} /></FormField>
            <div className={styles.scheduleField}>
              <span>Horario habitual <small>(opcional)</small></span>
              <div className={styles.timeRange}>
                <label htmlFor="hora_inicio"><span>Desde</span><TextInput id="hora_inicio" name="hora_inicio" onChange={handleChange} type="time" value={values.hora_inicio} /></label>
                <label htmlFor="hora_fin"><span>Hasta</span><TextInput id="hora_fin" name="hora_fin" onChange={handleChange} type="time" value={values.hora_fin} /></label>
              </div>
              {errors.horario ? <p className={styles.fieldError} id="horario" role="alert">{errors.horario}</p> : <p className={styles.fieldHint}>Es una referencia; no reemplaza la coordinación de una visita.</p>}
            </div>
          </div>
        </section>

        <section className={styles.formSection} aria-labelledby="specialties-title">
          <div className={styles.subheading}><h3 id="specialties-title">Especialidades</h3><p>Seleccioná todas las tareas que puede realizar.</p></div>
          <fieldset className={styles.checkboxFieldset}>
            <legend className="aari-sr-only">Especialidades disponibles</legend>
            <div className={styles.checkboxGrid}>{specialties.map((specialty) => <label key={specialty.id} className={styles.checkboxCard}><input checked={values.especialidad_ids.includes(specialty.id)} onChange={() => toggleSpecialty(specialty.id)} type="checkbox" /><span>{specialty.nombre}</span></label>)}</div>
            {errors.especialidades ? <p className={styles.fieldError} id="especialidades" role="alert">{errors.especialidades}</p> : null}
          </fieldset>
          <div className={styles.customSpecialty}><FormField error={errors.especialidades_personalizadas} hint="Opcional. Separalas con comas; quedarán disponibles para futuros proveedores." id="especialidades_personalizadas" label="Otras especialidades"><TextInput name="especialidades_personalizadas" onChange={handleChange} placeholder="Ej. domótica, reparación de bombas" value={values.especialidades_personalizadas} /></FormField></div>
        </section>

        <section className={styles.formSection} aria-labelledby="coverage-title">
          <div className={styles.coverageHeading}><div className={styles.subheading}><h3 id="coverage-title">Zonas de cobertura</h3><p>Indicá si trabaja en toda la localidad o solo en barrios concretos.</p></div><Button leadingIcon={<MapPinPlus />} onClick={() => setValues((current) => ({ ...current, coberturas: [...current.coberturas, newCoverage()] }))} size="sm" variant="secondary">Agregar zona</Button></div>
          {errors.coberturas ? <p className={styles.fieldError} id="coberturas" role="alert">{errors.coberturas}</p> : null}
          <div className={styles.coverageList}>{values.coberturas.map((coverage, index) => (
            <article className={styles.coverageCard} key={coverage.key}>
              <div className={styles.coverageCardHeading}><h4>Zona {index + 1}</h4><Button disabled={values.coberturas.length === 1} leadingIcon={<Trash2 />} onClick={() => removeCoverage(index)} size="sm" variant="secondary">Quitar</Button></div>
              <div className={styles.formGrid}>
                <FormField error={errors[`cobertura-${index}-provincia`]} id={`cobertura-${index}-provincia`} label="Provincia" required><SelectInput onChange={(event) => updateCoverage(index, 'provincia', event.target.value)} value={coverage.provincia}><option value="">Seleccionar provincia</option>{PROVINCIAS_ARGENTINAS.map((province) => <option key={province}>{province}</option>)}</SelectInput></FormField>
                <FormField error={errors[`cobertura-${index}-localidad`]} id={`cobertura-${index}-localidad`} label="Localidad" required><TextInput onChange={(event) => updateCoverage(index, 'localidad', event.target.value)} placeholder="Ej. San Francisco" value={coverage.localidad} /></FormField>
              </div>
              <label className={styles.scopeToggle}><input checked={coverage.cubre_toda_localidad} onChange={(event) => updateCoverage(index, 'cubre_toda_localidad', event.target.checked)} type="checkbox" /><span><strong>Cubre toda la localidad</strong><small>También incluye propiedades sin barrio informado.</small></span></label>
              {!coverage.cubre_toda_localidad ? <div className={styles.neighborhoodField}><FormField error={errors[`cobertura-${index}-barrios`]} hint="Separá los barrios con comas." id={`cobertura-${index}-barrios`} label="Barrios cubiertos" required><TextInput onChange={(event) => updateCoverage(index, 'barrios', event.target.value)} placeholder="Ej. Centro, La Milka" value={coverage.barrios} /></FormField></div> : null}
            </article>
          ))}</div>
        </section>

        <section className={styles.statusSection}><label className={styles.scopeToggle}><input checked={values.activo} name="activo" onChange={handleChange} type="checkbox" /><span><strong>Proveedor activo</strong><small>Solo los proveedores activos podrán considerarse para nuevas asignaciones.</small></span></label></section>

        <div className={styles.formActions}><Link className={styles.secondaryLink} to={isEditing ? `/proveedores/${proveedorId}` : '/proveedores'}>Cancelar</Link><Button disabled={isSubmitting} leadingIcon={<Save />} type="submit">{isSubmitting ? 'Guardando…' : 'Guardar proveedor'}</Button></div>
      </form> : null}
    </PageContainer>
  )
}

export default ProveedorFormPage
