import { useEffect, useState } from 'react'
import { Check, FileText, Pencil, RotateCw, Sparkles, X } from 'lucide-react'
import { AlertMessage, Button, FormField, LoadingState, SelectInput, StatusBadge } from '../../../components/ui/index.js'
import { getContractAnalysis, reviewContractClause, startContractAnalysis } from '../api/contratosApi.js'
import styles from './ContractClausesPanel.module.css'

const stateLabels = {
  pendiente: ['Pendiente', 'neutral'], procesando: ['Analizando', 'info'],
  completado: ['Completo', 'success'], incompleto: ['Revisar lectura', 'warning'],
  fallido: ['Falló', 'danger'], confirmada: ['Confirmada', 'success'],
  editada: ['Editada', 'success'], descartada: ['Descartada', 'neutral'],
}
const categoryLabels = {
  reparacion: 'Reparación', mantenimiento: 'Mantenimiento', danio: 'Daño',
  servicio: 'Servicio', expensa: 'Expensa', aviso: 'Aviso', acceso: 'Acceso',
  devolucion: 'Devolución', otro: 'Otro',
}
const responsibleLabels = {
  inquilino: 'Inquilino', propietario: 'Propietario', administracion: 'Administración',
  condicional: 'Depende de una condición', no_especificado: 'No especificado',
}
const usageLabels = {
  operativa: 'Habilitada para reclamos',
  contexto: 'Sólo contexto para revisión',
  excluir: 'Excluir del clasificador',
}

function Badge({ state }) {
  const [label, tone] = stateLabels[state] ?? [state, 'neutral']
  return <StatusBadge tone={tone}>{label}</StatusBadge>
}

