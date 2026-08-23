import { useEffect, useRef } from 'react'
import { AlertTriangle } from 'lucide-react'
import Button from './Button.jsx'
import styles from './ConfirmDialog.module.css'

function ConfirmDialog({
  cancelLabel = 'Cancelar',
  confirmLabel = 'Confirmar',
  description,
  isBusy = false,
  onCancel,
  onConfirm,
  open,
  title,
}) {
  const cancelRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    cancelRef.current?.focus()
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !isBusy) onCancel()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isBusy, onCancel, open])

  if (!open) return null

  return (
    <div className={styles.backdrop}>
      <section
        aria-describedby="confirm-dialog-description"
        aria-labelledby="confirm-dialog-title"
        aria-modal="true"
        className={styles.dialog}
        role="alertdialog"
      >
        <span className={styles.icon} aria-hidden="true">
          <AlertTriangle />
        </span>
        <div className={styles.copy}>
          <h2 id="confirm-dialog-title">{title}</h2>
          <p id="confirm-dialog-description">{description}</p>
        </div>
        <div className={styles.actions}>
          <Button
            disabled={isBusy}
            onClick={onCancel}
            ref={cancelRef}
            variant="secondary"
          >
            {cancelLabel}
          </Button>
          <Button disabled={isBusy} onClick={onConfirm} variant="danger">
            {isBusy ? 'Eliminando…' : confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  )
}

export default ConfirmDialog
