import styles from './PageContainer.module.css'

function PageContainer({ as: Element = 'main', children, className, ...props }) {
  const classes = [styles.container, className].filter(Boolean).join(' ')

  return (
    <Element className={classes} {...props}>
      {children}
    </Element>
  )
}

export default PageContainer
