import { useCallback, useEffect, useState } from 'react'
import {
  ArrowLeft,
  Building2,
  Mail,
  Pencil,
  Phone,
  Trash2,
  Unlink,
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
import {
  deleteInquilino,
  disassociateInquilino,
  getInquilino,
} from '../api/inquilinosApi.js'
import styles from './Inquilinos.module.css'

function propertyUnit(property) {
  if (property.tipo !== 'departamento') return ''
  return [
    property.piso === 0 ? 'Planta baja (piso 0)' : property.piso != null ? `Piso ${property.piso}` : null,
    property.numero ? `Unidad ${property.numero}` : null,
  ].filter(Boolean).join(' · ')
}

function InquilinoDetailPage() {
  const { inquilinoId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [tenant, setTenant] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(location.state?.notice ?? '')
  const [isLoading, setIsLoading] = useState(true)
  const [dialogAction, setDialogAction] = useState(null)
  const [isBusy, setIsBusy] = useState(false)

  const loadTenant = useCallback(
    (signal) =>
      getInquilino(inquilinoId, { signal })
        .then((response) => {
          setTenant(response)
          setError('')
        })
        .catch((requestError) => {
          if (requestError.name !== 'AbortError') setError(requestError.message)
        }),
    [inquilinoId],
  )

  useEffect(() => {
    const controller = new AbortController()
    let isActive = true
    loadTenant(controller.signal).finally(() => {
      if (isActive) setIsLoading(false)
    })
    return () => {
      isActive = false
      controller.abort()
    }
  }, [loadTenant])

  const handleConfirm = async () => {
    if (!dialogAction) return
    setIsBusy(true)
    try {
      if (dialogAction === 'delete') {
        await deleteInquilino(inquilinoId)
        navigate('/inquilinos', {
          replace: true,
          state: { notice: 'El inquilino se eliminó correctamente.' },
        })
        return
      }
      const updated = await disassociateInquilino(inquilinoId)
      setTenant(updated)
      setNotice('El inquilino quedó sin propiedad asignada.')
      setError('')
      setDialogAction(null)
    } catch (requestError) {
      setDialogAction(null)
      setError(requestError.message)
    } finally {
      setIsBusy(false)
    }
  }

  if (isLoading) {
    return (
      <PageContainer>
        <LoadingState label="Cargando detalle del inquilino" lines={6} />
      </PageContainer>
    )
  }

  if (!tenant) {
    return (
      <PageContainer>
        <AlertMessage>{error || 'No encontramos el inquilino solicitado.'}</AlertMessage>
      </PageContainer>
    )
  }

  const hasClaims = tenant.cantidad_reclamos > 0
  const isDisassociate = dialogAction === 'disassociate'

  return (
    <PageContainer>
      <Link className={styles.backLink} to="/inquilinos">
        <ArrowLeft aria-hidden="true" />
        Volver al listado
      </Link>
      <PageHeading
        action={
          <Link className={styles.primaryLink} to={`/inquilinos/${tenant.id}/editar`}>
            <Pencil aria-hidden="true" />
            Editar inquilino
          </Link>
        }
        description="Consultá sus datos de contacto y la propiedad que ocupa actualmente."
        eyebrow="Detalle del inquilino"
        title={tenant.nombre_completo}
      />

      <div className={styles.feedbackStack}>
        {notice ? <AlertMessage tone="success">{notice}</AlertMessage> : null}
        {error ? <AlertMessage>{error}</AlertMessage> : null}
        {hasClaims ? (
          <AlertMessage tone="warning">
            Tiene reclamos históricos: puede desasociarse, pero no eliminarse.
          </AlertMessage>
        ) : null}
      </div>

      <div className={styles.detailGrid}>
        <section className={styles.detailPanel} aria-labelledby="tenant-data-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Identificación</p>
              <h2 id="tenant-data-title">Datos del inquilino</h2>
            </div>
            <StatusBadge tone={tenant.estado === 'activo' ? 'success' : 'warning'}>
              {tenant.estado === 'activo' ? 'Activo' : 'Sin propiedad'}
            </StatusBadge>
          </div>
          <dl className={styles.detailList}>
            <div>
              <dt><UserRound aria-hidden="true" />DNI</dt>
              <dd>{tenant.dni}</dd>
            </div>
            <div>
              <dt><Mail aria-hidden="true" />Email</dt>
              <dd><a href={`mailto:${tenant.email}`}>{tenant.email}</a></dd>
            </div>
            <div>
              <dt><Phone aria-hidden="true" />Teléfono</dt>
              <dd><a href={`tel:${tenant.telefono}`}>{tenant.telefono}</a></dd>
            </div>
          </dl>
        </section>

        <section className={styles.detailPanel} aria-labelledby="tenant-property-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Ocupación actual</p>
              <h2 id="tenant-property-title">Propiedad asociada</h2>
            </div>
          </div>
          {tenant.propiedad ? (
            <div className={styles.propertyCard}>
              <span className={styles.propertyIcon} aria-hidden="true">
                <Building2 />
              </span>
              <div>
                <strong>{tenant.propiedad.direccion}</strong>
                <p>{tenant.propiedad.localidad}, {tenant.propiedad.provincia}</p>
                {propertyUnit(tenant.propiedad) ? <small>{propertyUnit(tenant.propiedad)}</small> : null}
              </div>
              <Link to={`/propiedades/${tenant.propiedad.id}`}>Ver propiedad</Link>
            </div>
          ) : (
            <div className={styles.unassignedState}>
              <Building2 aria-hidden="true" />
              <div>
                <strong>Sin propiedad asignada</strong>
                <p>Podés asociarlo desde la edición cuando haya una propiedad disponible.</p>
              </div>
            </div>
          )}
          <div className={styles.relationsSummary}>
            <span>
              {tenant.cantidad_reclamos === 0
                ? 'Sin reclamos históricos'
                : `${tenant.cantidad_reclamos} reclamos históricos`}
            </span>
          </div>
        </section>
      </div>

      <section className={styles.managementZone} aria-labelledby="association-title">
        <div>
          <h2 id="association-title">Administrar registro</h2>
          <p>
            {hasClaims
              ? 'La desasociación conserva al inquilino y sus reclamos históricos.'
              : 'Podés liberar la propiedad o eliminar el registro si ya no es necesario.'}
          </p>
        </div>
        <div className={styles.managementActions}>
          <Button
            disabled={!tenant.propiedad}
            leadingIcon={<Unlink />}
            onClick={() => setDialogAction('disassociate')}
            variant="secondary"
          >
            Desasociar propiedad
          </Button>
          <Button
            disabled={hasClaims}
            leadingIcon={<Trash2 />}
            onClick={() => setDialogAction('delete')}
            variant="danger"
          >
            Eliminar inquilino
          </Button>
        </div>
      </section>

      <ConfirmDialog
        confirmLabel={isDisassociate ? 'Desasociar propiedad' : 'Eliminar inquilino'}
        description={
          isDisassociate
            ? `Vas a liberar la propiedad de ${tenant.nombre_completo}. El inquilino y su historial se conservarán.`
            : `Vas a eliminar a ${tenant.nombre_completo}. Esta acción no se puede deshacer.`
        }
        isBusy={isBusy}
        onCancel={() => setDialogAction(null)}
        onConfirm={handleConfirm}
        open={Boolean(dialogAction)}
        title={isDisassociate ? '¿Desasociar la propiedad?' : '¿Eliminar inquilino?'}
      />
    </PageContainer>
  )
}

export default InquilinoDetailPage
