import styles from './LoadingState.module.css'

function LoadingState({ label = 'Cargando información', lines = 3 }) {
  const visibleLines = Math.max(1, lines)

  return (
    <div className={styles.container} role="status" aria-label={label}>
      <span className="aari-sr-only">{label}</span>
      <span className={styles.heading} aria-hidden="true" />
      {Array.from({ length: visibleLines }, (_, index) => (
        <span
          className={styles.line}
          data-short={index === visibleLines - 1 ? 'true' : undefined}
          key={index}
          aria-hidden="true"
        />
      ))}
    </div>
  )
}

export default LoadingState
