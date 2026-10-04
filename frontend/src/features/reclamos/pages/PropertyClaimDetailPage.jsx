import { useCallback } from 'react'
import { ArrowLeft, CalendarClock, ClipboardList, Home } from 'lucide-react'
import { Link, useLocation, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { getPropertyClaim } from '../api/propertyClaimsApi.js'
import { claimStatusTone, formatClaimDate, formatClaimNumber, urgencyLabel } from '../presentation.js'
import { claimPropertyLabel } from '../validation.js'
import { expenseLabel, propertyHistoryPath } from '../propertyHistory.js'
import { useHistoryResource } from '../useHistoryResource.js'
import styles from './Reclamos.module.css'

function PropertyClaimDetailPage({ tenantView = false }) {
  const { propiedadId, reclamoId } = useParams()
  const location = useLocation()
  const load = useCallback(
    (signal) => getPropertyClaim(propiedadId, reclamoId, { signal }),
    [propiedadId, reclamoId],
  )
  const { data: claim, error, isLoading } = useHistoryResource(`${propiedadId}:${reclamoId}`, load)
  const back = `${propertyHistoryPath(propiedadId, tenantView)}${location.search}`

  return (
    <PageContainer className={styles.claimsPage}>
      <Link className={styles.backLink} to={back}><ArrowLeft aria-hidden="true" />Volver al historial</Link>
      {isLoading ? <LoadingState label="Cargando detalle del reclamo" lines={6} /> : null}
      {error ? <AlertMessage>{error}</AlertMessage> : null}
      {claim ? (
        <>
          <PageHeading title={`Reclamo ${formatClaimNumber(claim.numero)}`} eyebrow="Historial de la propiedad" description={claimPropertyLabel(claim.propiedad)} />
          <section className={styles.currentStatus} aria-labelledby="property-claim-status">
            <div><p className={styles.eyebrow}>Estado actual</p><h2 id="property-claim-status">{claim.estado}</h2><p>Última actualización: {formatClaimDate(claim.updated_at)}</p></div>
            <StatusBadge tone={claimStatusTone(claim.estado)}>{claim.estado}</StatusBadge>
          </section>
          <div className={styles.detailGrid}>
            <section className={styles.claimSummaryPanel} aria-labelledby="property-claim-detail">
              <div className={styles.panelTitle}><ClipboardList aria-hidden="true" /><h2 id="property-claim-detail">Detalle del reclamo</h2></div>
              <p className={styles.detailDescription}>{claim.descripcion}</p>
              <dl className={styles.detailMetadata}>
                <div><dt><Home aria-hidden="true" />Unidad</dt><dd>{claimPropertyLabel(claim.propiedad)}</dd></div>
                <div><dt>Urgencia</dt><dd>{urgencyLabel(claim.urgencia)}</dd></div>
                <div><dt>Tipo de gasto</dt><dd>{expenseLabel(claim.tipo_gasto)}</dd></div>
                <div><dt>Ingresado</dt><dd>{formatClaimDate(claim.creado_en)}</dd></div>
              </dl>
            </section>
            <section className={styles.timelinePanel} aria-labelledby="property-claim-timeline">
              <div className={styles.panelTitle}><CalendarClock aria-hidden="true" /><h2 id="property-claim-timeline">Historial de estados</h2></div>
              {claim.historial.length ? (
                <ol className={styles.timeline}>
                  {[...claim.historial].reverse().map((item, index) => (
                    <li key={`${item.timestamp}-${item.estado_nuevo}-${index}`} aria-current={index === 0 ? 'step' : undefined}>
                      <span className={styles.timelineMarker} aria-hidden="true" />
                      <div><strong>{item.estado_nuevo}</strong><time dateTime={item.timestamp}>{formatClaimDate(item.timestamp)}</time><p>{item.estado_anterior ? `Antes: ${item.estado_anterior}` : 'Reclamo ingresado'} · Origen: {item.origen}</p></div>
                    </li>
                  ))}
                </ol>
              ) : <p>Este reclamo todavía no tiene cambios de estado registrados.</p>}
            </section>
          </div>
        </>
      ) : null}
    </PageContainer>
  )
}

export default PropertyClaimDetailPage
