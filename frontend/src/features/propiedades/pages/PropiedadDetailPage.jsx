import { useEffect, useState } from 'react'
import {
  ArrowLeft,
  Building2,
  MapPin,
  Pencil,
  Trash2,
  UserPlus,
  UserRound,
} from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  ConfirmDialog,
  LoadingState,
  StatusBadge,
} from '../../../components/ui/index.js'
import { getPropertyTenant } from '../../inquilinos/api/inquilinosApi.js'
import { deletePropiedad, getPropiedad } from '../api/propiedadesApi.js'
import styles from './Propiedades.module.css'

const TYPE_LABELS = {
  departamento: 'Departamento',
  casa: 'Casa',
  local: 'Local',
  otro: 'Otro',
}

function unitSummary(property) {
  const hasFloor = property.piso !== null && property.piso !== undefined
  return [
    hasFloor
      ? property.piso === 0
        ? 'Planta baja (piso 0)'
        : `Piso ${property.piso}`
      : null,
    property.numero ? `Unidad ${property.numero}` : null,
  ]
    .filter(Boolean)
    .join(' · ')
}

function PropiedadDetailPage() {
  const { propiedadId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [property, setProperty] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let isActive = true
    Promise.all([
      getPropiedad(propiedadId, { signal: controller.signal }),
      getPropertyTenant(propiedadId, { signal: controller.signal }),
    ])
      .then(([propertyResponse, tenantResponse]) => {
        if (isActive) {
          setProperty(propertyResponse)
          setTenant(tenantResponse)
        }
      })
      .catch((requestError) => {
        if (isActive && requestError.name !== 'AbortError') {
          setError(requestError.message)
        }
      })
      .finally(() => {
        if (isActive) setIsLoading(false)
      })
    return () => {
      isActive = false
      controller.abort()
    }
  }, [propiedadId])

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      await deletePropiedad(propiedadId)
      navigate('/propiedades', {
        replace: true,
        state: { notice: 'La propiedad se eliminó correctamente.' },
      })
    } catch (requestError) {
      setIsDeleteOpen(false)
      setError(requestError.message)
    } finally {
      setIsDeleting(false)
    }
  }

  if (isLoading) {
    return (
      <PageContainer>
        <LoadingState label="Cargando detalle de la propiedad" lines={6} />
      </PageContainer>
    )
  }

  if (!property) {
    return (
      <PageContainer>
        <AlertMessage>{error || 'No encontramos la propiedad solicitada.'}</AlertMessage>
      </PageContainer>
    )
  }

  const deletionReason = property.cantidad_reclamos > 0
    ? 'Tiene reclamos históricos asociados y debe conservarse para mantener la trazabilidad.'
    : tenant
      ? 'Tiene un inquilino activo. Primero debe resolverse esa asociación.'
      : ''

  return (
    <PageContainer>
      <Link className={styles.backLink} to="/propiedades">
        <ArrowLeft aria-hidden="true" />
        Volver al listado
      </Link>
      <PageHeading
        action={
          <Link className={styles.primaryLink} to={`/propiedades/${property.id}/editar`}>
            <Pencil aria-hidden="true" />
            Editar propiedad
          </Link>
        }
        description="Consultá la ubicación, el tipo y la persona responsable del inmueble."
        eyebrow="Detalle de la propiedad"
        title={property.direccion}
      />

      <div className={styles.feedbackStack}>
        {location.state?.notice ? (
          <AlertMessage tone="success">{location.state.notice}</AlertMessage>
        ) : null}
        {error ? <AlertMessage>{error}</AlertMessage> : null}
      </div>

      <div className={styles.detailGrid}>
        <section className={styles.detailPanel} aria-labelledby="property-data-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Ubicación</p>
              <h2 id="property-data-title">Datos del inmueble</h2>
            </div>
            <StatusBadge tone="info">{TYPE_LABELS[property.tipo]}</StatusBadge>
          </div>
          <dl className={styles.detailList}>
            <div>
              <dt><MapPin aria-hidden="true" />Dirección</dt>
              <dd>{property.direccion}</dd>
            </div>
            <div>
              <dt>Localidad</dt>
              <dd>{property.localidad}</dd>
            </div>
            <div>
              <dt>Provincia</dt>
              <dd>{property.provincia}</dd>
            </div>
            <div>
              <dt>Barrio</dt>
              <dd>{property.barrio || 'Sin barrio informado'}</dd>
            </div>
            {property.tipo === 'departamento' ? (
              <div>
                <dt>Piso y unidad</dt>
                <dd>{unitSummary(property) || 'Sin especificar'}</dd>
              </div>
            ) : null}
          </dl>
        </section>

        <section className={styles.detailPanel} aria-labelledby="owner-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Titularidad</p>
              <h2 id="owner-title">Propietario asociado</h2>
            </div>
          </div>
          <div className={styles.ownerCard}>
            <span className={styles.ownerIcon} aria-hidden="true">
              <UserRound />
            </span>
            <div>
              <strong>{property.propietario.nombre_completo}</strong>
              <p>Responsable actual del inmueble</p>
            </div>
            <Link to={`/propietarios/${property.propietario.id}`}>Ver propietario</Link>
          </div>
          <div className={styles.relationsSummary}>
            <Building2 aria-hidden="true" />
            <span>
              {property.cantidad_reclamos === 0
                ? 'Sin reclamos históricos'
                : `${property.cantidad_reclamos} reclamos históricos`}
            </span>
          </div>
        </section>
      </div>

      <section
        className={`${styles.detailPanel} ${styles.tenantPanel}`}
        aria-labelledby="tenant-title"
      >
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Ocupación actual</p>
            <h2 id="tenant-title">Inquilino asociado</h2>
          </div>
          <StatusBadge tone={tenant ? 'success' : 'neutral'}>
            {tenant ? 'Ocupada' : 'Disponible'}
          </StatusBadge>
        </div>
        <div className={styles.ownerCard}>
          <span className={styles.ownerIcon} aria-hidden="true">
            {tenant ? <UserRound /> : <UserPlus />}
          </span>
          <div>
            <strong>{tenant ? tenant.nombre_completo : 'Sin inquilino activo'}</strong>
            <p>
              {tenant
                ? `${tenant.email} · DNI ${tenant.dni}`
                : 'La propiedad está disponible para una nueva asociación.'}
            </p>
          </div>
          <Link
            to={
              tenant
                ? `/inquilinos/${tenant.id}`
                : `/inquilinos/nuevo?propiedad_id=${property.id}`
            }
          >
            {tenant ? 'Ver inquilino' : 'Asignar inquilino'}
          </Link>
        </div>
      </section>

      <section className={styles.dangerZone} aria-labelledby="danger-title">
        <div>
          <h2 id="danger-title">Eliminar propiedad</h2>
          <p>
            {deletionReason
              ? deletionReason
              : 'Solo se eliminará después de confirmar la acción.'}
          </p>
        </div>
        <Button
          disabled={Boolean(deletionReason)}
          leadingIcon={<Trash2 />}
          onClick={() => setIsDeleteOpen(true)}
          variant="danger"
        >
          Eliminar
        </Button>
      </section>

      <ConfirmDialog
        confirmLabel="Eliminar propiedad"
        description={`Vas a eliminar ${property.direccion}. Esta acción no se puede deshacer.`}
        isBusy={isDeleting}
        onCancel={() => setIsDeleteOpen(false)}
        onConfirm={handleDelete}
        open={isDeleteOpen}
        title="¿Eliminar propiedad?"
      />
    </PageContainer>
  )
}

export default PropiedadDetailPage
