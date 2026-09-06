import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, Building2, Camera, FileImage, Send, X } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  FormField,
  LoadingState,
  SelectInput,
} from '../../../components/ui/index.js'
import { ApiError } from '../../../services/apiClient.js'
import { createClaim, getClaimContext } from '../api/reclamosApi.js'
import {
  MAX_CLAIM_PHOTOS,
  claimPropertyLabel,
  normalizeClaim,
  validateClaim,
} from '../validation.js'
import styles from './Reclamos.module.css'

const emptyValues = { descripcion: '', fotos: [], urgencia: '' }

function SelectedPhoto({ index, onRemove, photo }) {
  const previewUrl = useMemo(
    () =>
      typeof URL.createObjectURL === 'function' ? URL.createObjectURL(photo) : '',
    [photo],
  )

  useEffect(() => {
    if (!previewUrl) return undefined
    return () => URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  return (
    <li>
      {previewUrl ? (
        <img alt="" className={styles.photoPreview} src={previewUrl} />
      ) : (
        <FileImage aria-hidden="true" />
      )}
      <span>
        <strong>{photo.name}</strong>
        <small>{(photo.size / 1024 / 1024).toFixed(2)} MB</small>
      </span>
      <button
        aria-label={`Quitar ${photo.name}`}
        onClick={() => onRemove(index)}
        type="button"
      >
        <X aria-hidden="true" />
      </button>
    </li>
  )
}

function ReclamoFormPage() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)
  const [context, setContext] = useState(null)
  const [values, setValues] = useState(emptyValues)
  const [errors, setErrors] = useState({})
  const [loadError, setLoadError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    getClaimContext({ signal: controller.signal })
      .then(setContext)
      .catch((error) => {
        if (error.name !== 'AbortError') setLoadError(error.message)
      })
      .finally(() => setIsLoading(false))
    return () => controller.abort()
  }, [])

  const handleChange = (event) => {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    if (errors[name]) {
      setErrors((current) => ({ ...current, [name]: undefined }))
    }
  }

  const handleBlur = (event) => {
    const field = event.target.name
    const validationErrors = validateClaim(values)
    setErrors((current) => ({ ...current, [field]: validationErrors[field] }))
  }

  const handleFiles = (event) => {
    const selected = Array.from(event.target.files ?? [])
    const nextPhotos = [...values.fotos, ...selected]
    const validationErrors = validateClaim({ ...values, fotos: nextPhotos })
    if (validationErrors.fotos) {
      setErrors((current) => ({ ...current, fotos: validationErrors.fotos }))
    } else {
      setValues((current) => ({ ...current, fotos: nextPhotos }))
      setErrors((current) => ({ ...current, fotos: undefined }))
    }
    event.target.value = ''
  }

  const removePhoto = (index) => {
    setValues((current) => ({
      ...current,
      fotos: current.fotos.filter((_, photoIndex) => photoIndex !== index),
    }))
    setErrors((current) => ({ ...current, fotos: undefined }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationErrors = validateClaim(values)
    setErrors(validationErrors)
    setSubmitError('')
    if (Object.keys(validationErrors).length) {
      const [firstInvalidField] = Object.keys(validationErrors)
      if (firstInvalidField === 'fotos') fileInputRef.current?.focus()
      else event.currentTarget.elements.namedItem(firstInvalidField)?.focus()
      return
    }

    setIsSubmitting(true)
    try {
      const normalized = normalizeClaim(values)
      const claim = await createClaim(normalized)
      navigate('/inquilino/reclamos/confirmacion', {
        replace: true,
        state: { claim, context, descripcion: normalized.descripcion },
      })
    } catch (error) {
      if (error instanceof ApiError) {
        const field = error.body?.detail?.field
        if (field) setErrors((current) => ({ ...current, [field]: error.message }))
        else setSubmitError(error.message)
      } else {
        setSubmitError('No pudimos crear el reclamo. Intentá nuevamente.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <PageContainer className={styles.page}>
        <LoadingState label="Cargando tu unidad" lines={5} />
      </PageContainer>
    )
  }

  return (
    <PageContainer className={styles.page}>
      <Link className={styles.backLink} to="/inquilino">
        <ArrowLeft aria-hidden="true" />
        Volver al inicio
      </Link>
      <PageHeading
        description="Contanos qué sucede en tu unidad. La inmobiliaria recibirá el reclamo con el estado inicial Recibido."
        eyebrow="Portal del inquilino"
        title="Crear un reclamo"
      />

      {loadError ? <AlertMessage>{loadError}</AlertMessage> : null}

      {!loadError && context ? (
        <>
          <section className={styles.contextCard} aria-labelledby="claim-context-title">
            <span className={styles.contextIcon} aria-hidden="true"><Building2 /></span>
            <div>
              <p className={styles.eyebrow}>Reclamo para</p>
              <h2 id="claim-context-title">{context.inquilino_nombre}</h2>
              <p>{claimPropertyLabel(context.propiedad)}</p>
              <small>{context.inquilino_email}</small>
            </div>
          </section>

          <form className={styles.formPanel} noValidate onSubmit={handleSubmit}>
            <div className={styles.formIntro}>
              <div>
                <h2>Detalle del problema</h2>
                <p>Los campos marcados con asterisco son obligatorios.</p>
              </div>
            </div>

            {submitError ? <AlertMessage>{submitError}</AlertMessage> : null}

            <div className={styles.formBody}>
              <FormField
                error={errors.descripcion}
                hint={`${values.descripcion.trim().length}/1000 caracteres. Incluí dónde ocurre y desde cuándo.`}
                id="descripcion"
                label="Descripción"
                required
              >
                <textarea
                  className={styles.textarea}
                  maxLength={1000}
                  name="descripcion"
                  onBlur={handleBlur}
                  onChange={handleChange}
                  placeholder="Ej. La canilla de la cocina pierde agua desde ayer..."
                  rows={6}
                  value={values.descripcion}
                />
              </FormField>

              <FormField
                error={errors.urgencia}
                hint="Elegí alta solo si existe un riesgo inmediato para personas o la propiedad."
                id="urgencia"
                label="Urgencia"
                required
              >
                <SelectInput
                  name="urgencia"
                  onBlur={handleBlur}
                  onChange={handleChange}
                  value={values.urgencia}
                >
                  <option value="">Seleccionar urgencia</option>
                  <option value="baja">Baja — puede esperar</option>
                  <option value="media">Media — requiere atención</option>
                  <option value="alta">Alta — hay riesgo inmediato</option>
                </SelectInput>
              </FormField>

              <div className={styles.fileField}>
                <span className={styles.fieldLabel} id="fotos-label">Fotos</span>
                <div>
                  <input
                    accept="image/jpeg,image/png"
                    aria-describedby={errors.fotos ? 'fotos-hint fotos-error' : 'fotos-hint'}
                    aria-invalid={errors.fotos ? true : undefined}
                    aria-labelledby="fotos-label"
                    className={styles.fileInput}
                    disabled={values.fotos.length >= MAX_CLAIM_PHOTOS}
                    id="fotos"
                    multiple
                    onChange={handleFiles}
                    ref={fileInputRef}
                    type="file"
                  />
                  <label
                    className={styles.fileButton}
                    data-disabled={values.fotos.length >= MAX_CLAIM_PHOTOS || undefined}
                    htmlFor="fotos"
                  >
                    <Camera aria-hidden="true" />
                    Seleccionar fotos
                  </label>
                </div>
                <p className={styles.fieldHint} id="fotos-hint">
                  Opcional. Hasta 3 imágenes JPG, JPEG o PNG de 5 MB cada una.
                </p>
                {errors.fotos ? (
                  <p className={styles.fieldError} id="fotos-error" role="alert">
                    {errors.fotos}
                  </p>
                ) : null}
              </div>

              {values.fotos.length ? (
                <ul className={styles.photoList} aria-label="Fotos seleccionadas">
                  {values.fotos.map((photo, index) => (
                    <SelectedPhoto
                      index={index}
                      key={`${photo.name}-${photo.lastModified}-${index}`}
                      onRemove={removePhoto}
                      photo={photo}
                    />
                  ))}
                </ul>
              ) : null}
            </div>

            <div className={styles.formActions}>
              <Link className={styles.secondaryLink} to="/inquilino">Cancelar</Link>
              <Button disabled={isSubmitting} leadingIcon={<Send />} type="submit">
                {isSubmitting ? 'Enviando…' : 'Enviar reclamo'}
              </Button>
            </div>
          </form>
        </>
      ) : null}
    </PageContainer>
  )
}

export default ReclamoFormPage
