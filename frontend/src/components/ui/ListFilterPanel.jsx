import { useId, useState } from 'react'
import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import Button from './Button.jsx'
import FormField from './FormField.jsx'
import SelectInput from './SelectInput.jsx'
import TextInput from './TextInput.jsx'
import styles from './ListFilterPanel.module.css'

// El padre usa key=panelKey para restaurar búsqueda y filtros desde la URL.
function ListFilterPanel({ fields, values, search = '', searchLabel, searchPlaceholder,
  hasSearch = false, onApply, onClear, title, description }) {
  const id = useId()
  const [draft, setDraft] = useState(values)
  const [draftSearch, setDraftSearch] = useState(search)
  const activeCount = Object.values(values).filter(Boolean).length + Number(hasSearch)
  const [open, setOpen] = useState(activeCount > 0)
  const update = (name, value) => setDraft((current) => ({ ...current, [name]: value }))
  const clear = () => {
    setDraft(Object.fromEntries(fields.map(({ name }) => [name, ''])))
    setDraftSearch('')
    onClear()
  }

  return (
    <section className={styles.panel} aria-label={title}>
      <div className={styles.heading}>
        <Button variant="secondary" leadingIcon={<SlidersHorizontal />}
          aria-expanded={open} aria-controls={id} onClick={() => setOpen((value) => !value)}>
          <span className={styles.toggleContent}>
            <span>Filtros{activeCount ? ` · ${activeCount} activos` : ''}</span>
            <ChevronDown aria-hidden="true" className={open ? styles.expanded : styles.chevron} />
          </span>
        </Button>
        <p>{activeCount ? 'Filtros aplicados al listado' : 'Acotá la búsqueda según lo que necesitás.'}</p>
      </div>
      <div id={id} hidden={!open}>
        {open ? <form onSubmit={(event) => { event.preventDefault(); onApply(draft, draftSearch) }}>
          <p className={styles.description}>{description}</p>
          <div className={styles.grid}>
            {searchLabel ? (
              <FormField id={`${id}-search`} label={searchLabel}>
                <TextInput value={draftSearch} placeholder={searchPlaceholder} maxLength={120}
                  onChange={(event) => setDraftSearch(event.target.value)} />
              </FormField>
            ) : null}
            {fields.map((field) => (
              <FormField key={field.name} id={`${id}-${field.name}`} label={field.label}>
                {field.options ? (
                  <SelectInput value={draft[field.name]} onChange={(event) => update(field.name, event.target.value)}>
                    <option value="">{field.allLabel ?? 'Todos'}</option>
                    {field.options.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                  </SelectInput>
                ) : (
                  <TextInput value={draft[field.name]} placeholder={field.placeholder} maxLength={field.maxLength ?? 100}
                    onChange={(event) => update(field.name, event.target.value)} />
                )}
              </FormField>
            ))}
          </div>
          <div className={styles.actions}>
            <Button variant="secondary" onClick={clear}
              disabled={!draftSearch && !Object.values(draft).some(Boolean) && !activeCount}>Limpiar filtros</Button>
            <Button type="submit">Aplicar filtros</Button>
          </div>
        </form> : null}
      </div>
    </section>
  )
}

export default ListFilterPanel
