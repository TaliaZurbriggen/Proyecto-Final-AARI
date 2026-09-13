import { useEffect, useState } from 'react'
import { ArrowLeft, Download, FileText, Upload } from 'lucide-react'
import { Link, useLocation, useParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, FormField, LoadingState, StatusBadge, TextInput } from '../../../components/ui/index.js'
import { useAuth } from '../../auth/authContext.js'
import { downloadContract, endContract, getContract, uploadContract } from '../api/contratosApi.js'
import { contractBase, contractTone, dateLabel, fileError } from '../validation.js'
import styles from './Contratos.module.css'

export default function ContractDetailPage() {
  const { contractId } = useParams()
  return <ContractDetail key={contractId} contractId={contractId} />
}

function ContractDetail({ contractId }) {
  const { user } = useAuth()
  const location = useLocation()
  const [result, setResult] = useState({ data: null, error: '', id: '' })
  const [error, setError] = useState(location.state?.uploadError ?? '')
  const [notice, setNotice] = useState(location.state?.notice ?? '')
  const [file, setFile] = useState(null)
  const [signed, setSigned] = useState(false)
  const [uploadKey, setUploadKey] = useState(0)
  const [busy, setBusy] = useState('')
  const [fileIssue, setFileIssue] = useState('')
  const [endDate, setEndDate] = useState('')
  const [endIssue, setEndIssue] = useState('')
  const [endConfirmed, setEndConfirmed] = useState(false)
  const admin = user.rol === 'administrador'
  const base = contractBase(user.rol)
  useEffect(() => {
    const controller = new AbortController()
    getContract(contractId, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult({ data, error: '', id: contractId }) })
      .catch(err => { if (!controller.signal.aborted) setResult({ data: null, error: err.message, id: contractId }) })
    return () => controller.abort()
  }, [contractId])
  const contract = result.data
  const saveFile = async event => {
    event.preventDefault()
    const issue = fileError(file, true)
    setFileIssue(issue)
    if (issue || busy) return
    setBusy('upload'); setError(''); setNotice('')
    try {
      const data = await uploadContract(contractId, { file, signed: signed || contract.estado === 'firmado', revision: contract.revision })
      setResult({ data, error: '', id: contractId }); setFile(null); setSigned(false); setUploadKey(key => key + 1)
      setNotice('La nueva versión del PDF se guardó. Las versiones anteriores se conservaron.')
    } catch (err) {
      if (err.body?.detail?.field === 'archivo') setFileIssue(err.message)
      else setError(err.message)
    } finally { setBusy('') }
  }
  const download = async documentId => {
    setBusy(documentId); setError('')
    try {
      const response = await downloadContract(contractId, documentId)
      // Enlace temporal privado. Supabase responde como descarga con este parámetro.
      const url = new URL(response.url)
      url.searchParams.set('download', '')
      window.location.assign(url.toString())
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }
  const finalize = async event => {
    event.preventDefault()
    if (busy || !endConfirmed) return
    setBusy('end'); setError(''); setNotice(''); setEndIssue('')
    try {
      const data = await endContract(contractId, { fecha_finalizacion: endDate, revision: contract.revision })
      setResult({ data, error: '', id: contractId }); setNotice('Se registró la finalización. El contrato y sus documentos permanecen en el historial.')
    } catch (err) {
      if (err.body?.detail?.field === 'fecha_finalizacion') setEndIssue(err.message)
      else setError(err.message)
    } finally { setBusy('') }
  }
  if (result.id !== contractId) return <PageContainer><LoadingState label="Cargando contrato" /></PageContainer>
  if (!contract) return <PageContainer><AlertMessage>{result.error}</AlertMessage></PageContainer>
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date())
  return <PageContainer>
    <Link to={base} className={styles.back}><ArrowLeft aria-hidden="true" />Volver a contratos</Link>
    <PageHeading eyebrow="Contrato de alquiler" title={contract.direccion} description={`${contract.localidad}, ${contract.provincia}`}
      action={<StatusBadge tone={contractTone(contract.vigencia)}>{contract.vigencia}</StatusBadge>} />
    <div className={styles.stack}>
      {notice && <AlertMessage tone="success">{notice}</AlertMessage>}
      {error && <AlertMessage>{error}</AlertMessage>}
      <section className={styles.panel} aria-label="Información del contrato">
        <div className={styles.panelHeading}><h2>Participantes y vigencia</h2>{admin && contract.estado === 'borrador' && <Link to={`/contratos/${contractId}/editar`}>Editar borrador</Link>}</div>
        <div className={styles.content}><dl className={styles.meta}>
          <div><dt>Inquilino</dt><dd>{contract.inquilino_nombre}</dd></div>
          <div><dt>Propietario al registrar el contrato</dt><dd>{contract.propietario_nombre}</dd></div>
          <div><dt>Inicio de vigencia</dt><dd>{dateLabel(contract.fecha_inicio)}</dd></div>
          <div><dt>Fin pactado</dt><dd>{dateLabel(contract.fecha_fin)}</dd></div>
          {contract.fecha_finalizacion && <div><dt>Finalización registrada</dt><dd>{dateLabel(contract.fecha_finalizacion)}</dd></div>}
        </dl>
        {contract.contrato_anterior_id && <Link to={`${base}/${contract.contrato_anterior_id}`}>Ver contrato anterior</Link>}
        </div>
      </section>
      <section className={styles.panel} aria-label="Documentos del contrato">
        <div className={styles.panelHeading}><h2>Documentos</h2><span className={styles.muted}>Acceso privado · historial de versiones</span></div>
        {contract.documentos.length ? <ul className={styles.documents}>{contract.documentos.map(doc => <li key={doc.id} className={styles.document}>
          <FileText className={styles.docIcon} aria-hidden="true" /><div className={styles.cardMain}>
            <strong>{doc.nombre_archivo}</strong><p className={styles.muted}>Versión {doc.version} · {dateLabel(doc.created_at)} · {(doc.tamano / 1024).toFixed(1)} KB</p>
          </div><StatusBadge tone={doc.firmado ? 'success' : 'neutral'}>{doc.firmado ? 'Firmado' : 'Borrador'}</StatusBadge>
          <Button leadingIcon={<Download aria-hidden="true" />} variant="secondary" disabled={Boolean(busy)} onClick={() => download(doc.id)} aria-label={`Descargar versión ${doc.version}`}>{busy === doc.id ? 'Preparando…' : 'Descargar'}</Button>
        </li>)}</ul> : <div className={styles.content}><p className={styles.muted}>Todavía no hay un PDF. Podés adjuntarlo cuando esté disponible.</p></div>}
        {admin && contract.estado !== 'finalizado' && <form onSubmit={saveFile}>
          <div className={styles.content}>
            <FormField id="new-contract-file" label={contract.documentos.length ? 'Agregar una versión' : 'Adjuntar documento'} error={fileIssue} hint="PDF sin contraseña, hasta 10 MB. No reemplaza ni elimina las versiones anteriores.">
              <input key={uploadKey} className={styles.file} type="file" accept=".pdf,application/pdf" onChange={event => setFile(event.target.files?.[0] ?? null)} />
            </FormField>
            {contract.estado === 'borrador' ? <div>
              <label className={styles.check}><input type="checkbox" checked={signed} onChange={event => setSigned(event.target.checked)} />Este PDF es el contrato firmado</label>
              <p className={styles.muted}>Confirmarlo habilita la consulta para el inquilino y el propietario. Las fechas quedan protegidas.</p>
            </div> : <p className={styles.muted}>Cargá una copia firmada. No se permite volver el contrato a borrador.</p>}
            <div className={styles.actions}><Button type="submit" disabled={Boolean(busy)} leadingIcon={<Upload aria-hidden="true" />}>{busy === 'upload' ? 'Cargando…' : 'Guardar PDF'}</Button></div>
          </div>
        </form>}
      </section>
      {admin && contract.estado !== 'borrador' && <section className={styles.panel}>
        <div className={styles.panelHeading}><h2>Continuidad del alquiler</h2></div>
        <div className={styles.content}><p className={styles.muted}>Una renovación crea otro registro con su propia vigencia y PDF. Este contrato permanece en el historial.</p><div><Link className={styles.primaryLink} to={`/contratos/nuevo?anterior=${contractId}`}>Registrar renovación</Link></div></div>
      </section>}
      {admin && contract.estado === 'firmado' && contract.fecha_inicio <= today && <section className={styles.panel}>
        <div className={styles.panelHeading}><h2>Registrar finalización</h2></div>
        <form className={styles.content} onSubmit={finalize}>
          <p className={styles.muted}>Usá esta opción si el alquiler terminó antes de la fecha pactada. No elimina documentos ni desasocia al inquilino automáticamente.</p>
          <div className={styles.grid}><FormField id="early-end" label="Fecha de finalización" required error={endIssue}>
            <TextInput type="date" min={contract.fecha_inicio} max={today < contract.fecha_fin ? today : contract.fecha_fin} value={endDate} onChange={event => setEndDate(event.target.value)} />
          </FormField></div>
          <label className={styles.check}><input type="checkbox" checked={endConfirmed} onChange={event => setEndConfirmed(event.target.checked)} />Confirmo que el contrato finalizó en la fecha indicada</label>
          <div className={styles.actions}><Button type="submit" variant="secondary" disabled={Boolean(busy) || !endDate || !endConfirmed}>{busy === 'end' ? 'Guardando…' : 'Registrar finalización'}</Button></div>
        </form>
      </section>}
    </div>
  </PageContainer>
}
