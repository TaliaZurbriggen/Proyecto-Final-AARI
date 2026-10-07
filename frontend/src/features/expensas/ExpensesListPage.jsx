import { useCallback, useState } from 'react'
import { ClipboardList, FilterX, RefreshCw } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, FormField, LoadingState, SelectInput, StatusBadge, TextInput } from '../../components/ui/index.js'
import { useAuth } from '../auth/authContext.js'
import { useHistoryResource } from '../reclamos/useHistoryResource.js'
import { claimPropertyLabel } from '../reclamos/validation.js'
import { formatClaimDate, formatClaimNumber } from '../reclamos/presentation.js'
import AgencyEmailSettings from './AgencyEmailSettings.jsx'
import { deliveryLabels, deliveryTone, listExpenses } from './api.js'
import styles from './Expensas.module.css'

export default function ExpensesListPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [revision, setRevision] = useState(0)
  const rawPage = Number(params.get('page') || 1)
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1
  const situation = params.get('situacion') || 'derivados'
  const propertyId = params.get('propiedad_id') || ''
  const from = params.get('fecha_desde') || ''
  const until = params.get('fecha_hasta') || ''
  const query = new URLSearchParams({ page: String(page), situacion: situation })
  if (propertyId) query.set('propiedad_id', propertyId)
  if (from) query.set('fecha_desde', from)
  if (until) query.set('fecha_hasta', until)
  const queryString = query.toString()
  const failuresQuery = new URLSearchParams(queryString)
  failuresQuery.set('page', '1')
  failuresQuery.set('situacion', 'fallidos')
  const failuresLink = `/expensas?${failuresQuery.toString()}`
  const dateError = from && until && from > until ? 'La fecha desde no puede ser posterior a la fecha hasta.' : ''
  const load = useCallback((signal) => listExpenses(queryString, { signal }), [queryString])
  const { data, error, isLoading } = useHistoryResource(`${queryString}:${revision}`, load, !dateError)
  const change = (name, value) => {
    const next = new URLSearchParams(params)
    if (value) next.set(name, value)
    else next.delete(name)
    next.delete('page')
    setParams(next, { replace: true })
  }
  const paginate = (value) => {
    const next = new URLSearchParams(params)
    next.set('page', String(value))
    setParams(next)
  }
  return (
    <PageContainer>
      <PageHeading eyebrow="Gestión de la inmobiliaria" title="Expensas"
        description="Evaluá los reclamos derivados y revisá los reportes que todavía no pudieron enviarse."
        action={<Button variant="secondary" leadingIcon={<RefreshCw />} disabled={isLoading} onClick={() => setRevision((value) => value + 1)}>Actualizar</Button>} />
      {user?.rol === 'administrador' ? <AgencyEmailSettings /> : null}
      <section className={styles.filters} aria-label="Filtros de expensas">
        <FormField id="expense-situation" label="Situación del reporte">
          <SelectInput value={situation} onChange={(event) => change('situacion', event.target.value)}>
            <option value="derivados">Derivados a inmobiliaria</option>
            <option value="pendientes">Pendientes de envío</option>
            <option value="fallidos">Fallos o configuración pendiente</option>
            <option value="historicos">Históricos sin reporte HU14</option>
            <option value="todos">Todas las expensas</option>
          </SelectInput>
        </FormField>
        <FormField id="expense-property" label="Propiedad">
          <SelectInput value={propertyId} onChange={(event) => change('propiedad_id', event.target.value)}>
            <option value="">Todas las propiedades</option>
            {!data && propertyId ? <option value={propertyId}>Propiedad seleccionada</option> : null}
            {data?.propiedades.map((property) => <option value={property.id} key={property.id}>{claimPropertyLabel(property)}</option>)}
          </SelectInput>
        </FormField>
        <FormField id="expense-from" label="Fecha de ingreso desde">
          <TextInput type="date" value={from} onChange={(event) => change('fecha_desde', event.target.value)} />
        </FormField>
        <FormField id="expense-until" label="Fecha de ingreso hasta" error={dateError}>
          <TextInput type="date" value={until} onChange={(event) => change('fecha_hasta', event.target.value)} />
        </FormField>
        <Button variant="secondary" leadingIcon={<FilterX />} onClick={() => setParams({})}
          disabled={!propertyId && !from && !until && situation === 'derivados'}>Limpiar filtros</Button>
      </section>
      {error ? <AlertMessage>{error}</AlertMessage> : null}
      {isLoading ? <LoadingState label="Cargando expensas" lines={5} /> : null}
      {data ? <>
        {data.fallidos || data.sin_configuracion ? <AlertMessage>
          Reportes que agotaron los tres intentos: {data.fallidos}. Sin destinatario válido: {data.sin_configuracion}.
          {' '}<Link to={failuresLink}>Revisar reportes no enviados</Link>
        </AlertMessage> : null}
        {data.pendientes ? <p className={styles.notice} role="status">Reportes pendientes de envío: {data.pendientes}. La derivación se confirma después de registrar la aceptación de SMTP.</p> : null}
        <section className={styles.panel} aria-label="Reclamos de expensa">
          <div className={styles.summary}><h2>Resultados</h2><p role="status">{data.total} {data.total === 1 ? 'expensa' : 'expensas'} · 20 por página</p></div>
          {data.items.length ? <div className={styles.tableRegion}>
            <table className={styles.table}>
              <caption className="aari-sr-only">Expensas ordenadas del ingreso más reciente al más antiguo</caption>
              <thead><tr><th scope="col">Número</th><th scope="col">Unidad</th><th scope="col">Estado del reclamo</th><th scope="col">Reporte</th><th scope="col">Ingreso</th></tr></thead>
              <tbody>{data.items.map((claim) => <tr key={claim.id}>
                <td data-label="Número"><Link className={styles.link} aria-label={`Ver expensa ${formatClaimNumber(claim.numero)}`} to={`/expensas/${claim.id}?${queryString}`}>{formatClaimNumber(claim.numero)}</Link></td>
                <td data-label="Unidad"><p>{claimPropertyLabel(claim.propiedad)}</p><p className={styles.description}>{claim.descripcion}</p></td>
                <td data-label="Estado del reclamo">{claim.estado}</td>
                <td data-label="Reporte"><StatusBadge tone={deliveryTone(claim.entrega_estado)}>{deliveryLabels[claim.entrega_estado]}</StatusBadge><p>{claim.intentos}/3 intentos</p></td>
                <td data-label="Ingreso"><time dateTime={claim.creado_en}>{formatClaimDate(claim.creado_en, { short: true })}</time></td>
              </tr>)}</tbody>
            </table>
          </div> : <EmptyState icon={ClipboardList} title="No hay expensas en esta vista"
            description="Probá otra situación o limpiá los filtros. Los reportes fallidos permanecen disponibles para revisión."
            action={page > 1 ? <Button variant="secondary" onClick={() => paginate(1)}>Volver a la primera página</Button> : null} />}
          {data.total_pages > 1 || page > 1 ? <nav className={styles.pagination} aria-label="Paginación de expensas">
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => paginate(Math.min(page - 1, data.total_pages))}>Anterior</Button>
            <span>Página {page} de {data.total_pages}</span>
            <Button variant="secondary" size="sm" disabled={page >= data.total_pages} onClick={() => paginate(page + 1)}>Siguiente</Button>
          </nav> : null}
        </section>
      </> : null}
    </PageContainer>
  )
}
