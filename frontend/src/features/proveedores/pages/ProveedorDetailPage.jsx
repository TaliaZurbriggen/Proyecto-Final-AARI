import { useEffect, useState } from 'react'
import {
  ArrowLeft,
  BadgeCheck,
  Clock3,
  MapPinned,
  MessageCircle,
  Pencil,
  Power,
  Wrench,
} from 'lucide-react'
import { Link, useLocation, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  Button,
  ConfirmDialog,
  LoadingState,
  StatusBadge,
} from '../../../components/ui/index.js'
import { getProveedor, updateProveedorEstado } from '../api/proveedoresApi.js'
import styles from './Proveedores.module.css'

function formatTime(value) {
  return value?.slice(0, 5) ?? ''
}

function ProveedorDetailPage() {
  const { proveedorId } = useParams()
  const location = useLocation()
  const [provider, setProvider] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isConfirmOpen, setIsConfirmOpen] = useState(false)
  const [isUpdating, setIsUpdating] = useState(false)
  const [notice, setNotice] = useState(location.state?.notice ?? '')

  useEffect(() => {
    const controller = new AbortController()
    let isActive = true
    getProveedor(proveedorId, { signal: controller.signal })
      .then((result) => {
        if (isActive) setProvider(result)
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
  }, [proveedorId])

  const handleStatusChange = async () => {
    setIsUpdating(true)
    try {
      const updated = await updateProveedorEstado(proveedorId, !provider.activo)
      setProvider(updated)
      setNotice(
        updated.activo
          ? 'El proveedor volvió a estar disponible para nuevas asignaciones.'
          : 'El proveedor quedó inactivo y no se considerará en nuevas asignaciones.',
      )
      setError('')
      setIsConfirmOpen(false)
    } catch (requestError) {
      setError(requestError.message)
      setIsConfirmOpen(false)
    } finally {
      setIsUpdating(false)
    }
  }

  if (isLoading) return <PageContainer><LoadingState label="Cargando detalle del proveedor" lines={7} /></PageContainer>
  if (!provider) return <PageContainer><AlertMessage>{error || 'No encontramos el proveedor solicitado.'}</AlertMessage></PageContainer>

  return (
    <PageContainer>
      <Link className={styles.backLink} to="/proveedores"><ArrowLeft aria-hidden="true" />Volver al listado</Link>
      <PageHeading
        action={<Link className={styles.primaryLink} to={`/proveedores/${provider.id}/editar`}><Pencil aria-hidden="true" />Editar proveedor</Link>}
        description="Consultá sus especialidades, disponibilidad habitual y zonas de trabajo."
        eyebrow="Detalle del proveedor"
        title={provider.nombre_razon_social}
      />
      <div className={styles.feedbackStack}>{notice ? <AlertMessage tone="success">{notice}</AlertMessage> : null}{error ? <AlertMessage>{error}</AlertMessage> : null}</div>

      <div className={styles.detailGrid}>
        <section className={styles.detailPanel} aria-labelledby="provider-contact-title">
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Contacto</p><h2 id="provider-contact-title">Datos del prestador</h2></div><StatusBadge tone={provider.activo ? 'success' : 'neutral'}>{provider.activo ? 'Activo' : 'Inactivo'}</StatusBadge></div>
          <dl className={styles.detailList}>
            <div><dt><MessageCircle aria-hidden="true" />WhatsApp</dt><dd><a href={`https://wa.me/${provider.telefono.replace(/\D/g, '')}`} rel="noreferrer" target="_blank">{provider.telefono}</a></dd></div>
            <div><dt><BadgeCheck aria-hidden="true" />Matrícula</dt><dd>{provider.matricula || 'No informada'}</dd></div>
            <div><dt><Clock3 aria-hidden="true" />Horario habitual</dt><dd>{provider.hora_inicio ? `${formatTime(provider.hora_inicio)} a ${formatTime(provider.hora_fin)}` : 'No informado'}</dd></div>
          </dl>
        </section>

        <section className={styles.detailPanel} aria-labelledby="provider-specialties-title">
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Oficios</p><h2 id="provider-specialties-title">Especialidades</h2></div><Wrench aria-hidden="true" className={styles.headingIcon} /></div>
          <div className={styles.detailBadgeList}>{provider.especialidades.map((specialty) => <span key={specialty.id}>{specialty.nombre}</span>)}</div>
        </section>
      </div>

      <section className={`${styles.detailPanel} ${styles.coverageDetail}`} aria-labelledby="provider-coverage-title">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Alcance geográfico</p><h2 id="provider-coverage-title">Zonas de cobertura</h2></div><MapPinned aria-hidden="true" className={styles.headingIcon} /></div>
        <div className={styles.coverageDetailGrid}>{provider.coberturas.map((coverage) => <article key={coverage.id}><h3>{coverage.localidad}, {coverage.provincia}</h3>{coverage.cubre_toda_localidad ? <p>Toda la localidad, incluso propiedades sin barrio informado.</p> : <><p>Barrios cubiertos:</p><div className={styles.badgeList}>{coverage.barrios.map((neighborhood) => <span key={neighborhood}>{neighborhood}</span>)}</div></>}</article>)}</div>
      </section>

      <section className={`${styles.statusZone} ${provider.activo ? '' : styles.statusZoneInactive}`} aria-labelledby="provider-status-title">
        <div><h2 id="provider-status-title">{provider.activo ? 'Desactivar proveedor' : 'Reactivar proveedor'}</h2><p>{provider.activo ? 'Dejará de aparecer como opción para nuevas asignaciones, pero se conservarán sus datos e historial.' : 'Volverá a estar disponible para nuevas asignaciones según su cobertura y especialidad.'}</p></div>
        <Button leadingIcon={<Power />} onClick={() => setIsConfirmOpen(true)} variant={provider.activo ? 'danger' : 'primary'}>{provider.activo ? 'Desactivar' : 'Reactivar'}</Button>
      </section>

      <ConfirmDialog
        confirmLabel={provider.activo ? 'Desactivar proveedor' : 'Reactivar proveedor'}
        description={provider.activo ? `${provider.nombre_razon_social} no podrá recibir nuevas asignaciones. Su información se conservará.` : `${provider.nombre_razon_social} volverá a ser elegible para nuevas asignaciones.`}
        isBusy={isUpdating}
        onCancel={() => setIsConfirmOpen(false)}
        onConfirm={handleStatusChange}
        open={isConfirmOpen}
        title={provider.activo ? '¿Desactivar proveedor?' : '¿Reactivar proveedor?'}
      />
    </PageContainer>
  )
}

export default ProveedorDetailPage
