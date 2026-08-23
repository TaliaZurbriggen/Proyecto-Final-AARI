import { AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react'
import styles from './AlertMessage.module.css'

function AlertMessage({ children, tone = 'error' }) {
  const Icon =
    tone === 'success'
      ? CheckCircle2
      : tone === 'warning'
        ? AlertTriangle
        : AlertCircle
  return (
    <div
      className={styles.alert}
      data-tone={tone}
      role={tone === 'error' ? 'alert' : 'status'}
    >
      <Icon aria-hidden="true" />
      <p>{children}</p>
    </div>
  )
}

export default AlertMessage
