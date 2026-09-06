import { CheckCircle2, ClipboardList, Mail } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import { PageContainer } from '../../../components/layout/index.js'
import { EmptyState, StatusBadge } from '../../../components/ui/index.js'
import { claimPropertyLabel } from '../validation.js'
import styles from './Reclamos.module.css'

function formatDate(value) {
  return new Intl.DateTimeFormat('es-AR', {
    dateStyle: 'long',
    timeStyle: 'short',
  }).format(new Date(value))
}

function ReclamoConfirmationPage() {
  const { state } = useLocation()
  if (!state?.claim || !state?.context) {
    return (
      <PageContainer className={styles.page}>
        <EmptyState
          action={<Link className={styles.primaryLink} to="/inquilino/reclamos/nuevo">Crear reclamo</Link>}
          description="Esta confirmación solo está disponible después de enviar un reclamo."
          icon={ClipboardList}
          title="No hay un reclamo para mostrar"
        />
      </PageContainer>
    )
  }

  const { claim, context, descripcion } = state
  return (
    <PageContainer className={styles.confirmationPage}>
      <section className={styles.confirmation} aria-labelledby="confirmation-title">
        <span className={styles.confirmationIcon} aria-hidden="true"><CheckCircle2 /></span>
        <p className={styles.eyebrow}>Reclamo recibido</p>
        <h1 id="confirmation-title">Tu reclamo quedó registrado</h1>
        <p className={styles.claimNumber}>#{String(claim.numero).padStart(6, '0')}</p>
        <StatusBadge tone="info">{claim.estado}</StatusBadge>

        <dl className={styles.summaryList}>
          <div><dt>Unidad</dt><dd>{claimPropertyLabel(context.propiedad)}</dd></div>
          <div><dt>Fecha de ingreso</dt><dd>{formatDate(claim.creado_en)}</dd></div>
          <div><dt>Descripción</dt><dd>{descripcion}</dd></div>
          <div><dt>Fotos adjuntas</dt><dd>{claim.fotos_adjuntas}</dd></div>
        </dl>

        <div className={styles.emailNotice}>
          <Mail aria-hidden="true" />
          <p>
            Enviaremos la confirmación a <strong>{context.inquilino_email}</strong>.
            Si el correo falla, el reclamo seguirá registrado.
          </p>
        </div>

        <Link className={styles.primaryLink} to="/inquilino">Volver al inicio</Link>
      </section>
    </PageContainer>
  )
}

export default ReclamoConfirmationPage
