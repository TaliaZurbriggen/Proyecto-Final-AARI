import { useCallback } from 'react'
import { ArrowLeft, CalendarClock, ClipboardList, Home } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { getMyClaim } from '../api/reclamosApi.js'
import {
  claimStatusTone,
  formatClaimDate,
  formatClaimNumber,
  urgencyLabel,
} from '../presentation.js'
import { claimPropertyLabel } from '../validation.js'
import { usePollingResource } from '../usePollingResource.js'
import styles from './Reclamos.module.css'

function ReclamoDetailPage() {
  const { reclamoId } = useParams()
  const loadClaim = useCallback(
    (signal) => getMyClaim(reclamoId, { signal }),
    [reclamoId],
  )
  const { data: claim, error, isLoading } = usePollingResource(loadClaim, null)

  if (isLoading) {
    return (
      <PageContainer className={styles.claimsPage}>
        <LoadingState label="Cargando el seguimiento" lines={6} />
      </PageContainer>
    )
  }

  if (!claim) {
    return (
      <PageContainer className={styles.claimsPage}>
        <Link className={styles.backLink} to="/inquilino/reclamos">
          <ArrowLeft aria-hidden="true" />
          Volver a mis reclamos
        </Link>
        <AlertMessage>{error || 'No encontramos ese reclamo en tu cuenta.'}</AlertMessage>
      </PageContainer>
    )
  }

  return (
    <PageContainer className={styles.claimsPage}>
      <Link className={styles.backLink} to="/inquilino/reclamos">
        <ArrowLeft aria-hidden="true" />
        Volver a mis reclamos
      </Link>
      <PageHeading
        description="Cada cambio queda registrado con su fecha para que sepas cómo avanza."
        eyebrow="Seguimiento del reclamo"
        title={`Reclamo ${formatClaimNumber(claim.numero)}`}
      />
      {error ? <AlertMessage>{error}</AlertMessage> : null}

      <section className={styles.currentStatus} aria-labelledby="current-status-title">
        <div>
          <p className={styles.eyebrow}>Estado actual</p>
          <h2 id="current-status-title">{claim.estado}</h2>
          <p>Última actualización: {formatClaimDate(claim.updated_at)}</p>
        </div>
        <StatusBadge tone={claimStatusTone(claim.estado)}>{claim.estado}</StatusBadge>
      </section>

      <div className={styles.detailGrid}>
        <section className={styles.claimSummaryPanel} aria-labelledby="claim-detail-title">
          <div className={styles.panelTitle}>
            <ClipboardList aria-hidden="true" />
            <h2 id="claim-detail-title">Detalle informado</h2>
          </div>
          <p className={styles.detailDescription}>{claim.descripcion}</p>
          <dl className={styles.detailMetadata}>
            <div>
              <dt><Home aria-hidden="true" /> Unidad</dt>
              <dd>{claimPropertyLabel(claim.propiedad)}</dd>
            </div>
            <div>
              <dt>Urgencia</dt>
              <dd>{urgencyLabel(claim.urgencia)}</dd>
            </div>
            <div>
              <dt>Ingresado</dt>
              <dd>{formatClaimDate(claim.creado_en)}</dd>
            </div>
          </dl>
        </section>

        <section className={styles.timelinePanel} aria-labelledby="claim-timeline-title">
          <div className={styles.panelTitle}>
            <CalendarClock aria-hidden="true" />
            <h2 id="claim-timeline-title">Historial de estados</h2>
          </div>
          <ol className={styles.timeline}>
            {[...claim.historial].reverse().map((item, index) => (
              <li aria-current={index === 0 ? 'step' : undefined} key={`${item.timestamp}-${item.estado_nuevo}`}>
                <span className={styles.timelineMarker} aria-hidden="true" />
                <div>
                  <strong>{item.estado_nuevo}</strong>
                  <time dateTime={item.timestamp}>{formatClaimDate(item.timestamp)}</time>
                  {item.estado_anterior ? (
                    <p>Antes: {item.estado_anterior}</p>
                  ) : (
                    <p>Reclamo ingresado</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </PageContainer>
  )
}

export default ReclamoDetailPage
