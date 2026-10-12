import { useCallback, useRef, useState } from 'react'
import { ArrowLeft, RefreshCw, Search, Wrench } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, FormField, LoadingState, SelectInput } from '../../../components/ui/index.js'
import { getCandidateSpecialties, getProviderCandidates, searchProviderCandidates } from '../api/providerCandidatesApi.js'
import { assignmentReturnQuery, candidateOutcome, operatorAlert, positivePage } from '../providerCandidates.js'
import { formatClaimDate, formatClaimNumber } from '../presentation.js'
import { claimPropertyLabel } from '../validation.js'
import { useHistoryResource } from '../useHistoryResource.js'
import shared from './Escalados.module.css'
import styles from './ProviderCandidates.module.css'

function SearchForm({ claim, specialties, onSaved }) {
  const [specialty, setSpecialty] = useState(claim.especialidad?.id || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fieldError, setFieldError] = useState('')
  const attempt = useRef(null)
  const submit = async (event) => {
    event.preventDefault()
    if (saving) return
    if (!specialty) { setFieldError('Seleccioná la especialidad requerida.'); return }
    const key = `${specialty}:${claim.updated_at}`
    if (attempt.current?.key !== key) attempt.current = { key, id: crypto.randomUUID() }
    setSaving(true)
    setError('')
    setFieldError('')
    try {
      const result = await searchProviderCandidates(claim.id, {
        request_id: attempt.current.id, expected_updated_at: claim.updated_at, especialidad_id: specialty,
      })
      onSaved(result)
    } catch (failure) {
      if (failure.body?.detail?.field === 'especialidad_id') setFieldError(failure.message)
      else setError(failure.message)
    } finally { setSaving(false) }
  }
  return <form className={styles.searchForm} onSubmit={submit} noValidate>
    <FormField id="candidate-specialty" label="Especialidad requerida" required error={fieldError}
      hint="Este dato no modifica quién paga el reclamo.">
      <SelectInput value={specialty} disabled={saving || !claim.puede_buscar}
        onChange={(event) => { setSpecialty(event.target.value); setFieldError('') }}>
        <option value="">Seleccionar especialidad</option>
        {specialties.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}
      </SelectInput>
    </FormField>
    <Button type="submit" leadingIcon={<Search />} disabled={saving || !claim.puede_buscar}>
      {saving ? 'Registrando búsqueda…' : 'Guardar especialidad y buscar'}
    </Button>
    {error ? <div className={styles.formError}><AlertMessage>{error}</AlertMessage></div> : null}
  </form>
}

