import { useEffect, useRef } from 'react'
import { Bell, Building2, LogOut } from 'lucide-react'
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
  onLogout,
  onProfileClick,
  onSearchChange,
  onSearchClear,
  profileName = 'Usuario AARI',
  profileRole = 'Administración',
  searchPlaceholder = 'Buscar reclamo o propiedad',
  searchValue,
  showNotifications = true,
  showSearch = true,
}) {
  const navigationRef = useRef(null)

  useEffect(() => {
    navigationRef.current
      ?.querySelector('[aria-current="page"]')
      ?.scrollIntoView?.({ block: 'nearest', inline: 'center' })
  }, [activeItem])

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

        <nav
          className={styles.navigation}
          aria-label="Navegación principal"
          ref={navigationRef}
        >
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

        {showSearch ? (
          <SearchInput
            className={styles.search}
            label="Buscar en AARI"
            onChange={onSearchChange}
            onClear={onSearchClear}
            placeholder={searchPlaceholder}
            value={searchValue}
          />
        ) : null}

        <div
          className={`${styles.account} ${!showSearch ? styles.accountAtEnd : ''}`}
        >
          {showNotifications ? <div className={styles.notification}>
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
          </div> : null}

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
          {onLogout ? (
            <IconButton label="Cerrar sesión" onClick={onLogout}>
              <LogOut />
            </IconButton>
          ) : null}
        </div>
      </div>
    </header>
  )
}

export default AppHeader
