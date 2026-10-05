import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Building2, ClipboardList, ContactRound, FileText, History, KeyRound, RefreshCw, UsersRound, Wrench } from 'lucide-react'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { getAdminSummary } from '../api/homeApi.js'
import styles from './AdminHomePage.module.css'

const modules = [
  { key: 'propietarios', label: 'Propietarios', description: 'Registrados', icon: UsersRound },
  { key: 'propiedades', label: 'Propiedades', description: 'Registradas', icon: Building2 },
  { key: 'inquilinos', label: 'Inquilinos', description: 'Registrados', icon: KeyRound },
  { key: 'proveedores', label: 'Proveedores', icon: Wrench },
  { key: 'operadores', label: 'Operadores', icon: ContactRound },
]
const numberFormat = new Intl.NumberFormat('es-AR')
const dateFormat = new Intl.DateTimeFormat('es-AR', {
  dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Argentina/Buenos_Aires',
})

function AdminHomePage() {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ data: null, error: '', loading: true })

  useEffect(() => {
    const controller = new AbortController()
    getAdminSummary({ signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) setState({ data, error: '', loading: false })
    }).catch((error) => {
      if (!controller.signal.aborted) {
        setState({ data: null, error: error.message || 'No pudimos obtener el resumen.', loading: false })
      }
    })
    return () => controller.abort()
  }, [attempt])

  const refresh = () => {
    setState({ data: null, error: '', loading: true })
    setAttempt((value) => value + 1)
  }
  const { data, error, loading } = state
  const count = (value) => data ? numberFormat.format(value) : '—'
  const pending = data?.reclamos.pendientes_clasificacion
  const isEmpty = data && modules.every(({ key }) => data[key].total === 0)
    && data.reclamos.activos === 0

  return (
    <PageContainer className={styles.home}>
      <PageHeading eyebrow="Administración" title="Tu inmobiliaria, de un vistazo."
        description="Bienvenido. Revisá los pendientes y seguí con tu gestión." />
      <div className={styles.toolbar}>
        <p className={styles.updated} role="status" aria-live="polite">
          {loading ? 'Consultando el resumen…' : error ? 'Resumen no disponible'
            : `Última consulta · ${dateFormat.format(new Date(data.consultado_en))}`}
        </p>
        <Button variant="secondary" leadingIcon={<RefreshCw />} onClick={refresh} disabled={loading}>
          Actualizar
        </Button>
      </div>
      {error ? <AlertMessage>{error} Los accesos a los módulos siguen disponibles.</AlertMessage> : null}
      {loading ? <LoadingState label="Cargando resumen operativo" lines={1} /> : null}
      <section className={styles.operational} aria-label="Situación de los reclamos" aria-busy={loading}>
        <article className={`${styles.summary} ${styles.activeSummary}`}>
          <h2 className={styles.summaryTitle}><ClipboardList aria-hidden="true" />Reclamos activos</h2>
          <strong className={styles.number}>{count(data?.reclamos.activos)}</strong>
          <p>{data?.reclamos.activos === 0 ? 'No hay reclamos activos.' : 'Solicitudes que todavía no están resueltas.'}</p>
          <small>Incluye los pendientes de clasificación.</small>
        </article>
        <article className={styles.summary}>
          <div className={styles.summaryTop}>
            <h2 className={styles.summaryTitle}>Pendientes de clasificación</h2>
            <StatusBadge tone={pending > 0 ? 'warning' : pending === 0 ? 'success' : 'neutral'}>
              {loading ? 'Consultando' : error ? 'Sin información' : pending === 0 ? 'Sin pendientes' : 'Requieren revisión'}
            </StatusBadge>
          </div>
          <strong className={styles.number}>{count(pending)}</strong>
          <p>{pending === 0 ? 'No hay casos que requieran clasificación manual.'
            : 'La inmobiliaria debe revisar y decidir el tipo de gasto.'}</p>
          {/* HU13 no está en main: no publicar un enlace a una ruta inexistente. */}
          <Button disabled className={styles.reviewButton}>Revisar casos</Button>
          <small>Este acceso se habilitará cuando se integre HU13.</small>
        </article>
      </section>
      <section aria-labelledby="home-modules-title" aria-busy={loading}>
        <div className={styles.sectionHeading}>
          <h2 id="home-modules-title">Tu base de trabajo</h2><p>Elegí un módulo para continuar</p>
        </div>
        <div className={styles.modules}>
          {modules.map(({ key, label, description, icon: Icon }) => (
            <Link className={styles.module} to={`/${key}`} key={key}>
              <Icon aria-hidden="true" className={styles.moduleIcon} />
              <strong className={styles.moduleNumber}>{count(data?.[key].total)}</strong>
              <span className={styles.moduleName}>{label}</span>
              <small>{description ?? (data ? `${numberFormat.format(data[key].activos)} activos` : 'Activos sin consultar')}</small>
              <span className={styles.openModule}>Ver listado →</span>
            </Link>
          ))}
        </div>
      </section>
      {isEmpty ? <EmptyState title="Tu base de trabajo está lista para empezar"
        description="Usá los accesos para registrar los primeros datos de la inmobiliaria." /> : null}
      <section className={styles.shortcuts} aria-label="Contratos e historial">
        <Link to="/contratos" className={styles.shortcut}>
          <span className={styles.shortcutIcon}><FileText aria-hidden="true" /></span>
          <span><strong>Contratos de alquiler</strong><span>Consultá los documentos y la vigencia de cada alquiler.</span><em>Abrir contratos →</em></span>
        </Link>
        <Link to="/propiedades" className={styles.shortcut}>
          <span className={styles.shortcutIcon}><History aria-hidden="true" /></span>
          <span><strong>Historial de reclamos</strong><span>Elegí una propiedad para consultar sus reclamos.</span><em>Buscar propiedad →</em></span>
        </Link>
      </section>
    </PageContainer>
  )
}

export default AdminHomePage
