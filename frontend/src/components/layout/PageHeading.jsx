import styles from './PageHeading.module.css'

function PageHeading({ action, description, eyebrow, title }) {
  return (
    <header className={styles.heading}>
      <div className={styles.copy}>
        {eyebrow ? <p className={styles.eyebrow}>{eyebrow}</p> : null}
        <h1 className={styles.title}>{title}</h1>
        {description ? (
          <p className={styles.description}>{description}</p>
        ) : null}
      </div>
      {action ? <div className={styles.action}>{action}</div> : null}
    </header>
  )
}

export default PageHeading
