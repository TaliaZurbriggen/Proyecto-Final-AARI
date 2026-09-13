import { useCallback } from 'react'
import { ArrowRight, ClipboardList, Plus } from 'lucide-react'
import { Link } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import {
  AlertMessage,
  EmptyState,
  LoadingState,
  StatusBadge,
} from '../../../components/ui/index.js'
import { listMyClaims } from '../api/reclamosApi.js'
import {
  claimStatusTone,
  formatClaimDate,
  formatClaimNumber,
  urgencyLabel,
} from '../presentation.js'
import { claimPropertyLabel } from '../validation.js'
import { usePollingResource } from '../usePollingResource.js'
import styles from './Reclamos.module.css'

function ReclamosListPage() {
  const loadClaims = useCallback(
    async (signal) => (await listMyClaims({ signal })).items,
    [],
  )
  const { data: claims, error, isLoading } = usePollingResource(loadClaims, [])

  return (
    <PageContainer className={styles.claimsPage}>
      <PageHeading
        action={
          <Link className={styles.primaryLink} to="/inquilino/reclamos/nuevo">
            <Plus aria-hidden="true" />
            Nuevo reclamo
          </Link>
        }
        description="Consultá el estado actual y cada avance informado por la inmobiliaria."
        eyebrow="Portal del inquilino"
        title="Mis reclamos"
      />

      {error ? <AlertMessage>{error}</AlertMessage> : null}
      {isLoading ? <LoadingState label="Cargando tus reclamos" lines={5} /> : null}

      {!isLoading && !error && claims.length === 0 ? (
        <EmptyState
          action={
            <Link className={styles.primaryLink} to="/inquilino/reclamos/nuevo">
              <Plus aria-hidden="true" />
              Crear el primero
            </Link>
          }
          description="Cuando informes un problema, vas a poder seguir todos sus cambios desde acá."
          icon={ClipboardList}
          title="Todavía no tenés reclamos"
        />
      ) : null}

      {!isLoading && claims.length ? (
        <section className={styles.claimsList} aria-label="Reclamos registrados">
          {claims.map((claim) => (
            <article className={styles.claimCard} key={claim.id}>
              <div className={styles.claimCardHeader}>
                <div>
                  <p className={styles.claimCardNumber}>
                    Reclamo {formatClaimNumber(claim.numero)}
                  </p>
                  <p className={styles.claimCardProperty}>
                    {claimPropertyLabel(claim.propiedad)}
                  </p>
                </div>
                <StatusBadge tone={claimStatusTone(claim.estado)}>
                  {claim.estado}
                </StatusBadge>
              </div>

              <p className={styles.claimDescription}>{claim.descripcion}</p>

              <dl className={styles.claimMetadata}>
                <div>
                  <dt>Urgencia</dt>
                  <dd>{urgencyLabel(claim.urgencia)}</dd>
                </div>
                <div>
                  <dt>Ingresado</dt>
                  <dd>{formatClaimDate(claim.creado_en, { short: true })}</dd>
                </div>
                <div>
                  <dt>Último cambio</dt>
                  <dd>{formatClaimDate(claim.updated_at, { short: true })}</dd>
                </div>
              </dl>

              <Link className={styles.claimDetailLink} to={`/inquilino/reclamos/${claim.id}`}>
                Ver seguimiento
                <ArrowRight aria-hidden="true" />
              </Link>
            </article>
          ))}
        </section>
      ) : null}
    </PageContainer>
  )
}

export default ReclamosListPage
