import { useEffect, useId, useRef, useState } from 'react'
import { Bell, Building2, ChevronDown, LogOut } from 'lucide-react'
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
  navigationVariant = 'tabs',
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
  const menuButtonRef = useRef(null)
  const navigationId = useId()
  const [menuOpen, setMenuOpen] = useState(false)
  const tiledNavigation = navigationVariant === 'tiles'

  useEffect(() => {
    if (tiledNavigation) return
    const navigation = navigationRef.current
    const activeLink = navigation?.querySelector('[aria-current="page"]')
    if (!activeLink) return

    // Desplazar solo el menú; scrollIntoView también movía la página completa.
    const centerActiveLink = () => {
      if (navigation.scrollWidth <= navigation.clientWidth) return
      navigation.scrollTo?.({
        left: navigation.scrollLeft + activeLink.getBoundingClientRect().left
          - navigation.getBoundingClientRect().left
          - (navigation.clientWidth - activeLink.offsetWidth) / 2,
        behavior: 'instant',
      })
    }
    centerActiveLink()
    // Recalcular al cargar la tipografía o cambiar el ancho/orientación.
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(centerActiveLink)
    observer.observe(navigation)
    observer.observe(activeLink)
    return () => observer.disconnect()
  }, [activeItem, tiledNavigation])

  useEffect(() => {
    if (!menuOpen) return
    const closeOutside = (event) => {
      if (!navigationRef.current?.contains(event.target)
          && !menuButtonRef.current?.contains(event.target)) setMenuOpen(false)
    }
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        menuButtonRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [menuOpen])

  const handleNavigation = (event, item) => {
    // Conservar los enlaces nativos (abrir en otra pestaña, copiar dirección).
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return
    setMenuOpen(false)
    if (onNavigate) {
      event.preventDefault()
      onNavigate(item)
    }
  }

  return (
    <header className={[styles.header, tiledNavigation && styles.tiledHeader].filter(Boolean).join(' ')}>
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

        {tiledNavigation ? (
          <button
            aria-controls={navigationId}
            aria-expanded={menuOpen}
            className={styles.menuToggle}
            onClick={() => setMenuOpen((open) => !open)}
            ref={menuButtonRef}
            type="button"
          >
            <span>Menú</span><span className={styles.currentSection}>{activeItem}</span>
            <ChevronDown aria-hidden="true" />
          </button>
        ) : null}
        <nav
          className={[styles.navigation, tiledNavigation && styles.tiledNavigation, menuOpen && styles.menuOpen].filter(Boolean).join(' ')}
          id={navigationId}
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
              <strong title={profileName}>{profileName}</strong>
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
