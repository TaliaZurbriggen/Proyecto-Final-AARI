import { useEffect, useState } from 'react'
import { ClipboardList, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, EmptyState, LoadingState, StatusBadge } from '../../../components/ui/index.js'
import { getProviderProfile } from '../api/providerAccessApi.js'
import ProviderQuoteRequests from '../components/ProviderQuoteRequests.jsx'
import styles from './ProviderPortal.module.css'

function ProviderHomePage() {
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let mounted = true
    getProviderProfile({ signal: controller.signal })
      .then((result) => { if (mounted) { setProfile(result); setError('') } })
      .catch((requestError) => { if (mounted && requestError.name !== 'AbortError') { setProfile(null); setError(requestError.message) } })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false; controller.abort() }
  }, [refresh])

  return <PageContainer>
    <PageHeading eyebrow="Espacio del proveedor" title="Mis solicitudes" description="Un lugar para seguir las solicitudes que te envía la inmobiliaria." />
    {loading ? <LoadingState label="Cargando tu espacio" /> : error ? <div className={styles.panelBody}><AlertMessage>{error}</AlertMessage><Button onClick={() => setRefresh((value) => value + 1)} variant="secondary">Reintentar</Button></div> : profile ? <>
      <section className={styles.welcome} aria-labelledby="provider-welcome-title"><div className={styles.welcomeIcon}><ShieldCheck aria-hidden="true" /></div><div><h2 id="provider-welcome-title">{profile.nombre_razon_social}</h2><p>{profile.email}</p></div><StatusBadge tone="success">Cuenta activa</StatusBadge></section>
      {profile.solicitudes_disponibles ? <ProviderQuoteRequests /> : <section className={styles.panel}><EmptyState icon={ClipboardList} title="Tu acceso ya está preparado" description="La recepción de solicitudes de presupuesto todavía está en preparación. La inmobiliaria te avisará cuando puedas comenzar a responderlas desde acá." /></section>}
      <p className={styles.accountLink}><Link to="/cambiar-contrasena">Cambiar mi contraseña</Link></p>
    </> : null}
  </PageContainer>
}

export default ProviderHomePage
