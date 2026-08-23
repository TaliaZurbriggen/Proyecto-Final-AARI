import { useEffect, useState } from 'react'
import { ArrowLeft, Building2, Mail, MapPin, Pencil, Phone, Trash2 } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  ConfirmDialog,
  EmptyState,
  LoadingState,
} from '../../../components/ui/index.js'
import { deletePropietario, getPropietario } from '../api/propietariosApi.js'
import styles from './Propietarios.module.css'

function PropietarioDetailPage() {
  const { propietarioId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [owner, setOwner] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let isActive = true
    getPropietario(propietarioId, { signal: controller.signal })
      .then((response) => {
        if (isActive) setOwner(response)
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
  }, [propietarioId])

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      await deletePropietario(propietarioId)
      navigate('/propietarios', {
        replace: true,
        state: { notice: 'El propietario se eliminó correctamente.' },
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
        <LoadingState label="Cargando detalle del propietario" lines={6} />
      </PageContainer>
    )
  }

  if (!owner) {
    return (
      <PageContainer>
        <AlertMessage>{error || 'No encontramos el propietario solicitado.'}</AlertMessage>
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <Link className={styles.backLink} to="/propietarios">
        <ArrowLeft aria-hidden="true" />
        Volver al listado
      </Link>
      <PageHeading
        action={
          <Link className={styles.primaryLink} to={`/propietarios/${owner.id}/editar`}>
            <Pencil aria-hidden="true" />
            Editar datos
          </Link>
        }
        description="Consultá sus datos de contacto y los inmuebles que tiene asociados."
        eyebrow="Detalle del propietario"
        title={owner.nombre_completo}
      />

      <div className={styles.feedbackStack}>
        {location.state?.notice ? (
          <AlertMessage tone="success">{location.state.notice}</AlertMessage>
        ) : null}
        {error ? <AlertMessage>{error}</AlertMessage> : null}
      </div>

      <div className={styles.detailGrid}>
        <section className={styles.detailPanel} aria-labelledby="contact-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Información personal</p>
              <h2 id="contact-title">Datos de contacto</h2>
            </div>
          </div>
          <dl className={styles.contactList}>
            <div>
              <dt>DNI</dt>
              <dd>{owner.dni}</dd>
            </div>
            <div>
              <dt><Mail aria-hidden="true" />Email</dt>
              <dd><a href={`mailto:${owner.email}`}>{owner.email}</a></dd>
            </div>
            <div>
              <dt><Phone aria-hidden="true" />Teléfono</dt>
              <dd><a href={`tel:${owner.telefono}`}>{owner.telefono}</a></dd>
            </div>
          </dl>
        </section>

        <section className={styles.detailPanel} aria-labelledby="properties-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Patrimonio asociado</p>
              <h2 id="properties-title">Inmuebles ({owner.cantidad_inmuebles})</h2>
            </div>
          </div>

          {owner.propiedades.length ? (
            <ul className={styles.propertiesList}>
              {owner.propiedades.map((property) => (
                <li key={property.id}>
                  <span className={styles.propertyIcon} aria-hidden="true">
                    <Building2 />
                  </span>
                  <div>
                    <strong>{property.direccion}</strong>
                    <p>
                      <MapPin aria-hidden="true" />
                      {property.localidad}, {property.provincia} · {property.tipo}
                    </p>
                  </div>
                  <Link to={`/propiedades/${property.id}`}>Ver inmueble</Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              description="Cuando registres una propiedad a su nombre, aparecerá en esta sección."
              icon={Building2}
              title="Sin inmuebles asociados"
            />
          )}
        </section>
      </div>

      <section className={styles.dangerZone} aria-labelledby="danger-title">
        <div>
          <h2 id="danger-title">Eliminar propietario</h2>
          <p>Solo se podrá eliminar si no tiene inmuebles asociados.</p>
        </div>
        <Button
          leadingIcon={<Trash2 />}
          onClick={() => setIsDeleteOpen(true)}
          variant="danger"
        >
          Eliminar
        </Button>
      </section>

      <ConfirmDialog
        confirmLabel="Eliminar propietario"
        description={`Vas a eliminar a ${owner.nombre_completo}. Esta acción no se puede deshacer.`}
        isBusy={isDeleting}
        onCancel={() => setIsDeleteOpen(false)}
        onConfirm={handleDelete}
        open={isDeleteOpen}
        title="¿Eliminar propietario?"
      />
    </PageContainer>
  )
}

export default PropietarioDetailPage
