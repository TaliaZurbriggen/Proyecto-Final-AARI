import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../auth/authContext.js'
import ContractFormPage from './ContractFormPage.jsx'
import ContractDetailPage from './ContractDetailPage.jsx'
import ContractsListPage from './ContractsListPage.jsx'
import { fileError, MAX_PDF_SIZE, nextDay, validateDates } from '../validation.js'
import { uploadContract } from '../api/contratosApi.js'

const contract = {
  id: 'contract-one', inquilino_id: 'tenant-one', propiedad_id: 'property-one',
  propietario_id: 'owner-one', inquilino_nombre: 'Inquilino de prueba',
  propietario_nombre: 'Propietario de prueba', direccion: 'Inmueble de prueba 123',
  localidad: 'Localidad de prueba', provincia: 'Córdoba', fecha_inicio: '2026-09-01',
  fecha_fin: '2027-08-31', fecha_finalizacion: null, contrato_anterior_id: null,
  estado: 'borrador', vigencia: 'Borrador', revision: 1, documentos: [],
}
const tenant = { id: 'tenant-one', nombre_completo: 'Inquilino de prueba',
  propiedad: { id: 'property-one', direccion: contract.direccion } }
const json = (body, status = 200) => ({ headers: { get: () => 'application/json' }, ok: status < 400, status, json: async () => body })
function renderRoute(path, role = 'administrador') {
  return render(<AuthContext.Provider value={{ user: { rol: role } }}>
    <MemoryRouter initialEntries={[path]}><Routes>
      <Route path="/contratos/nuevo" element={<ContractFormPage />} />
      <Route path="/contratos/:contractId/editar" element={<ContractFormPage />} />
      <Route path="/contratos/:contractId" element={<ContractDetailPage />} />
      <Route path="/contratos" element={<ContractsListPage />} />
      <Route path="/inquilino/contratos/:contractId" element={<ContractDetailPage />} />
      <Route path="/propietario/contratos/:contractId" element={<ContractDetailPage />} />
    </Routes></MemoryRouter>
  </AuthContext.Provider>)
}
afterEach(() => vi.restoreAllMocks())

