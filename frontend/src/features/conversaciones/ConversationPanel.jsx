import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { MessageSquare, RefreshCw, Send } from 'lucide-react'
import { AlertMessage, Button, EmptyState, FormField, LoadingState, StatusBadge } from '../../components/ui/index.js'
import { finishQuestions, getConversation, markConversationRead, sendMessage } from './conversationsApi.js'
import styles from './ConversationPanel.module.css'

const date = (value) => new Intl.DateTimeFormat('es-AR', {
  dateStyle: 'short', timeStyle: 'short', hourCycle: 'h23', timeZone: 'America/Argentina/Buenos_Aires',
}).format(new Date(value))
const merge = (previous, incoming) => [...new Map([...previous, ...incoming].map((item) => [item.numero, item])).values()]
  .sort((left, right) => left.numero - right.numero)
const contiguousThrough = (items, confirmed) => {
  let through = confirmed
  for (const item of items) {
    if (item.numero <= through) continue
    if (item.numero !== through + 1) break
    through = item.numero
  }
  return through
}

export default function ConversationPanel({ requestId, threadId, onRead, onFinished, onDisabled }) {
  return <ConversationThread key={threadId || requestId} requestId={threadId || requestId} thread={Boolean(threadId)} onRead={onRead} onFinished={onFinished} onDisabled={onDisabled} />
}

