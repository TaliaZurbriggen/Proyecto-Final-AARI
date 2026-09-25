import { useEffect, useState } from 'react'
import { Check, Pencil, RotateCw, Sparkles, X } from 'lucide-react'
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
  operativa: 'Puede aportar al clasificador',
  contexto: 'Sólo contexto para revisión',
  excluir: 'Excluir del clasificador',
}

function Badge({ state }) {
  const [label, tone] = stateLabels[state] ?? [state, 'neutral']
  return <StatusBadge tone={tone}>{label}</StatusBadge>
}

function ClauseEditor({ clause, busy, onCancel, onSave }) {
  const [values, setValues] = useState({
    resumen: clause.resumen, categoria: clause.categoria,
    responsable: clause.responsable, condiciones: clause.condiciones ?? '',
    uso_clasificador: clause.uso_clasificador ?? 'operativa',
  })
  const update = (field) => (event) => setValues(current => ({ ...current, [field]: event.target.value }))
  return <form className={styles.editor} onSubmit={event => { event.preventDefault(); onSave(values) }}>
    <FormField id={`summary-${clause.id}`} label="Resumen" required>
      <textarea className={styles.textarea} value={values.resumen} onChange={update('resumen')} />
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
      <FormField id={`usage-${clause.id}`} label="Uso en reclamos" required>
        <SelectInput value={values.uso_clasificador} onChange={update('uso_clasificador')}>
          {Object.entries(usageLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectInput>
      </FormField>
    </div>
    <FormField id={`conditions-${clause.id}`} label="Condiciones o excepciones" hint="Dejalo vacío solamente si el texto no establece condiciones.">
      <textarea className={styles.textarea} value={values.condiciones} onChange={update('condiciones')} />
    </FormField>
    <div className={styles.actions}>
      <Button variant="secondary" disabled={busy} onClick={onCancel}>Cancelar</Button>
      <Button type="submit" disabled={busy}>{busy ? 'Guardando…' : 'Guardar y confirmar'}</Button>
    </div>
  </form>
}

function ClauseCard({ clause, busy, editing, onEdit, onReview }) {
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
        <p className={styles.label}>Propuesta para revisión</p>
        <p>{clause.resumen}</p>
        <dl><div><dt>Categoría</dt><dd>{categoryLabels[clause.categoria]}</dd></div><div><dt>Responsable</dt><dd>{responsibleLabels[clause.responsable]}</dd></div><div><dt>Uso</dt><dd>{usageLabels[clause.uso_clasificador ?? 'operativa']}</dd></div></dl>
        {clause.condiciones && <p className={styles.conditions}><strong>Condiciones:</strong> {clause.condiciones}</p>}
      </div>
    </div>
    {editing ? <ClauseEditor clause={clause} busy={busy} onCancel={() => onEdit('')} onSave={values => onReview(clause, 'editar', values)} /> : clause.estado_revision === 'pendiente' && <div className={styles.actions}>
      <Button variant="secondary" disabled={busy} leadingIcon={<X />} onClick={() => onReview(clause, 'descartar')}>Descartar</Button>
      <Button variant="secondary" disabled={busy} leadingIcon={<Pencil />} onClick={() => onEdit(clause.id)}>Editar</Button>
      <Button disabled={busy} leadingIcon={<Check />} onClick={() => onReview(clause, 'confirmar')}>Confirmar</Button>
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

export default function ContractClausesPanel({ contractId, document }) {
  const [analysis, setAnalysis] = useState(undefined)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [editing, setEditing] = useState('')

  const load = (signal) => getContractAnalysis(contractId, document.id, { signal })
    .then(setAnalysis).catch(err => { if (!signal?.aborted) setError(err.message) })

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

  const start = async () => {
    setBusy('start'); setError('')
    try { setAnalysis(await startContractAnalysis(contractId, document.id)) }
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
    <div className={styles.heading}><div><h2>Cláusulas del contrato</h2><p>Versión {document.version} · revisión obligatoria antes de usar el contexto</p></div>{analysis && <Badge state={analysis.estado} />}</div>
    <div className={styles.body}>
      {error && <AlertMessage>{error}</AlertMessage>}
      {analysis === undefined ? <LoadingState label="Cargando análisis" /> : !analysis ? <div className={styles.empty}>
        <Sparkles aria-hidden="true" /><div><h3>Este documento todavía no fue analizado</h3><p>La IA propondrá cláusulas; ninguna se aplicará sin tu confirmación.</p></div>
        <Button disabled={Boolean(busy)} leadingIcon={<Sparkles />} onClick={start}>{busy ? 'Preparando…' : 'Analizar cláusulas'}</Button>
      </div> : <>
        {['pendiente', 'procesando'].includes(analysis.estado) && <LoadingState label="Analizando el contrato. Podés seguir usando AARI" />}
        {analysis.ultimo_error && <AlertMessage tone={analysis.estado === 'incompleto' ? 'warning' : 'danger'}>{analysis.ultimo_error}</AlertMessage>}
        {analysis.estado === 'fallido' && <div className={styles.actions}><Button disabled={Boolean(busy)} leadingIcon={<RotateCw />} onClick={start}>{busy ? 'Preparando…' : 'Reintentar análisis'}</Button></div>}
        {analysis.estado === 'incompleto' && <div className={styles.actions}><Button disabled={Boolean(busy)} variant="secondary" leadingIcon={<RotateCw />} onClick={start}>{busy ? 'Preparando…' : 'Reintentar lectura'}</Button></div>}
        {['completado', 'incompleto'].includes(analysis.estado) && !analysis.clausulas.length && !(analysis.propuestas_rechazadas?.length) && <p className={styles.muted}>No se encontraron cláusulas operativas. Revisá el PDF antes de dar por finalizada la lectura.</p>}
        {analysis.clausulas.length > 0 && <div className={styles.list}>{analysis.clausulas.map(clause => <ClauseCard key={clause.id} clause={clause} busy={busy === clause.id} editing={editing === clause.id} onEdit={setEditing} onReview={review} />)}</div>}
        {analysis.propuestas_rechazadas?.length > 0 && <section className={styles.rejectedSection} aria-label="Propuestas con evidencia rechazada">
          <div><h3>Propuestas que requieren auditoría</h3><p>No se usarán en reclamos. Se conservan para comparar con el PDF y mejorar la extracción.</p></div>
          <div className={styles.list}>{analysis.propuestas_rechazadas.map(rejected => <RejectedCard key={rejected.ordinal} rejected={rejected} />)}</div>
        </section>}
      </>}
    </div>
  </section>
}
