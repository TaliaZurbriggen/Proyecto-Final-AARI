import { useCallback, useEffect, useRef, useState } from 'react'
import { Mail, Plus, UserRoundCog, UserRoundX } from 'lucide-react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, ConfirmDialog, EmptyState, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { deactivateOperador, listOperadores, retryOperadorAccess } from '../api/operadoresApi.js'
import styles from './Operadores.module.css'

function deliveryStatus(operator) {
  if (!operator.activo) return ['Acceso deshabilitado', 'neutral']
  if (!operator.acceso?.primer_ingreso && operator.acceso) return ['Contraseña actualizada', 'success']
  if (operator.acceso?.estado === 'enviado') return ['Espera primer ingreso', 'info']
  if (operator.acceso?.estado === 'fallido') return ['Envío fallido', 'danger']
  return ['Envío pendiente', 'warning']
}

function OperadoresListPage() {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const parsedPage = Number(params.get('page'))
  const page = Number.isSafeInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1
  const search = params.get('search') ?? ''
  const queryKey = `${page}:${search}`
  const [result, setResult] = useState({ key: '', data: null, error: '' })
  const [notice, setNotice] = useState(location.state?.notice ?? null)
  const [action, setAction] = useState(null)
  const [busy, setBusy] = useState(false)
  const actionTrigger = useRef(null)
  const feedbackRef = useRef(null)
  const restoreActionFocus = useRef(false)
  const requestVersion = useRef(0)

  const load = useCallback((signal) => {
    const version = ++requestVersion.current
    return listOperadores({ page, search, signal }).then((data) => {
      if (!signal?.aborted && version === requestVersion.current) setResult({ key: queryKey, data, error: '' })
    }).catch((error) => {
      if (error.name !== 'AbortError' && version === requestVersion.current) setResult({ key: queryKey, data: null, error: error.message })
    })
  }, [page, search, queryKey])
  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => { controller.abort(); requestVersion.current += 1 }
  }, [load])

  const closeAction = useCallback(() => {
    restoreActionFocus.current = true
    setAction(null)
  }, [])
  useEffect(() => {
    if (!action && !busy && restoreActionFocus.current) {
      const trigger = actionTrigger.current
      if (trigger?.isConnected && !trigger.disabled) trigger.focus()
      else feedbackRef.current?.focus()
      restoreActionFocus.current = false
    }
  }, [action, busy])
  const openAction = (kind, operator, event) => {
    actionTrigger.current = event.currentTarget
    setAction({ kind, operator })
  }
  const confirmAction = async () => {
    if (!action || busy) return
    setBusy(true)
    setNotice(null)
    try {
      if (action.kind === 'deactivate') {
        const response = await deactivateOperador(action.operator.id)
        setNotice({ tone: 'success', message: `Operador desactivado. Reclamos devueltos a la cola general: ${response.reclamos_liberados}.` })
      } else {
        const response = await retryOperadorAccess(action.operator.id)
        const sent = response.acceso?.estado === 'enviado'
        setNotice({ tone: sent ? 'success' : 'warning', message: sent
          ? 'Se enviaron nuevas credenciales temporales. La contraseña anterior ya no es válida.'
          : 'La cuenta se conserva, pero el correo no está confirmado. Reintentá el envío más tarde.' })
      }
      closeAction()
      await load()
    } catch (error) {
      closeAction()
      setNotice({ tone: 'danger', message: error.message })
    } finally { setBusy(false) }
  }
  const goToPage = (nextPage) => {
    const next = new URLSearchParams(params)
    next.set('page', String(nextPage))
    setParams(next)
  }
  const loading = result.key !== queryKey
  const operators = result.data?.items ?? []
  const deactivating = action?.kind === 'deactivate'

  return (
    <PageContainer>
      <PageHeading title="Operadores" eyebrow="Administración"
        description="Gestioná quiénes pueden atender los casos escalados y su acceso al sistema."
        action={<Link className={styles.primaryLink} to="/operadores/nuevo"><Plus aria-hidden="true" />Nuevo operador</Link>} />
      <div className={styles.feedback} ref={feedbackRef} tabIndex={-1}>
        {notice ? <AlertMessage tone={notice.tone}>{notice.message}</AlertMessage> : null}
        {!loading && result.error ? <AlertMessage>{result.error}</AlertMessage> : null}
      </div>
      {loading ? <LoadingState label="Cargando operadores" lines={5} /> : null}
      {!loading && result.error ? <Button variant="secondary" onClick={() => load()}>Reintentar carga</Button> : null}
      {!loading && !result.error && !operators.length ? <EmptyState icon={UserRoundCog}
        title={search || page > 1 ? 'Sin resultados' : 'Todavía no hay operadores'}
        description={search || page > 1 ? 'Probá con otra búsqueda o volvé al listado completo.' : 'Registrá al primer integrante del equipo para habilitar su acceso.'}
        action={search || page > 1 ? <Button variant="secondary" onClick={() => setParams({})}>Ver todos</Button>
          : <Link className={styles.primaryLink} to="/operadores/nuevo">Registrar el primero</Link>} /> : null}
      {!loading && !result.error && operators.length > 0 ? (
        <section className={styles.panel} aria-labelledby="operators-title">
          <div className={styles.sectionHeading}><h2 id="operators-title">Equipo de operadores</h2><p>{result.data.total} registros en total</p></div>
          <div className={styles.tableRegion}>
            <table className={styles.table}>
              <thead><tr><th scope="col">Nombre</th><th scope="col">Email</th><th scope="col">Estado</th><th scope="col">Credenciales</th><th scope="col">Acciones</th></tr></thead>
              <tbody>{operators.map((operator) => {
                const [label, tone] = deliveryStatus(operator)
                return <tr key={operator.id}>
                  <td data-label="Nombre"><strong>{operator.nombre_completo}</strong></td>
                  <td data-label="Email">{operator.email}</td>
                  <td data-label="Estado"><StatusBadge tone={operator.activo ? 'success' : 'neutral'}>{operator.activo ? 'Activo' : 'Inactivo'}</StatusBadge></td>
                  <td data-label="Credenciales"><StatusBadge tone={tone}>{label}</StatusBadge></td>
                  <td data-label="Acciones"><div className={styles.rowActions}>
                    {operator.activo && operator.acceso?.primer_ingreso ? <Button variant="secondary" disabled={busy}
                      aria-label={`Reenviar credenciales de ${operator.nombre_completo}`} leadingIcon={<Mail />}
                      onClick={(event) => openAction('retry', operator, event)}>Reenviar</Button> : null}
                    {operator.activo ? <Button variant="ghost" disabled={busy} leadingIcon={<UserRoundX />}
                      aria-label={`Desactivar a ${operator.nombre_completo}`} onClick={(event) => openAction('deactivate', operator, event)}>Desactivar</Button>
                      : <span className={styles.muted}>Sin acciones</span>}
                  </div></td>
                </tr>
              })}</tbody>
            </table>
          </div>
          {result.data.total_pages > 1 ? <nav className={styles.pagination} aria-label="Paginación de operadores">
            <Button variant="secondary" disabled={page <= 1 || busy} onClick={() => goToPage(page - 1)}>Anterior</Button>
            <span>Página {page} de {result.data.total_pages}</span>
            <Button variant="secondary" disabled={page >= result.data.total_pages || busy} onClick={() => goToPage(page + 1)}>Siguiente</Button>
          </nav> : null}
        </section>
      ) : null}
      <ConfirmDialog open={Boolean(action)} isBusy={busy} onCancel={closeAction} onConfirm={confirmAction}
        title={deactivating ? '¿Desactivar operador?' : '¿Generar y reenviar credenciales?'}
        confirmLabel={deactivating ? 'Desactivar operador' : 'Generar y enviar'}
        busyLabel={deactivating ? 'Desactivando…' : 'Enviando…'}
        description={action ? deactivating
          ? `${action.operator.nombre_completo} perderá el acceso. Sus reclamos en estado Escalado volverán a la cola general; el historial se conserva.`
          : `Se enviará una nueva contraseña temporal a ${action.operator.email}. La clave anterior dejará de funcionar, incluso si el correo falla.` : ''} />
    </PageContainer>
  )
}

export default OperadoresListPage
