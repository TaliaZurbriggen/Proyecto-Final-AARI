import { Building2, ClipboardList, Wrench } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import AlertMessage from '../../../components/ui/AlertMessage.jsx'
import { useAuth } from '../authContext.js'
import styles from './RoleHomePage.module.css'

const contentByRole = {
  inquilino: {
    description: 'Tu acceso está listo para gestionar los reclamos de tu vivienda.',
    eyebrow: 'Portal del inquilino',
    title: 'Hola, ya podés ingresar a AARI',
  },
  operador: {
    description: 'Tu acceso está listo para trabajar con la gestión operativa.',
    eyebrow: 'Portal de operación',
    title: 'Bienvenido a AARI',
  },
  propietario: {
    description: 'Tu acceso está listo para consultar propiedades y reclamos asociados.',
    eyebrow: 'Portal del propietario',
    title: 'Hola, ya podés ingresar a AARI',
  },
}

function RoleHomePage() {
  const { user } = useAuth()
  const location = useLocation()
  const content = contentByRole[user?.rol] ?? contentByRole.operador

  return (
    <PageContainer>
      <PageHeading
        description={content.description}
        eyebrow={content.eyebrow}
        title={content.title}
      />

      {location.state?.notice ? (
        <div className={styles.notice}>
          <AlertMessage tone="success">{location.state.notice}</AlertMessage>
        </div>
      ) : null}

      <section className={styles.summary} aria-labelledby="access-ready-title">
        <span className={styles.summaryIcon} aria-hidden="true">
          <Building2 />
        </span>
        <div>
          <p className={styles.eyebrow}>Cuenta activa</p>
          <h2 id="access-ready-title">Tu sesión está protegida y lista</h2>
          <p>
            Ingresaste como <strong>{user?.email}</strong>. Las funciones del
            portal se incorporarán en las próximas historias del Sprint.
          </p>
        </div>
      </section>

      <div className={styles.cards}>
        <article>
          <ClipboardList aria-hidden="true" />
          <h2>Reclamos</h2>
          <p>
            {user?.rol === 'inquilino'
              ? 'Informá un problema de tu unidad y recibí el número de seguimiento.'
              : 'Vas a poder consultar y seguir el estado de tus solicitudes.'}
          </p>
          {user?.rol === 'inquilino' ? (
            <Link className={styles.cardAction} to="/inquilino/reclamos/nuevo">
              Crear reclamo
            </Link>
          ) : (
            <span>Próximamente</span>
          )}
        </article>
        <article>
          <Wrench aria-hidden="true" />
          <h2>Gestión asociada</h2>
          <p>La información disponible se adaptará al rol de tu cuenta.</p>
          <span>Próximamente</span>
        </article>
      </div>
    </PageContainer>
  )
}

export default RoleHomePage