function ProviderCandidatesPage({ operatorView = false }) {
  const { reclamoId } = useParams()
  const [params, setParams] = useSearchParams()
  const [refresh, setRefresh] = useState(0)
  const [notice, setNotice] = useState(null)
  const page = positivePage(params.get('cpage'))
  const auditPage = positivePage(params.get('apage'))
  const query = new URLSearchParams({ page: String(page), audit_page: String(auditPage) }).toString()
  const base = operatorView ? '/operador/pendientes-asignacion' : '/pendientes-asignacion'
  const load = useCallback(async (signal) => {
    const [claim, specialties] = await Promise.all([
      getProviderCandidates(reclamoId, query, { signal }), getCandidateSpecialties({ signal }),
    ])
    return { claim, specialties }
  }, [reclamoId, query])
  const { data, error, isLoading } = useHistoryResource(`${reclamoId}:${query}:${refresh}`, load)
  const claim = data?.claim
  const movePage = (name, value) => {
    const next = new URLSearchParams(params); next.set(name, String(value)); setParams(next)
  }
  const saved = (result) => {
    setNotice({ ...result, reclamoId })
    const next = new URLSearchParams(params); next.delete('cpage'); next.delete('apage'); setParams(next, { replace: true })
    setRefresh((value) => value + 1)
  }
  return <PageContainer className={shared.detailPage}>
    <Link className={shared.backLink} to={`${base}?${assignmentReturnQuery(params)}`}>
      <ArrowLeft aria-hidden="true" />Volver a pendientes de asignación
    </Link>
    <PageHeading eyebrow="Coordinación de proveedores" title={claim ? `Proveedores para ${formatClaimNumber(claim.numero)}` : 'Proveedores candidatos'}
      description="El agente busca especialidad y cobertura compatibles desde el reclamo. El presupuesto y la visita se confirman después."
      action={<Button variant="secondary" leadingIcon={<RefreshCw />} disabled={isLoading}
        onClick={() => setRefresh((value) => value + 1)}>Actualizar</Button>} />
    {error ? <AlertMessage>{error}</AlertMessage> : null}
    {isLoading ? <LoadingState label="Cargando proveedores candidatos" lines={5} /> : null}
    {claim && !error ? <div className={styles.sections}>
      {notice?.reclamoId === reclamoId ? <AlertMessage tone={notice.resultado === 'candidatos_encontrados' ? 'success' : 'warning'}>
        {candidateOutcome[notice.resultado]}. {operatorAlert[notice.aviso_operador]}
      </AlertMessage> : null}
      <section className={shared.panel}>
        <div className={shared.panelHeading}><h2>Reclamo y especialidad</h2><span>{claim.estado}</span></div>
        <div className={shared.panelBody}>
          <p className={shared.fullDescription}>{claim.descripcion}</p>
          <p>{claimPropertyLabel(claim.propiedad)}</p>
          <AlertMessage tone={claim.tarea_agente === 'revision' ? 'warning' : 'info'}>
            {claim.tarea_agente === 'procesando' ? 'El agente está identificando la especialidad y buscando proveedores. Actualizá para ver el resultado.'
              : claim.tarea_agente === 'pendiente' ? 'La búsqueda automática está pendiente de procesamiento.'
              : claim.tarea_agente === 'completada' ? 'El agente completó la búsqueda. Los candidatos son preliminares: no están contratados ni tienen un turno confirmado.'
              : claim.tarea_agente === 'revision' ? `La búsqueda necesita revisión. ${claim.motivo_agente || ''}`
              : claim.tarea_agente === 'cancelada' ? 'Se descartó un resultado porque cambió el reclamo. Actualizá para consultar el nuevo intento.'
              : 'Todavía no se ejecutó una búsqueda automática. Su activación requiere configurar el procesador en el backend.'}
          </AlertMessage>
          <p>Especialidad: <strong>{claim.especialidad?.nombre || 'Pendiente de identificar'}</strong></p>
          {!claim.puede_buscar ? <AlertMessage tone="warning">El reclamo está cerrado o salió de este circuito. Sólo podés consultar sus candidatos.</AlertMessage> : null}
          <details open={!claim.especialidad && (!claim.tarea_agente || claim.tarea_agente === 'revision')}>
            <summary>Corregir especialidad o repetir búsqueda</summary>
            <p className={shared.hint}>Intervención de la inmobiliaria. No modifica quién paga ni autoriza la contratación.</p>
            <SearchForm key={claim.updated_at} claim={claim} specialties={data.specialties} onSaved={saved} />
          </details>
          {!claim.propiedad.barrio ? <p className={shared.hint}>Sin barrio informado: sólo se incluyen proveedores que cubren toda la localidad.</p> : null}
        </div>
      </section>
      <section className={shared.panel} aria-label="Proveedores compatibles">
        <div className={shared.panelHeading}><h2>Candidatos actuales</h2><span>{claim.total} proveedores</span></div>
        <div className={shared.panelBody}>
          <p className={shared.hint}>Cobertura compatible no significa disponibilidad confirmada. Esta consulta no envía WhatsApp ni selecciona un proveedor.</p>
          {claim.candidatos.length ? <div className={styles.candidates}>{claim.candidatos.map((provider) => <article className={styles.candidate} key={provider.id}>
            <h3>{provider.nombre_razon_social}</h3>
            <p>{provider.especialidades.map((item) => item.nombre).join(' · ')}</p>
            <p>Contacto: {provider.telefono}</p>
            <p>Horario habitual: {provider.hora_inicio && provider.hora_fin ? `${provider.hora_inicio.slice(0, 5)} a ${provider.hora_fin.slice(0, 5)}` : 'No informado'}</p>
            <p>Cubre la ubicación de esta propiedad.</p>
          </article>)}</div> : <EmptyState icon={Wrench}
            title={claim.total && page > 1 ? 'No hay candidatos en esta página' : candidateOutcome[claim.resultado]}
            description={claim.resultado === 'sin_candidatos' ? 'Revisá la cobertura y especialidad del padrón o incorporá un proveedor compatible.' : 'Completá los datos necesarios para poder continuar.'} />}
          {claim.total_pages > 1 || page > 1 ? <nav className={shared.pagination} aria-label="Paginación de candidatos">
            <Button variant="secondary" disabled={page <= 1} onClick={() => movePage('cpage', Math.max(1, Math.min(page-1, claim.total_pages)))}>Anterior</Button>
            <span>Página {page} de {claim.total_pages}</span>
            <Button variant="secondary" disabled={page >= claim.total_pages} onClick={() => movePage('cpage', page+1)}>Siguiente</Button>
          </nav> : null}
        </div>
      </section>
      <section className={shared.panel} aria-label="Historial de búsquedas">
        <div className={shared.panelHeading}><h2>Búsquedas registradas</h2><span>{claim.historial_total} intentos</span></div>
        <div className={shared.panelBody}>
          {claim.historial_busquedas.length ? <ol className={shared.timeline}>{claim.historial_busquedas.map((audit) => <li key={audit.id}>
            <strong>{candidateOutcome[audit.resultado]} · {audit.candidato_ids.length} candidatos</strong>
            <time dateTime={audit.buscado_en}>{formatClaimDate(audit.buscado_en)}</time>
            <small>Origen: {audit.origen}. {operatorAlert[audit.aviso_operador]}</small>
            <details className={shared.audit}><summary>Ver criterios e identificadores</summary>
              <p>{audit.provincia || 'Sin provincia'} · {audit.localidad || 'Sin localidad'} · {audit.barrio || 'Toda la localidad'}</p>
              <p>Especialidad: {audit.especialidad_id || 'Pendiente'}</p>
              <p>Responsable del registro: {audit.usuario_id || 'Agente'}</p>
              <p>Proveedores: {audit.candidato_ids.join(', ') || 'Ninguno'}</p>
            </details>
          </li>)}</ol> : <p>Todavía no hay búsquedas registradas. Abrir esta pantalla no registra un intento.</p>}
          {claim.historial_total > 10 || auditPage > 1 ? <nav className={shared.pagination} aria-label="Paginación de auditoría">
            <Button variant="secondary" disabled={auditPage <= 1} onClick={() => movePage('apage', auditPage-1)}>Más recientes</Button>
            <span>Página {auditPage} de {Math.max(1, Math.ceil(claim.historial_total / 10))}</span>
            <Button variant="secondary" disabled={auditPage * 10 >= claim.historial_total} onClick={() => movePage('apage', auditPage+1)}>Más antiguas</Button>
          </nav> : null}
        </div>
      </section>
    </div> : null}
  </PageContainer>
}

export default ProviderCandidatesPage
