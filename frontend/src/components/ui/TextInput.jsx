import styles from './TextInput.module.css'

function TextInput({ className, ...props }) {
  const classes = [styles.input, className].filter(Boolean).join(' ')
  return <input className={classes} {...props} />
}

export default TextInput
