import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import { ArrowLeft, MessageSquare, X } from 'lucide-react'
import { AlertMessage, Button, EmptyState, IconButton, LoadingState, StatusBadge } from '../../components/ui/index.js'
import ConversationPanel from './ConversationPanel.jsx'
import { getConversation, getInbox, openQuestions, questionsChanged } from './conversationsApi.js'
import styles from './ConversationDock.module.css'

const DockContext = createContext(null)

export function ConversationDockProvider({ user, children }) {
  return <ConversationDockState key={`${user?.id}:${user?.rol}`} user={user}>{children}</ConversationDockState>
}

function ConversationDockState({ user, children }) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(null)
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [loading, setLoading] = useState(true)
  const [resolving, setResolving] = useState(false)
  const launcher = useRef(null)
  const dialog = useRef(null)
  const closeButton = useRef(null)
  const returnFocus = useRef(null)
  const pending = useRef(null)
  const resolution = useRef(null)
  const session = `${user?.id}:${user?.rol}`
  const titleId = useId()
  const valid = user && !user.primer_ingreso

  const refresh = useCallback(async () => {
    if (!user || user.primer_ingreso || document.visibilityState === 'hidden') return
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    try {
      const result = await getInbox(page, { signal: controller.signal })
      if (controller.signal.aborted) return
      setData(result)
      setPage(result.page)
      setError('')
      setEnabled(true)
    } catch (failure) {
      if (controller.signal.aborted || failure.name === 'AbortError') return
      if (failure.body?.detail?.code === 'conversations_disabled') { setEnabled(false); setData(null) }
      else {
        setData(null)
        if ([401, 403, 404].includes(failure.status)) setSelected(null)
        setError(failure.message)
      }
    } finally { if (!controller.signal.aborted) setLoading(false) }
  }, [user, page])

  useEffect(() => {
    let stopped = false
    let timer
    const poll = async () => {
      clearTimeout(timer)
      if (stopped || document.visibilityState === 'hidden') return
      await refresh()
      if (!stopped) timer = setTimeout(poll, 8000)
    }
    const visibility = () => { clearTimeout(timer); if (document.visibilityState !== 'hidden') poll() }
    poll()
    document.addEventListener('visibilitychange', visibility)
    return () => {
      stopped = true
      clearTimeout(timer)
      pending.current?.abort()
      resolution.current?.abort()
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [refresh])

  const show = useCallback(() => {
    returnFocus.current = document.activeElement
    setOpen(true)
  }, [])
  const openThread = useCallback((id) => { show(); setSelected(id); setError('') }, [show])
  const openRequest = useCallback(async (id) => {
    show()
    setSelected(null)
    setResolving(true)
    resolution.current?.abort()
    const controller = new AbortController()
    resolution.current = controller
    try {
      const result = await getConversation(id, { signal: controller.signal })
      if (!controller.signal.aborted) { setSelected(result.id); setError('') }
    } catch (failure) { if (!controller.signal.aborted) setError(failure.message) }
    finally { if (!controller.signal.aborted) setResolving(false) }
  }, [show])
  const close = useCallback(() => {
    resolution.current?.abort()
    setResolving(false)
    setOpen(false)
    setSelected(null)
    const previous = returnFocus.current
    if (previous?.isConnected) previous.focus()
    else launcher.current?.focus()
  }, [])

  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButton.current?.focus()
    return () => { document.body.style.overflow = previous }
  }, [open])
  const onRead = useCallback(() => {
    window.dispatchEvent(new Event('aari:mensajes-leidos'))
    refresh()
  }, [refresh])
  const onFinished = useCallback((id) => { questionsChanged(id); refresh() }, [refresh])
  const keydown = (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close() }
    if (event.key !== 'Tab') return
    const controls = Array.from(dialog.current?.querySelectorAll('button:not(:disabled),textarea:not(:disabled),a[href]') || [])
      .filter((element) => element.getClientRects().length)
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }

  return <DockContext.Provider key={session} value={{ openRequest, openThread }}>
    {children}
    {valid && enabled ? <>
      <Button ref={launcher} className={styles.launcher} leadingIcon={<MessageSquare />} aria-label={`Mensajes${data?.no_leidos ? `, ${data.no_leidos} sin leer` : ''}`}
        aria-haspopup="dialog" aria-expanded={open} onClick={() => { if (open) close(); else { show(); refresh() } }}>
        Mensajes {data?.no_leidos > 0 ? <span className={styles.count} aria-hidden="true">{data.no_leidos > 99 ? '99+' : data.no_leidos}</span> : null}
      </Button>
      {open ? <div className={styles.overlay}>
        <div className={styles.dialog} ref={dialog} role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={keydown}>
          <header className={styles.header}>
            {selected ? <IconButton label="Volver a mensajes" onClick={() => setSelected(null)}><ArrowLeft /></IconButton> : null}
            <h2 id={titleId}>{selected ? 'Mensajes del reclamo' : 'Tus mensajes'}</h2>
            <button ref={closeButton} className={styles.close} onClick={close} aria-label="Cerrar mensajes"><X aria-hidden="true" /></button>
          </header>
          <div className={styles.content}>
            {resolving ? <LoadingState label="Abriendo conversación" /> : selected ?
              <ConversationPanel threadId={selected} onRead={onRead} onFinished={onFinished} /> : <>
                {error ? <AlertMessage>{error}</AlertMessage> : null}
                {loading ? <LoadingState label="Consultando mensajes" /> : data?.items?.length ? <ul className={styles.list}>
                  {data.items.map((item) => <li key={item.id}><button className={styles.thread} onClick={() => setSelected(item.id)}>
                    <strong>Reclamo #{String(item.numero).padStart(6, '0')}</strong>
                    <span>{item.finalidad === 'consulta_tecnica' ? user.rol === 'proveedor' ? 'Consultas técnicas con el inquilino' : 'Consultas técnicas con el proveedor' : `Agente AARI · ${item.audiencia === 'proveedor' ? 'Avisos al proveedor' : 'Avisos al responsable'}`}</span>
                    <span>{item.proveedor}</span>
                    {item.no_leidos > 0 ? <StatusBadge tone="info">{item.no_leidos} sin leer</StatusBadge> : null}
                  </button></li>)}
                </ul> : !error ? <EmptyState title="No tenés mensajes" description="Los avisos del agente y las consultas habilitadas aparecerán acá." /> : null}
                {page > 1 || (data && data.total > data.page_size) ? <div className={styles.pagination}>
                  <Button size="sm" variant="secondary" disabled={page <= 1 || loading} onClick={() => { setLoading(true); setPage((value) => value - 1) }}>Ver anteriores</Button>
                  <Button size="sm" variant="secondary" disabled={!data || data.page * data.page_size >= data.total || loading} onClick={() => { setLoading(true); setPage((value) => value + 1) }}>Ver siguientes</Button>
                </div> : null}
                {error ? <Button size="sm" variant="secondary" onClick={refresh}>Reintentar mensajes</Button> : null}
              </>}
          </div>
        </div>
      </div> : null}
    </> : null}
  </DockContext.Provider>
}

