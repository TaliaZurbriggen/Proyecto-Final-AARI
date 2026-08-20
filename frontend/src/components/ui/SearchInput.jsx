import { Search, X } from 'lucide-react'
import styles from './SearchInput.module.css'

const joinClassNames = (...classNames) => classNames.filter(Boolean).join(' ')

function SearchInput({
  className,
  label = 'Buscar',
  onClear,
  value,
  ...props
}) {
  const canClear = Boolean(value) && typeof onClear === 'function'

  return (
    <div className={joinClassNames(styles.wrapper, className)}>
      <Search className={styles.searchIcon} aria-hidden="true" />
      <input
        aria-label={label}
        className={styles.input}
        type="search"
        value={value}
        {...props}
      />
      {canClear ? (
        <button
          aria-label="Limpiar búsqueda"
          className={styles.clearButton}
          onClick={onClear}
          type="button"
        >
          <X aria-hidden="true" />
        </button>
      ) : null}
    </div>
  )
}

export default SearchInput
