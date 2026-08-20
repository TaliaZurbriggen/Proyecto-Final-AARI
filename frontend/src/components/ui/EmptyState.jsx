import { useId } from 'react'
import { Inbox } from 'lucide-react'
import styles from './EmptyState.module.css'

function EmptyState({
  action,
  description,
  icon: Icon = Inbox,
  title = 'Todavía no hay información',
}) {
  const titleId = useId()

  return (
    <section className={styles.container} aria-labelledby={titleId}>
      <span className={styles.icon} aria-hidden="true">
        <Icon />
      </span>
      <div className={styles.copy}>
        <h2 className={styles.title} id={titleId}>
          {title}
        </h2>
        {description ? <p className={styles.description}>{description}</p> : null}
      </div>
      {action ? <div className={styles.action}>{action}</div> : null}
    </section>
  )
}

export default EmptyState
