import { KeyRound, RefreshCw } from 'lucide-react'
import Button from '../../../components/ui/Button.jsx'
import StatusBadge from '../../../components/ui/StatusBadge.jsx'
import styles from './AccessDeliveryPanel.module.css'

function presentation(access) {
  if (!access.primer_ingreso) {
    return {
      description: 'La persona ya reemplazó la contraseña temporal.',
      label: 'Cuenta activa',
      tone: 'success',
    }
  }
  if (access.estado === 'enviado') {
    return {
      description: 'El correo fue entregado y espera el primer ingreso.',
      label: 'Credenciales enviadas',
      tone: 'info',
    }
  }
  if (access.estado === 'fallido') {
    return {
      description:
        access.ultimo_error ?? 'No se pudo entregar el correo de bienvenida.',
      label: 'Envío fallido',
      tone: 'danger',
    }
  }
  return {
    description: 'Las credenciales todavía no fueron enviadas.',
    label: 'Envío pendiente',
    tone: 'warning',
  }
}

function AccessDeliveryPanel({ access, isRetrying = false, onRetry }) {
  if (!access) return null
  const content = presentation(access)
  const canRetry = access.primer_ingreso && access.estado !== 'enviado'

  return (
    <section className={styles.panel} aria-labelledby="access-delivery-title">
      <span className={styles.icon} aria-hidden="true">
        <KeyRound />
      </span>
      <div className={styles.copy}>
        <div className={styles.heading}>
          <h2 id="access-delivery-title">Acceso al sistema</h2>
          <StatusBadge tone={content.tone}>{content.label}</StatusBadge>
        </div>
        <p>{content.description}</p>
        <small>
          {access.intentos === 1
            ? '1 intento de envío registrado'
            : `${access.intentos} intentos de envío registrados`}
        </small>
      </div>
      {canRetry ? (
        <Button
          disabled={isRetrying}
          leadingIcon={<RefreshCw />}
          onClick={onRetry}
          variant="secondary"
        >
          {isRetrying ? 'Reintentando…' : 'Reintentar envío'}
        </Button>
      ) : null}
    </section>
  )
}

export default AccessDeliveryPanel
