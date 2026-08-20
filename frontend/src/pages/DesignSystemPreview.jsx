import { useState } from 'react'
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Plus,
  Wrench,
} from 'lucide-react'
import { AppHeader, PageContainer, PageHeading } from '../components/layout/index.js'
import {
  Button,
  EmptyState,
  FormField,
  IconButton,
  LoadingState,
  StatusBadge,
} from '../components/ui/index.js'
import styles from './DesignSystemPreview.module.css'

const navigationItems = [
  { href: '#inicio', label: 'Inicio' },
  { href: '#reclamos', label: 'Reclamos' },
  { href: '#propiedades', label: 'Propiedades' },
  { href: '#proveedores', label: 'Proveedores' },
]

const metrics = [
  {
    helper: '3 requieren atención hoy',
    icon: ClipboardList,
    label: 'Reclamos abiertos',
    tone: 'info',
    value: '12',
  },
  {
    helper: 'Dentro del objetivo mensual',
    icon: Clock3,
    label: 'Tiempo medio de respuesta',
    tone: 'warning',
    value: '2 h 18 min',
  },
  {
    helper: '8 puntos más que el mes anterior',
    icon: CheckCircle2,
    label: 'Resolución satisfactoria',
    tone: 'success',
    value: '91%',
  },
]

const claims = [
  {
    address: 'Av. Central 1840 · Depto. 3B',
    id: 'REC-0241',
    status: 'En proceso',
    title: 'Pérdida de agua bajo la mesada',
    tone: 'info',
  },
  {
    address: 'Calle Norte 456 · Casa',
    id: 'REC-0238',
    status: 'Urgente',
    title: 'Corte total de electricidad',
    tone: 'danger',
  },
  {
    address: 'Bv. del Parque 910 · Depto. 8A',
    id: 'REC-0235',
    status: 'Esperando respuesta',
    title: 'Persiana del dormitorio trabada',
    tone: 'warning',
  },
]

function DesignSystemPreview() {
  const [activeItem, setActiveItem] = useState('Inicio')
  const [searchValue, setSearchValue] = useState('')

  return (
    <>
      <AppHeader
        activeItem={activeItem}
        items={navigationItems}
        notificationCount={3}
        onNavigate={(item) => setActiveItem(item.label)}
        onSearchChange={(event) => setSearchValue(event.target.value)}
        onSearchClear={() => setSearchValue('')}
        profileName="Usuario demo"
        profileRole="Administración"
        searchValue={searchValue}
      />

      <PageContainer>
        <PageHeading
          action={<Button leadingIcon={<Plus />}>Nuevo reclamo</Button>}
          description="Una base compartida para construir cada pantalla con la misma identidad, jerarquía y accesibilidad."
          eyebrow="Sistema visual compartido"
          title="Buen día"
        />

        <section className={styles.metrics} aria-label="Resumen operativo">
          {metrics.map((metric) => {
            const MetricIcon = metric.icon

            return (
              <article className={styles.metric} key={metric.label}>
                <span className={styles.metricIcon} data-tone={metric.tone}>
                  <MetricIcon aria-hidden="true" />
                </span>
                <div>
                  <p className={styles.metricLabel}>{metric.label}</p>
                  <strong className={styles.metricValue}>{metric.value}</strong>
                  <p className={styles.metricHelper}>{metric.helper}</p>
                </div>
              </article>
            )
          })}
        </section>

        <div className={styles.workspace}>
          <section className={styles.panel} aria-labelledby="claims-title">
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.sectionEyebrow}>Prioridad operativa</p>
                <h2 id="claims-title">Reclamos que requieren atención</h2>
              </div>
              <Button variant="ghost" size="sm">
                Ver todos
              </Button>
            </div>

            <div className={styles.claimList}>
              {claims.map((claim) => (
                <article className={styles.claim} key={claim.id}>
                  <span className={styles.claimIcon} aria-hidden="true">
                    {claim.tone === 'danger' ? <AlertTriangle /> : <Wrench />}
                  </span>
                  <div className={styles.claimCopy}>
                    <div className={styles.claimMeta}>
                      <span>{claim.id}</span>
                      <StatusBadge tone={claim.tone}>{claim.status}</StatusBadge>
                    </div>
                    <h3>{claim.title}</h3>
                    <p>{claim.address}</p>
                  </div>
                  <IconButton
                    label={'Abrir ' + claim.id}
                    variant="secondary"
                  >
                    <ArrowUpRight />
                  </IconButton>
                </article>
              ))}
            </div>
          </section>

          <aside className={styles.panel} aria-labelledby="components-title">
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.sectionEyebrow}>Componentes base</p>
                <h2 id="components-title">Estados consistentes</h2>
              </div>
            </div>

            <div className={styles.badges} aria-label="Ejemplos de estados">
              <StatusBadge tone="success">Resuelto</StatusBadge>
              <StatusBadge tone="info">En proceso</StatusBadge>
              <StatusBadge tone="warning">Pendiente</StatusBadge>
              <StatusBadge tone="danger">Urgente</StatusBadge>
            </div>

            <FormField
              hint="Ejemplo de etiqueta y ayuda visibles."
              id="preview-observation"
              label="Observación interna"
            >
              <input
                className={styles.textInput}
                placeholder="Agregar contexto para el equipo"
                type="text"
              />
            </FormField>

            <div className={styles.buttonRow}>
              <Button size="sm">Guardar</Button>
              <Button size="sm" variant="secondary">
                Cancelar
              </Button>
            </div>
          </aside>
        </div>

        <section className={styles.feedback} aria-label="Estados de contenido">
          <EmptyState
            action={<Button variant="secondary">Crear primer registro</Button>}
            description="Usar este estado cuando la consulta fue correcta pero todavía no existen datos."
            title="Sin resultados para mostrar"
          />
          <LoadingState label="Cargando reclamos de ejemplo" lines={4} />
        </section>
      </PageContainer>
    </>
  )
}

export default DesignSystemPreview
