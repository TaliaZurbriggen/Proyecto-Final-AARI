import { cloneElement, isValidElement } from 'react'
import styles from './FormField.module.css'

function FormField({ children, error, hint, id, label, required = false }) {
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined
  const controlId = isValidElement(children) ? (children.props.id ?? id) : id

  const control = isValidElement(children)
    ? cloneElement(children, {
        id: controlId,
        'aria-describedby':
          children.props['aria-describedby'] ?? describedBy,
        'aria-invalid':
          children.props['aria-invalid'] ?? (error ? true : undefined),
        required: children.props.required ?? required,
      })
    : children

  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={controlId}>
        {label}
        {required ? (
          <span className={styles.required} aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {control}
      {hint ? (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className={styles.error} id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export default FormField
