import { Bell, Building2 } from 'lucide-react'
import { IconButton, SearchInput } from '../ui/index.js'
import styles from './AppHeader.module.css'

function getInitials(name) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join('')
    .toUpperCase()
}

function AppHeader({
  activeItem,
  items = [],
  notificationCount = 0,
  onNavigate,
  onNotificationsClick,
  onProfileClick,
  onSearchChange,
  onSearchClear,
  profileName = 'Usuario AARI',
  profileRole = 'Administración',
  searchPlaceholder = 'Buscar reclamo o propiedad',
  searchValue,
}) {
  const handleNavigation = (event, item) => {
    if (onNavigate) {
      event.preventDefault()
      onNavigate(item)
    }
  }

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <a className={styles.brand} href="/" aria-label="Ir al inicio de AARI">
          <span className={styles.brandMark} aria-hidden="true">
            <Building2 />
          </span>
          <span className={styles.brandCopy}>
            <strong>AARI</strong>
            <small>Gestión inmobiliaria</small>
          </span>
        </a>

        <nav className={styles.navigation} aria-label="Navegación principal">
          {items.map((item) => {
            const isActive = item.label === activeItem

            return (
              <a
                aria-current={isActive ? 'page' : undefined}
                className={isActive ? styles.activeLink : styles.link}
                href={item.href}
                key={item.label}
                onClick={(event) => handleNavigation(event, item)}
              >
                {item.label}
              </a>
            )
          })}
        </nav>

        <SearchInput
          className={styles.search}
          label="Buscar en AARI"
          onChange={onSearchChange}
          onClear={onSearchClear}
          placeholder={searchPlaceholder}
          value={searchValue}
        />

        <div className={styles.account}>
          <div className={styles.notification}>
            <IconButton
              label={
                notificationCount > 0
                  ? `Ver notificaciones, ${notificationCount} sin leer`
                  : 'Ver notificaciones'
              }
              onClick={onNotificationsClick}
            >
              <Bell />
            </IconButton>
            {notificationCount > 0 ? (
              <span className={styles.notificationCount} aria-hidden="true">
                {notificationCount > 9 ? '9+' : notificationCount}
              </span>
            ) : null}
          </div>

          <button
            aria-label={`Abrir perfil de ${profileName}`}
            className={styles.profile}
            onClick={onProfileClick}
            type="button"
          >
            <span className={styles.avatar} aria-hidden="true">
              {getInitials(profileName)}
            </span>
            <span className={styles.profileCopy}>
              <strong>{profileName}</strong>
              <small>{profileRole}</small>
            </span>
          </button>
        </div>
      </div>
    </header>
  )
}

export default AppHeader
