import styles from './SelectInput.module.css'

function SelectInput({ className, ...props }) {
  const classes = [styles.select, className].filter(Boolean).join(' ')
  return <select className={classes} {...props} />
}

export default SelectInput