function ClauseEditor({ clause, busy, onCancel, onSave }) {
  const [summaryError, setSummaryError] = useState('')
  const [values, setValues] = useState({
    resumen: clause.origen === 'literal' && clause.estado_revision === 'pendiente' ? '' : clause.resumen, categoria: clause.categoria,
    responsable: clause.responsable, condiciones: clause.condiciones ?? '',
    uso_clasificador: clause.habilitada_para_reclamos
      ? 'operativa' : clause.uso_clasificador === 'excluir' ? 'excluir' : 'contexto',
  })
  const update = (field) => (event) => {
    if (field === 'resumen') setSummaryError('')
    setValues(current => ({ ...current, [field]: event.target.value }))
  }
  return <form className={styles.editor} onSubmit={event => {
    event.preventDefault()
    if (!values.resumen.trim()) { setSummaryError('Completá el resumen de la cláusula.'); return }
    onSave({ ...values, resumen: values.resumen.trim(), condiciones: values.condiciones.trim() })
  }}>
    <FormField id={`summary-${clause.id}`} label="Resumen" required error={summaryError}>
      <textarea required maxLength={1200} className={styles.textarea} value={values.resumen} onChange={update('resumen')} />
    </FormField>
    <div className={styles.formGrid}>
      <FormField id={`category-${clause.id}`} label="Categoría" required>
        <SelectInput value={values.categoria} onChange={update('categoria')}>
          {Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectInput>
      </FormField>
      <FormField id={`responsible-${clause.id}`} label="Responsable indicado" required>
        <SelectInput value={values.responsable} onChange={update('responsable')}>
          {Object.entries(responsibleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectInput>
      </FormField>
      <FormField id={`usage-${clause.id}`} label="Uso en reclamos" required hint="Sólo una edición que seleccione 'Puede aportar al clasificador' habilita esta regla para reclamos.">
        <SelectInput value={values.uso_clasificador} onChange={update('uso_clasificador')}>
          <option value="contexto">Sólo contexto para revisión</option>
          <option value="operativa">Puede aportar al clasificador</option>
          <option value="excluir">Excluir del clasificador</option>
        </SelectInput>
      </FormField>
    </div>
    <FormField id={`conditions-${clause.id}`} label="Condiciones o excepciones" hint="Dejalo vacío solamente si el texto no establece condiciones.">
      <textarea maxLength={1600} className={styles.textarea} value={values.condiciones} onChange={update('condiciones')} />
    </FormField>
    {values.uso_clasificador === 'operativa' && <AlertMessage tone="warning">Compará la interpretación y las excepciones con el PDF antes de habilitarla para reclamos.</AlertMessage>}
    <div className={styles.actions}>
      <Button variant="secondary" disabled={busy} onClick={onCancel}>Cancelar</Button>
      <Button type="submit" disabled={busy}>{busy ? 'Guardando…' : values.uso_clasificador === 'operativa' ? 'Guardar y habilitar' : 'Guardar revisión'}</Button>
    </div>
  </form>
}

function ClauseCard({ clause, busy, editing, onEdit, onReview }) {
  const visibleUsage = clause.habilitada_para_reclamos
    ? 'operativa' : clause.uso_clasificador === 'excluir' ? 'excluir' : 'contexto'
  const evidences = clause.evidencias?.length
    ? clause.evidencias
    : [{ pagina: null, texto: clause.texto_original }]
  return <article className={styles.clause}>
    <div className={styles.clauseHeading}>
      <div><p className={styles.eyebrow}>{clause.numero || `Cláusula ${clause.ordinal}`}</p><h3>{clause.titulo || categoryLabels[clause.categoria]}</h3></div>
      <Badge state={clause.estado_revision} />
    </div>
    <div className={styles.clauseGrid}>
      <div className={styles.evidence}>
        <p className={styles.label}>Evidencia literal</p>
        {evidences.map((evidence, index) => <div className={styles.evidenceItem} key={`${evidence.pagina ?? 'legacy'}-${index}`}>
          <span>{evidence.pagina ? `Página ${evidence.pagina}` : clause.paginas.length === 1 ? `Página ${clause.paginas[0]}` : `Páginas ${clause.paginas.join(', ')}`}</span>
          <blockquote>{evidence.texto}</blockquote>
        </div>)}
      </div>
      <div className={styles.interpretation}>
        <p className={styles.label}>{clause.origen === 'literal' ? clause.estado_revision === 'editada' ? 'Interpretación revisada de extracción literal' : 'Extracción literal · interpretación pendiente' : 'Propuesta de IA para revisión'}</p>
        <p>{clause.resumen}</p>
        <dl><div><dt>Categoría</dt><dd>{categoryLabels[clause.categoria]}</dd></div><div><dt>Responsable</dt><dd>{responsibleLabels[clause.responsable]}</dd></div><div><dt>Uso actual</dt><dd>{usageLabels[visibleUsage]}</dd></div></dl>
        {clause.condiciones && <p className={styles.conditions}><strong>Condiciones:</strong> {clause.condiciones}</p>}
      </div>
    </div>
    {editing ? <ClauseEditor clause={clause} busy={busy} onCancel={() => onEdit('')} onSave={values => onReview(clause, 'editar', values)} /> : clause.estado_revision !== 'descartada' && <div className={styles.actions}>
      {clause.estado_revision === 'pendiente' && <Button variant="secondary" disabled={busy} leadingIcon={<X />} onClick={() => onReview(clause, 'descartar')}>Descartar</Button>}
      <Button variant="secondary" disabled={busy} leadingIcon={<Pencil />} onClick={() => onEdit(clause.id)}>{clause.estado_revision === 'pendiente' ? 'Editar' : 'Editar revisión'}</Button>
      {clause.estado_revision === 'pendiente' && <Button disabled={busy} leadingIcon={<Check />} onClick={() => onReview(clause, 'confirmar')}>Confirmar como contexto</Button>}
    </div>}
  </article>
}

function RejectedCard({ rejected }) {
  const clause = rejected.propuesta
  return <article className={`${styles.clause} ${styles.rejected}`}>
    <div className={styles.clauseHeading}>
      <div><p className={styles.eyebrow}>Propuesta {rejected.ordinal}</p><h3>{clause.titulo || clause.numero || 'Evidencia sin validar'}</h3></div>
      <StatusBadge tone="warning">Requiere revisión de evidencia</StatusBadge>
    </div>
    <AlertMessage tone="warning">{rejected.motivo}</AlertMessage>
    <div className={styles.evidence}>
      <p className={styles.label}>Fragmentos rechazados</p>
      {rejected.evidencias_invalidas.map((evidence, index) => <div className={styles.evidenceItem} key={`${evidence.pagina}-${index}`}>
        <span>Página declarada {evidence.pagina}</span>
        <blockquote>{evidence.texto}</blockquote>
      </div>)}
    </div>
    <p className={styles.muted}>Esta propuesta se conserva para auditoría, pero no puede confirmarse ni incorporarse al clasificador.</p>
  </article>
}

function ClausePanel({ contractId, document }) {
  const [analysis, setAnalysis] = useState(undefined)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [editing, setEditing] = useState('')

  const load = (signal) => getContractAnalysis(contractId, document.id, { signal })
    .then(value => { if (!signal?.aborted) setAnalysis(value) }).catch(err => { if (!signal?.aborted) setError(err.message) })

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [contractId, document.id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!['pendiente', 'procesando'].includes(analysis?.estado)) return undefined
    const timer = window.setInterval(() => load(), 2000)
    return () => window.clearInterval(timer)
  }, [analysis?.estado]) // eslint-disable-line react-hooks/exhaustive-deps

  const start = async (mode = 'ia') => {
    setBusy('start'); setError('')
    try { setAnalysis(await startContractAnalysis(contractId, document.id, mode)) }
    catch (err) { setError(err.message) }
    finally { setBusy('') }
  }
  const review = async (clause, action, changes = {}) => {
    setBusy(clause.id); setError('')
    try {
      setAnalysis(await reviewContractClause(contractId, clause.id, { accion: action, revision: clause.revision, ...changes }))
      setEditing('')
    } catch (err) { setError(err.message) }
    finally { setBusy('') }
  }

  return <section className={styles.panel} aria-label="Cláusulas del contrato">
    <div className={styles.heading}><div><h2>Cláusulas del contrato</h2><p>Versión {document.version} · las propuestas no se usan como reglas sin una habilitación explícita</p></div>{analysis && <Badge state={analysis.estado} />}</div>
    <div className={styles.body}>
      {error && <AlertMessage>{error}</AlertMessage>}
      {analysis === undefined ? <LoadingState label="Cargando análisis" /> : !analysis ? <div className={styles.empty}>
        <Sparkles aria-hidden="true" /><div><h3>Este documento todavía no fue analizado</h3><p>La IA propondrá cláusulas como contexto. Para usarlas en reclamos, tendrás que editarlas y habilitarlas.</p></div>
        <div className={styles.actions}>
          <Button disabled={Boolean(busy)} variant="secondary" leadingIcon={<FileText />} onClick={() => start('literal')}>Extraer sin IA</Button>
          <Button disabled={Boolean(busy)} leadingIcon={<Sparkles />} onClick={() => start('ia')}>{busy ? 'Preparando…' : 'Analizar cláusulas'}</Button>
        </div>
      </div> : <>
        {['pendiente', 'procesando'].includes(analysis.estado) && <LoadingState label="Analizando el contrato. Podés seguir usando AARI" />}
        {analysis.ultimo_error && <AlertMessage tone={analysis.estado === 'incompleto' ? 'warning' : 'error'}>{analysis.ultimo_error}</AlertMessage>}
        {!['pendiente', 'procesando'].includes(analysis.estado) && <div className={styles.actions}>
          <Button disabled={Boolean(busy)} variant="secondary" leadingIcon={<FileText />} onClick={() => start('literal')}>Extraer sin IA</Button>
          {analysis.modo === 'literal' && !analysis.clausulas.some(clause => clause.estado_revision !== 'pendiente') && <Button disabled={Boolean(busy)} leadingIcon={<Sparkles />} onClick={() => start('ia')}>Proponer con IA</Button>}
          {['fallido', 'incompleto'].includes(analysis.estado) && <Button disabled={Boolean(busy) || (analysis.modo !== 'literal' && analysis.clausulas.some(clause => clause.estado_revision !== 'pendiente'))} leadingIcon={<RotateCw />} onClick={() => start(analysis.modo ?? 'ia')}>{busy ? 'Preparando…' : analysis.modo === 'literal' ? 'Reintentar lectura' : 'Reintentar análisis'}</Button>}
        </div>}
        {analysis.modo === 'literal' && <p className={styles.muted}>Extracción local sin IA. No se interpretaron responsables ni obligaciones: completá la revisión comparando con el PDF.</p>}
        {['completado', 'incompleto'].includes(analysis.estado) && !analysis.clausulas.length && !(analysis.propuestas_rechazadas?.length) && <p className={styles.muted}>No se encontraron propuestas de cláusulas. Revisá el PDF antes de dar por finalizada la lectura.</p>}
        {analysis.clausulas.length > 0 && <div className={styles.list}>{analysis.clausulas.map(clause => <ClauseCard key={clause.id} clause={clause} busy={busy === clause.id} editing={editing === clause.id} onEdit={setEditing} onReview={review} />)}</div>}
        {analysis.propuestas_rechazadas?.length > 0 && <section className={styles.rejectedSection} aria-label="Propuestas con evidencia rechazada">
          <div><h3>Propuestas que requieren auditoría</h3><p>No se usarán en reclamos. Se conservan para comparar con el PDF y mejorar la extracción.</p></div>
          <div className={styles.list}>{analysis.propuestas_rechazadas.map((rejected, index) => <RejectedCard key={`${rejected.ordinal}-${index}`} rejected={rejected} />)}</div>
        </section>}
        {analysis.propuestas_fuente_rechazadas?.length > 0 && <section className={styles.rejectedSection} aria-label="Propuestas sin tramo verificable">
          <h3>Propuestas sin tramo verificable</h3>
          {analysis.propuestas_fuente_rechazadas.map((item, index) => <div key={index}><p>{item.propuesta?.resumen}</p><p className={styles.muted}>{item.motivo} No se incorpora al clasificador.</p></div>)}
        </section>}
        {analysis.historial_intentos?.length > 0 && <details><summary>Historial de intentos ({analysis.historial_intentos.length})</summary>
          <ul>{analysis.historial_intentos.map(attempt => <li key={attempt.id}>{attempt.modo === 'literal' ? 'Extracción local' : 'Análisis con IA'} · {stateLabels[attempt.estado]?.[0] ?? attempt.estado}{attempt.error ? ` · ${attempt.error}` : ''}</li>)}</ul>
        </details>}
      </>}
    </div>
  </section>
}

export default function ContractClausesPanel({ contractId, document }) {
  return <ClausePanel key={`${contractId}-${document.id}`} contractId={contractId} document={document} />
}
