import styles from './IconButton.module.css'

const joinClassNames = (...classNames) => classNames.filter(Boolean).join(' ')

function IconButton({
  children,
  className,
  label,
  size = 'md',
  type = 'button',
  variant = 'ghost',
  ...props
}) {
  return (
    <button
      aria-label={label}
      className={joinClassNames(
        styles.button,
        styles[variant],
        styles[size],
        className,
      )}
      title={label}
      type={type}
      {...props}
    >
      {children}
    </button>
  )
}

export default IconButton