function ConversationThread({ requestId, thread, onRead, onFinished, onDisabled }) {
  const id = useId()
  const [data, setData] = useState(null)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState('')
  const [sendError, setSendError] = useState('')
  const [readError, setReadError] = useState('')
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const content = useRef([])
  const cursor = useRef(0)
  const readThrough = useRef(0)
  const initialized = useRef(false)
  const pending = useRef(null)
  const sending = useRef(false)
  const token = useRef(null)
  const alive = useRef(true)
  const controls = useRef(new Set())
  const input = useRef(null)
  const restoreFocus = useRef(false)
  const finishKey = useRef(null)

  useEffect(() => {
    if (!busy && restoreFocus.current) {
      input.current?.focus()
      restoreFocus.current = false
    }
  }, [busy])

  const load = useCallback(async (mode = 'new') => {
    if (pending.current) return pending.current
    const controller = new AbortController()
    controls.current.add(controller)
    const task = (async () => {
      setUpdating(true)
      try {
        let result = await getConversation(requestId, {
          thread,
          before: mode === 'older' ? content.current[0]?.numero : undefined,
          after: mode !== 'older' && initialized.current ? cursor.current : undefined,
          signal: controller.signal,
        })
        if (!alive.current || controller.signal.aborted) return
        const confirmed = Math.max(readThrough.current, result.leido_hasta ?? 0)
        // El primer GET entrega el final del hilo. Si omite pendientes, empezar
        // desde el cursor confirmado y no dar por leídas las páginas intermedias.
        if (!initialized.current && result.items[0]?.numero > confirmed + 1) {
          result = await getConversation(requestId, { thread, after: confirmed, signal: controller.signal })
          if (!alive.current || controller.signal.aborted) return
          result = { ...result, hay_anteriores: confirmed > 0 }
        }
        readThrough.current = Math.max(confirmed, result.leido_hasta ?? 0)
        initialized.current = true
        content.current = merge(content.current, result.items)
        const through = contiguousThrough(content.current, readThrough.current)
        cursor.current = Math.max(cursor.current, through)
        setItems(content.current)
        setData((previous) => ({ ...result,
          hay_anteriores: mode === 'older' || !previous ? result.hay_anteriores : previous.hay_anteriores,
          hay_nuevos: mode === 'older' && previous ? previous.hay_nuevos : result.hay_nuevos,
        }))
        setError('')
        // No confirmar mensajes que aún están en páginas nuevas pendientes.
        if (document.visibilityState !== 'hidden' && through > readThrough.current) {
          try {
            const read = await markConversationRead(requestId, through, { signal: controller.signal, thread })
            if (!alive.current || controller.signal.aborted) return
            readThrough.current = Math.max(readThrough.current, read.leido_hasta)
            cursor.current = Math.max(cursor.current, readThrough.current)
            setData((previous) => previous ? { ...previous, no_leidos: read.no_leidos } : previous)
            setReadError('')
            onRead?.(requestId, read.no_leidos)
          } catch (failure) {
            const disabled = failure.body?.detail?.code === 'conversations_disabled'
            if (([401, 403, 404].includes(failure.status) || disabled) && alive.current) {
              content.current = []
              cursor.current = 0
              readThrough.current = 0
              initialized.current = false
              setItems([])
              setData(null)
              setError(failure.message)
              if (disabled) onDisabled?.()
              return
            }
            if (failure.name !== 'AbortError' && alive.current) setReadError('No pudimos registrar la lectura. Volveremos a intentarlo al actualizar.')
          }
        }
      } catch (failure) {
        if (failure.name !== 'AbortError' && alive.current) {
          const disabled = failure.body?.detail?.code === 'conversations_disabled'
          if ([401, 403, 404].includes(failure.status) || disabled) {
            content.current = []
            cursor.current = 0
            readThrough.current = 0
            initialized.current = false
            setItems([])
            setData(null)
            if (disabled) onDisabled?.()
          }
          setError(failure.message)
        }
      } finally {
        controls.current.delete(controller)
        if (alive.current && !controller.signal.aborted) { setLoading(false); setUpdating(false) }
      }
    })()
    pending.current = task
    try { await task } finally { if (pending.current === task) pending.current = null }
  }, [requestId, onRead, onDisabled, thread])

  useEffect(() => {
    alive.current = true
    let timer
    let stopped = false
    const refresh = async () => {
      clearTimeout(timer)
      if (stopped || document.visibilityState === 'hidden') return
      await load()
      if (!stopped) timer = setTimeout(refresh, 8000)
    }
    const visibility = () => {
      clearTimeout(timer)
      if (document.visibilityState !== 'hidden') refresh()
    }
    refresh()
    document.addEventListener('visibilitychange', visibility)
    const activeControls = controls.current
    return () => {
      stopped = true
      alive.current = false
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', visibility)
      activeControls.forEach((controller) => controller.abort())
      pending.current = null
    }
  }, [load])

  const send = async (event) => {
    event.preventDefault()
    const text = draft.replace(/\r\n?/g, '\n').trim()
    if (!text || text.length > 2000) { setSendError('Escribí un mensaje de entre 1 y 2000 caracteres.'); return }
    if (sending.current) return
    sending.current = true
    setBusy(true)
    setSendError('')
    if (!token.current || token.current.text !== text) token.current = { text, id: crypto.randomUUID() }
    try {
      const result = await sendMessage(requestId, { texto: text, request_id: token.current.id }, { thread })
      if (!alive.current) return
      // No avanzar cursor con el POST: podría saltar mensajes ajenos concurrentes.
      content.current = merge(content.current, [result.mensaje])
      setItems(content.current)
      setDraft('')
      token.current = null
      await load()
    } catch (failure) {
      if (alive.current) {
        setSendError(failure.message)
        if (failure.body?.detail?.code === 'conversations_disabled') onDisabled?.()
        if ([401, 403, 404, 409].includes(failure.status)) await load()
      }
    } finally {
      sending.current = false
      if (alive.current) { restoreFocus.current = true; setBusy(false) }
    }
  }

  const finish = async () => {
    if (sending.current) return
    sending.current = true
    setBusy(true)
    setSendError('')
    finishKey.current ??= crypto.randomUUID()
    try {
      await finishQuestions(data.id, finishKey.current)
      await load()
      onFinished?.(data.solicitud_id)
    } catch (failure) {
      if (alive.current) { setSendError(failure.message); await load() }
    } finally {
      sending.current = false
      if (alive.current) setBusy(false)
    }
  }

  return <section className={styles.panel} aria-labelledby={`${id}-title`}>
    <div className={styles.heading}>
      <div><h2 id={`${id}-title`}><MessageSquare aria-hidden="true" />{data?.finalidad === 'presupuesto' ? 'Avisos del agente' : 'Consultas técnicas'}</h2>
        <p>{data ? `Reclamo #${String(data.numero_reclamo).padStart(6, '0')} · ` : ''}{data?.finalidad === 'presupuesto' ? 'Novedades de esta solicitud. No es un chat libre con IA.' : 'Proveedor e inquilino aclaran el problema antes del presupuesto.'}</p></div>
      <Button variant="secondary" leadingIcon={<RefreshCw />} disabled={loading || updating}
        onClick={() => load()}>Actualizar conversación</Button>
    </div>
    <div className={styles.body}>
      {error ? <AlertMessage>{error}</AlertMessage> : null}
      {readError ? <AlertMessage tone="info">{readError}</AlertMessage> : null}
      {loading ? <LoadingState label="Cargando conversación" /> : data ? <>
        <div className={styles.toolbar}><p className={styles.muted}>Horarios de Argentina · {data.no_leidos} sin leer</p>
          <StatusBadge tone={data.puede_enviar ? 'success' : 'neutral'}>{data.puede_enviar ? 'Consultas abiertas' : 'Sólo lectura'}</StatusBadge></div>
        {data.hay_anteriores ? <Button variant="secondary" disabled={updating} onClick={() => load('older')}>Ver mensajes anteriores</Button> : null}
        {items.length ? <ol className={styles.messages} aria-label="Mensajes de la conversación">
          {items.map((item) => <li key={item.id} className={[styles.message, item.propio ? styles.own : '', item.origen === 'agente' ? styles.agent : ''].join(' ')}>
            <div className={styles.metadata}><strong>{item.autor_nombre}{item.propio ? ' · Vos' : ''}</strong>
              <time dateTime={item.creado_en}>{date(item.creado_en)}</time></div>
            {item.origen === 'agente' ? <small>Aviso automático del agente</small> : null}
            <p>{item.texto}</p>
          </li>)}
        </ol> : <EmptyState title="Todavía no hay mensajes" description="Podés hacer una consulta sobre este trabajo desde acá." />}
        {data.hay_nuevos ? <Button variant="secondary" disabled={updating} onClick={() => load()}>Ver mensajes nuevos</Button> : null}
        {data.finalidad === 'consulta_tecnica' && data.puede_enviar ? <form className={styles.composer} onSubmit={send} noValidate>
          <FormField id={`${id}-message`} label="Tu mensaje" error={sendError} hint="Hasta 2000 caracteres. El chat no aprueba presupuestos ni confirma visitas.">
            <textarea ref={input} className={styles.input} rows={3} maxLength={2000} value={draft} disabled={busy || Boolean(error)}
              onChange={(event) => { setDraft(event.target.value); setSendError('') }} />
          </FormField>
          <div className={styles.send}><span className={styles.muted}>{draft.length}/2000</span>
            <Button type="submit" leadingIcon={<Send />} disabled={busy || Boolean(error) || !draft.trim()}>{busy ? 'Enviando…' : 'Enviar mensaje'}</Button></div>
        </form> : <AlertMessage tone="info">{data.motivo_solo_lectura}</AlertMessage>}
        {data.puede_finalizar ? <Button variant="secondary" disabled={busy || updating} onClick={finish}>Finalizar consultas y continuar presupuesto</Button> : null}
        {!data.puede_enviar && sendError ? <AlertMessage>{sendError}</AlertMessage> : null}
      </> : !loading ? <Button variant="secondary" disabled={updating} onClick={() => load()}>Reintentar conversación</Button> : null}
    </div>
  </section>
}