export function ConversationLauncher({ requestId, label = 'Ver avisos del agente' }) {
  const dock = useContext(DockContext)
  return <Button variant="secondary" disabled={!dock} onClick={() => dock.openRequest(requestId)}>{label}</Button>
}

export function QuestionsButton({ request }) {
  const dock = useContext(DockContext)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const key = useRef(null)
  const locked = useRef(false)
  const questions = request.consulta_tecnica
  const open = async () => {
    if (locked.current) return
    if (questions) { dock?.openThread(questions.id); return }
    locked.current = true
    setBusy(true)
    setError('')
    key.current ??= crypto.randomUUID()
    try {
      const result = await openQuestions(request.id, key.current)
      questionsChanged(request.id)
      dock?.openThread(result.id)
    } catch (failure) { setError(failure.message) }
    finally { locked.current = false; setBusy(false) }
  }
  if (!request.conversacion_habilitada) return null
  return <div className={styles.questions}>
    {questions || request.puede_responder ? <Button variant="secondary" disabled={busy || !dock} onClick={open}>
      {busy ? 'Abriendo consultas…' : questions ? questions.consultas_cerradas_en ? 'Ver consultas finalizadas' : 'Continuar consultas con el inquilino' : 'Necesito hacer unas preguntas'}
    </Button> : null}
    {questions && !questions.consultas_cerradas_en ? <p>Finalizá las consultas desde Mensajes antes de enviar el presupuesto. El plazo de la solicitud no se amplía.</p> : null}
    {error ? <AlertMessage>{error}</AlertMessage> : null}
  </div>
}