describe('contratos: validaciones y formularios', () => {
  it('valida fechas y archivos antes de enviarlos', () => {
    expect(validateDates('', '')).toHaveProperty('fecha_inicio')
    expect(validateDates('2026-01-01', '2026-01-01')).toHaveProperty('fecha_fin')
    expect(validateDates('2026-01-01', '2026-01-02')).toEqual({})
    expect(fileError(null)).toBe('')
    expect(fileError(null, true)).toBeTruthy()
    expect(fileError({ name: 'x.exe', type: '', size: 1 })).toBeTruthy()
    expect(fileError({ name: 'x.pdf', type: 'application/pdf', size: MAX_PDF_SIZE + 1 })).toBeTruthy()
    expect(fileError({ name: 'x.pdf', type: 'application/pdf', size: MAX_PDF_SIZE })).toBe('')
    expect(nextDay('2028-02-28')).toBe('2028-02-29')
  })

  it('manda FormData sin forzar Content-Type y con credenciales', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(contract))
    await uploadContract(contract.id, { file: new File(['%PDF-'], 'a.pdf'), signed: true, revision: 1 })
    const options = fetch.mock.calls[0][1]
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.headers['Content-Type']).toBeUndefined()
    expect(options.credentials).toBe('include')
    expect(options.body.get('firmado')).toBe('true')
  })

  it('guarda borrador sin archivo y no pide fecha de firma', async () => {
    const ui = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
      if (url.includes('/inquilinos/tenant-one')) return json(tenant)
      if (url.endsWith('/contratos') && options.method === 'POST') return json(contract, 201)
      return json(contract)
    })
    renderRoute('/contratos/nuevo?inquilino_id=tenant-one')
    await screen.findByLabelText(/Inicio de vigencia/)
    expect(screen.queryByLabelText(/fecha de firma/i)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Inicio de vigencia/), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByLabelText(/Fin de vigencia/), { target: { value: '2027-08-31' } })
    await ui.click(screen.getByRole('button', { name: 'Guardar borrador' }))
    expect(await screen.findByText('El borrador se guardó. Podés completar el PDF firmado más adelante.')).toBeInTheDocument()
    expect(fetch.mock.calls.filter(([url, options]) => url.endsWith('/contratos') && options.method === 'POST')).toHaveLength(1)
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/documentos'))).toBe(false)
  })

  it('no duplica el contrato si falla la subida posterior al alta', async () => {
    const ui = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
      if (url.includes('/inquilinos/tenant-one')) return json(tenant)
      if (url.endsWith('/documentos')) return json({ detail: { message: 'Storage no disponible' } }, 503)
      if (url.endsWith('/contratos') && options.method === 'POST') return json(contract, 201)
      return json(contract)
    })
    renderRoute('/contratos/nuevo?inquilino_id=tenant-one')
    await screen.findByLabelText(/Inicio de vigencia/)
    fireEvent.change(screen.getByLabelText(/Inicio de vigencia/), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByLabelText(/Fin de vigencia/), { target: { value: '2027-08-31' } })
    await ui.upload(screen.getByLabelText('Documento del contrato'), new File(['%PDF-'], 'contrato.pdf', { type: 'application/pdf' }))
    await ui.click(screen.getByRole('checkbox'))
    await ui.click(screen.getByRole('button', { name: 'Guardar contrato firmado' }))
    expect(await screen.findByText(/Los datos quedaron guardados, pero no se pudo cargar el PDF/)).toBeInTheDocument()
    expect(screen.getByLabelText('Adjuntar documento')).toBeInTheDocument()
    expect(fetch.mock.calls.filter(([url, options]) => url.endsWith('/contratos') && options.method === 'POST')).toHaveLength(1)
  })

  it('muestra errores de validación y no envía un período inválido', async () => {
    const ui = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(tenant))
    renderRoute('/contratos/nuevo?inquilino_id=tenant-one')
    await screen.findByLabelText(/Inicio de vigencia/)
    fireEvent.change(screen.getByLabelText(/Inicio de vigencia/), { target: { value: '2027-09-01' } })
    fireEvent.change(screen.getByLabelText(/Fin de vigencia/), { target: { value: '2026-08-31' } })
    await ui.click(screen.getByRole('button', { name: 'Guardar borrador' }))
    expect(screen.getByText('La finalización debe ser posterior al inicio.')).toBeInTheDocument()
    expect(fetch.mock.calls.every(([, options]) => options.method !== 'POST')).toBe(true)
  })

  it('impide confirmar firmado sin PDF', async () => {
    const ui = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(tenant))
    renderRoute('/contratos/nuevo?inquilino_id=tenant-one')
    await screen.findByLabelText(/Inicio de vigencia/)
    await ui.click(screen.getByRole('checkbox'))
    await ui.click(screen.getByRole('button', { name: 'Guardar contrato firmado' }))
    expect(screen.getByText('Seleccioná el PDF del contrato.')).toBeInTheDocument()
  })

  it('prepara una renovación sin modificar el contrato anterior', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...contract, estado: 'firmado' }))
    renderRoute('/contratos/nuevo?anterior=contract-one')
    expect(await screen.findByLabelText(/Inicio de vigencia/)).toHaveValue('2027-09-01')
    expect(screen.getByLabelText(/Fin de vigencia/)).toHaveValue('')
    expect(screen.queryByRole('button', { name: 'Cambiar inquilino' })).not.toBeInTheDocument()
  })
})

describe('consulta y gestión de contratos', () => {
  it.each(['inquilino', 'propietario'])('solo ofrece lectura al %s', async role => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...contract, estado: 'firmado', vigencia: 'Vigente', documentos: [{ id: 'doc-one', version: 1, nombre_archivo: 'contrato.pdf', tamano: 500, firmado: true, created_at: '2026-09-12' }] }))
    renderRoute(`/${role}/contratos/contract-one`, role)
    expect(await screen.findByRole('button', { name: 'Descargar versión 1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar PDF' })).not.toBeInTheDocument()
    expect(screen.queryByText('Registrar renovación')).not.toBeInTheDocument()
    expect(screen.queryByText('Editar borrador')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Fecha de finalización')).not.toBeInTheDocument()
  })

  it('un error en una búsqueda no deja resultados de los filtros anteriores', async () => {
    const ui = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
      if (url.includes('search=')) return json({ detail: 'No se pudo actualizar la búsqueda.' }, 503)
      return json({ items: [contract], total: 1, page: 1, page_size: 10, total_pages: 1 })
    })
    renderRoute('/contratos')
    expect(await screen.findByText(contract.direccion)).toBeInTheDocument()
    await ui.type(screen.getByLabelText('Buscar contratos'), 'Otro')
    await waitFor(() => expect(screen.getByText('No se pudo actualizar la búsqueda.')).toBeInTheDocument())
    expect(screen.queryByText(contract.direccion)).not.toBeInTheDocument()
  })

  it('no permite editar las fechas de un contrato firmado por URL directa', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...contract, estado: 'firmado' }))
    renderRoute('/contratos/contract-one/editar')
    expect(await screen.findByText('Solo se pueden editar las fechas de un borrador.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Guardar/ })).not.toBeInTheDocument()
  })
})
