import { AlertCircle, CheckCircle2 } from 'lucide-react'
import styles from './AlertMessage.module.css'

function AlertMessage({ children, tone = 'error' }) {
  const Icon = tone === 'success' ? CheckCircle2 : AlertCircle
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
