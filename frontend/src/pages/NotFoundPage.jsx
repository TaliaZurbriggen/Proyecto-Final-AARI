import { Link } from 'react-router'
import { SearchX } from 'lucide-react'
import { PageContainer } from '../components/layout/index.js'
import { EmptyState } from '../components/ui/index.js'
import styles from './NotFoundPage.module.css'

function NotFoundPage() {
  return (
    <PageContainer>
      <EmptyState
        action={
          <Link className={styles.link} to="/propietarios">
            Volver a propietarios
          </Link>
        }
        description="La dirección ingresada no corresponde a una pantalla disponible."
        icon={SearchX}
        title="No encontramos esta página"
      />
    </PageContainer>
  )
}

export default NotFoundPage
