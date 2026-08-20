import styles from './Button.module.css'

const joinClassNames = (...classNames) => classNames.filter(Boolean).join(' ')

function Button({
  children,
  className,
  leadingIcon,
  size = 'md',
  type = 'button',
  variant = 'primary',
  ...props
}) {
  return (
    <button
      className={joinClassNames(
        styles.button,
        styles[variant],
        styles[size],
        className,
      )}
      type={type}
      {...props}
    >
      {leadingIcon ? (
        <span className={styles.icon} aria-hidden="true">
          {leadingIcon}
        </span>
      ) : null}
      <span>{children}</span>
    </button>
  )
}

export default Button
