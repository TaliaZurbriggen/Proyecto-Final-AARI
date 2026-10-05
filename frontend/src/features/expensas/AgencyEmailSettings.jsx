import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, Mail, Save } from 'lucide-react'
import { AlertMessage, Button, FormField, LoadingState, TextInput } from '../../components/ui/index.js'
import { useHistoryResource } from '../reclamos/useHistoryResource.js'
import { getAgencyEmail, updateAgencyEmail } from './api.js'
import styles from './Expensas.module.css'

function AgencyEmailForm({ current }) {
  const [email, setEmail] = useState(current.email ?? '')
  const [result, setResult] = useState({ error: '', saved: false, saving: false })
  const controller = useRef(null)
  useEffect(() => () => controller.current?.abort(), [])
  const save = async (event) => {
    event.preventDefault()
    if (result.saving) return
    const abort = new AbortController()
    controller.current = abort
    setResult({ error: '', saved: false, saving: true })
    try {
      await updateAgencyEmail(email.trim(), { signal: abort.signal })
      if (!abort.signal.aborted) setResult({ error: '', saved: true, saving: false })
    } catch (error) {
      if (!abort.signal.aborted) setResult({ error: error.message, saved: false, saving: false })
    }
  }
  return (
    <form onSubmit={save} className={styles.settingsForm}>
      <p>Este destinatario es independiente del remitente SMTP. Cambiarlo afecta reportes nuevos, no los ya encolados.</p>
      {!current.configurado ? <AlertMessage>Configurá un correo válido antes de generar nuevas derivaciones.</AlertMessage> : null}
      <FormField id="agency-email" label="Correo de contacto de la inmobiliaria" required error={result.error}>
        <TextInput type="email" value={email} maxLength={254} onChange={(event) => {
          setEmail(event.target.value)
          setResult({ error: '', saved: false, saving: false })
        }} disabled={result.saving} />
      </FormField>
      <Button type="submit" leadingIcon={<Save />} disabled={result.saving || !email.trim()}>
        {result.saving ? 'Guardando…' : 'Guardar correo'}
      </Button>
      {result.saved ? <p role="status">Correo actualizado. Los envíos anteriores conservan su destinatario.</p> : null}
    </form>
  )
}

export default function AgencyEmailSettings() {
  const load = useCallback((signal) => getAgencyEmail({ signal }), [])
  const { data, error, isLoading } = useHistoryResource('agency-email', load)
  return (
    <details className={styles.settings}>
      <summary><Mail aria-hidden="true" /> Correo de la inmobiliaria <ChevronDown className={styles.chevron} aria-hidden="true" /></summary>
      {isLoading ? <LoadingState label="Cargando configuración del correo" /> : null}
      {error ? <AlertMessage>{error}</AlertMessage> : null}
      {data ? <AgencyEmailForm current={data} /> : null}
    </details>
  )
}
