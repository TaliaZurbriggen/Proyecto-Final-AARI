import styles from './StatusBadge.module.css'

const joinClassNames = (...classNames) => classNames.filter(Boolean).join(' ')

function StatusBadge({ children, className, tone = 'neutral' }) {
  return (
    <span className={joinClassNames(styles.badge, styles[tone], className)}>
      <span className={styles.dot} aria-hidden="true" />
      {children}
    </span>
  )
}

export default StatusBadge
