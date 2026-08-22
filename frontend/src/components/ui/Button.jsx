import { forwardRef } from 'react'
import styles from './Button.module.css'

const joinClassNames = (...classNames) => classNames.filter(Boolean).join(' ')

const Button = forwardRef(function Button({
  children,
  className,
  leadingIcon,
  size = 'md',
  type = 'button',
  variant = 'primary',
  ...props
}, ref) {
  return (
    <button
      className={joinClassNames(
        styles.button,
        styles[variant],
        styles[size],
        className,
      )}
      ref={ref}
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
})

export default Button
