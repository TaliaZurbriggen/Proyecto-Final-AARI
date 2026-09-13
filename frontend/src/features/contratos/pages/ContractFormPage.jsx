import { useEffect, useState } from 'react'
import { ArrowLeft, Save } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, FormField, LoadingState, SearchInput, TextInput } from '../../../components/ui/index.js'
import { getInquilino, getPropertyTenant, listInquilinos } from '../../inquilinos/api/inquilinosApi.js'
import { createContract, getContract, updateContract, uploadContract } from '../api/contratosApi.js'
import { dateLabel, fileError, nextDay, validateDates } from '../validation.js'
import styles from './Contratos.module.css'

export default function ContractFormPage() {
  const { contractId } = useParams()
  const [params] = useSearchParams()
  return <ContractForm key={`${contractId ?? 'nuevo'}:${params}`} contractId={contractId} params={params} />
}

function ContractForm({ contractId, params }) {
  const navigate = useNavigate()
  const tenantId = params.get('inquilino_id')
  const propertyId = params.get('propiedad_id')
  const previousId = params.get('anterior')
  const [context, setContext] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [search, setSearch] = useState('')
  const [results, setResults] = useState({ items: [], total: 0, key: '' })
  const [dates, setDates] = useState({ fecha_inicio: '', fecha_fin: '' })
  const [file, setFile] = useState(null)
  const [signed, setSigned] = useState(false)
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      if (contractId || previousId) {
        const contract = await getContract(contractId || previousId, { signal: controller.signal })
        if (controller.signal.aborted) return
        if (contractId && contract.estado !== 'borrador') throw new Error('Solo se pueden editar las fechas de un borrador.')
        setContext(contract)
        setDates(contractId ? { fecha_inicio: contract.fecha_inicio, fecha_fin: contract.fecha_fin } : { fecha_inicio: nextDay(contract.fecha_finalizacion ?? contract.fecha_fin), fecha_fin: '' })
      } else if (tenantId || propertyId) {
        const selected = tenantId ? await getInquilino(tenantId, { signal: controller.signal }) : await getPropertyTenant(propertyId, { signal: controller.signal })
        if (!controller.signal.aborted) setTenant(selected)
      }
    }
    load().catch(err => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoaded(true) })
    return () => controller.abort()
  }, [contractId, previousId, tenantId, propertyId])

  useEffect(() => {
    if (tenant || context || !loaded) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      listInquilinos({ search, pageSize: 20, signal: controller.signal })
        .then(data => { if (!controller.signal.aborted) setResults({ ...data, key: search }) })
        .catch(err => { if (!controller.signal.aborted) setError(err.message) })
    }, 200)
    return () => { clearTimeout(timer); controller.abort() }
  }, [search, tenant, context, loaded])
  const selectedProperty = context?.propiedad_id ?? tenant?.propiedad?.id
  const submit = async event => {
    event.preventDefault()
    if (busy) return
    const nextErrors = validateDates(dates.fecha_inicio, dates.fecha_fin)
    if (!selectedProperty) nextErrors.inquilino_id = 'Elegí un inquilino que tenga una propiedad asignada.'
    const pdfError = fileError(file, signed)
    if (pdfError) nextErrors.archivo = pdfError
    if (previousId && context && dates.fecha_inicio <= (context.fecha_finalizacion ?? context.fecha_fin)) nextErrors.fecha_inicio = 'La renovación debe comenzar después del contrato anterior.'
    setErrors(nextErrors)
    setError('')
    if (Object.keys(nextErrors).length) return
    setBusy(true)
    let saved = null
    try {
      saved = contractId
        ? await updateContract(contractId, { ...dates, revision: context.revision })
        : await createContract({ ...dates, inquilino_id: context?.inquilino_id ?? tenant.id, propiedad_id: selectedProperty, contrato_anterior_id: previousId || null })
      if (file) saved = await uploadContract(saved.id, { file, signed, revision: saved.revision })
      navigate(`/contratos/${saved.id}`, { replace: true, state: { notice: file && signed ? 'El contrato firmado quedó guardado y disponible para sus participantes.' : 'El borrador se guardó. Podés completar el PDF firmado más adelante.' } })
    } catch (err) {
      if (saved) {
        navigate(`/contratos/${saved.id}`, { replace: true, state: { uploadError: `Los datos quedaron guardados, pero no se pudo cargar el PDF: ${err.message}. Reintentá desde Documentos.` } })
      } else {
        setError(err.message)
        if (err.body?.detail?.field) setErrors({ [err.body.detail.field]: err.message })
      }
    } finally { setBusy(false) }
  }
  if (!loaded) return <PageContainer><LoadingState label="Preparando contrato" /></PageContainer>
  if ((contractId || previousId) && !context) return <PageContainer><AlertMessage>{error || 'No se pudo cargar el contrato.'}</AlertMessage></PageContainer>
  return <PageContainer><div className={styles.center}>
    <Link className={styles.back} to={contractId ? `/contratos/${contractId}` : '/contratos'}><ArrowLeft aria-hidden="true" />Volver a contratos</Link>
    <PageHeading eyebrow="Administración" title={contractId ? 'Editar borrador' : previousId ? 'Renovar contrato' : 'Cargar contrato'} description="Registrá el alquiler y adjuntá el documento. La firma se realiza en el contrato, fuera de AARI." />
    <form noValidate onSubmit={submit} className={styles.panel}>
      <div className={styles.panelHeading}><h2>{previousId ? 'Nueva vigencia' : 'Datos del contrato'}</h2><span className={styles.muted}>Los campos con asterisco son obligatorios.</span></div>
      <div className={styles.content}>
        {error && <AlertMessage>{error}</AlertMessage>}
        {(context || tenant) ? <div className={styles.summary}>
          <strong>{context?.inquilino_nombre ?? tenant.nombre_completo}</strong>
          <p>{context?.direccion ?? tenant.propiedad?.direccion ?? 'Este inquilino no tiene una propiedad asignada.'}</p>
          {previousId && <p>Contrato anterior hasta el {dateLabel(context.fecha_finalizacion ?? context.fecha_fin)}. Se conservará en el historial.</p>}
          {!context && <Button variant="ghost" onClick={() => setTenant(null)}>Cambiar inquilino</Button>}
        </div> : <div className={styles.stack}>
          <FormField id="tenant-search" label="Buscar inquilino" required error={errors.inquilino_id} hint="Elegí una persona con propiedad asignada. Podés buscar por nombre o DNI.">
            <SearchInput placeholder="Nombre o DNI del inquilino" value={search} onChange={event => setSearch(event.target.value)} onClear={() => setSearch('')} />
          </FormField>
          <div className={styles.results} aria-label="Inquilinos disponibles">
            {results.key === search && results.items.map(item => <button key={item.id} className={styles.result} type="button" disabled={!item.propiedad} onClick={() => { setTenant(item); setErrors({}) }}>
              {item.nombre_completo}<small>{item.propiedad?.direccion ?? 'Sin propiedad asignada'}</small>
            </button>)}
            {results.key === search && !results.items.length && <p className={styles.muted}>No se encontraron inquilinos.</p>}
          </div>
          {results.total > 20 && <p className={styles.muted}>Hay más coincidencias. Escribí el nombre o DNI para acotar la búsqueda.</p>}
        </div>}
        {errors.inquilino_id && (context || tenant) && <AlertMessage>{errors.inquilino_id}</AlertMessage>}
        <div className={styles.grid}>
          <FormField id="contract-start" label="Inicio de vigencia" required error={errors.fecha_inicio}><TextInput type="date" value={dates.fecha_inicio} onChange={event => setDates({ ...dates, fecha_inicio: event.target.value })} /></FormField>
          <FormField id="contract-end" label="Fin de vigencia" required error={errors.fecha_fin}><TextInput type="date" value={dates.fecha_fin} onChange={event => setDates({ ...dates, fecha_fin: event.target.value })} /></FormField>
        </div>
        <FormField id="contract-file" label="Documento del contrato" error={errors.archivo} hint="PDF de hasta 10 MB, sin contraseña. Podés guardar un borrador sin archivo.">
          <input className={styles.file} type="file" accept=".pdf,application/pdf" onChange={event => setFile(event.target.files?.[0] ?? null)} />
        </FormField>
        <div>
          <label className={styles.check}><input type="checkbox" checked={signed} onChange={event => setSigned(event.target.checked)} />Este PDF es el contrato firmado</label>
          <p className={styles.muted}>Al confirmarlo, sus participantes podrán consultarlo y no se podrán editar sus fechas. Sin marcar esta opción, queda como borrador privado de la inmobiliaria.</p>
        </div>
      </div>
      <div className={`${styles.footer} ${styles.actions}`}><Link className={styles.cancelLink} to={contractId ? `/contratos/${contractId}` : '/contratos'}>Cancelar</Link><Button disabled={busy} type="submit" leadingIcon={<Save aria-hidden="true" />}>{busy ? 'Guardando…' : signed ? 'Guardar contrato firmado' : 'Guardar borrador'}</Button></div>
    </form>
  </div></PageContainer>
}
