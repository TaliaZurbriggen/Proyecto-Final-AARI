import { useEffect, useState } from 'react'
import { FilePlus2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { PageContainer, PageHeading } from '../../../components/layout/index.js'
import { AlertMessage, Button, LoadingState, SearchInput, StatusBadge } from '../../../components/ui/index.js'
import { useAuth } from '../../auth/authContext.js'
import { listContracts } from '../api/contratosApi.js'
import { contractBase, contractTone, dateLabel } from '../validation.js'
import styles from './Contratos.module.css'

export default function ContractsListPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [result, setResult] = useState({ data: null, error: '', key: '' })
  const key = params.toString()
  const base = contractBase(user.rol)
  const page = Math.max(1, Number(params.get('page')) || 1)
  const search = params.get('search') ?? ''
  const tenantId = params.get('inquilino_id') ?? ''
  const propertyId = params.get('propiedad_id') ?? ''
  useEffect(() => {
    const controller = new AbortController()
    listContracts({ page, search, inquilinoId: tenantId, propiedadId: propertyId, signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult({ data, error: '', key }) })
      .catch(error => { if (!controller.signal.aborted) setResult({ data: null, error: error.message, key }) })
    return () => controller.abort()
  }, [page, search, tenantId, propertyId, key])
  const update = (name, value) => {
    const next = new URLSearchParams(params)
    next.delete('page')
    if (value) next.set(name, String(value))
    else next.delete(name)
    setParams(next, { replace: true })
  }
  const loading = result.key !== key || (!result.data && !result.error)
  return <PageContainer>
    <PageHeading eyebrow={user.rol === 'administrador' ? 'Administración' : 'Documentación personal'} title={user.rol === 'administrador' ? 'Contratos de alquiler' : 'Mis contratos'}
      description={user.rol === 'administrador' ? 'Gestioná los documentos, las vigencias y el historial de cada alquiler.' : 'Consultá los contratos firmados que la inmobiliaria compartió con vos.'}
      action={user.rol === 'administrador' && <Link className={styles.primaryLink} to="/contratos/nuevo"><FilePlus2 aria-hidden="true" />Cargar contrato</Link>} />
    <div className={styles.stack}>
      <div className={styles.search}><SearchInput aria-label="Buscar contratos" placeholder="Buscar por inmueble o participante" value={search} onChange={event => update('search', event.target.value)} onClear={() => update('search', '')} /></div>
      {(tenantId || propertyId) && <p className={styles.muted}>Mostrando contratos de la ficha seleccionada. <Link to={base}>Ver todos</Link></p>}
      {loading ? <LoadingState label="Cargando contratos" /> : result.error ? <AlertMessage>{result.error}</AlertMessage> : <>
        <p className={styles.muted}>{result.data.total} contratos encontrados</p>
        {result.data.items.length ? <div className={styles.cards}>{result.data.items.map(contract => <article className={styles.panel} key={contract.id}>
          <div className={styles.card}><div className={styles.cardMain}>
            <h2><Link to={`${base}/${contract.id}`}>{contract.direccion}</Link></h2>
            <p>{contract.inquilino_nombre} · {contract.propietario_nombre}</p>
            <p>{dateLabel(contract.fecha_inicio)} — {dateLabel(contract.fecha_finalizacion ?? contract.fecha_fin)}</p>
          </div><StatusBadge tone={contractTone(contract.vigencia)}>{contract.vigencia}</StatusBadge></div>
        </article>)}</div> : <section className={styles.panel}><div className={styles.content}><h2>No hay contratos para mostrar</h2><p className={styles.muted}>{user.rol === 'administrador' ? 'Cargá un contrato o probá con otra búsqueda.' : 'Acá aparecerán tus contratos cuando la inmobiliaria los registre como firmados.'}</p></div></section>}
        {result.data.total_pages > 1 && <nav className={styles.pager} aria-label="Páginas de contratos">
          <Button variant="secondary" disabled={page <= 1} onClick={() => update('page', page - 1)}>Anterior</Button>
          <span>Página {page} de {result.data.total_pages}</span>
          <Button variant="secondary" disabled={page >= result.data.total_pages} onClick={() => update('page', page + 1)}>Siguiente</Button>
        </nav>}
      </>}
    </div>
  </PageContainer>
}
