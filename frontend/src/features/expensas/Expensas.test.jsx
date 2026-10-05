import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../auth/authContext.js'
import ProtectedRoute from '../auth/ProtectedRoute.jsx'
import ExpensesListPage from './ExpensesListPage.jsx'
import ExpenseDetailPage from './ExpenseDetailPage.jsx'
import ExpenseLayout from './ExpenseLayout.jsx'

const property = { id: '4206c0bd-3bcd-4d72-8d1d-f1ce0ed641fa', direccion: 'Unidad sintética 100',
  provincia: 'Córdoba', localidad: 'Localidad de prueba', tipo: 'casa' }
const claim = { id: 'ac1fa08d-4a1c-4b40-a717-6682b656c96c', numero: 1,
  descripcion: 'Falla común informada.', estado: 'Derivado a inmobiliaria (expensa)',
  creado_en: '2026-10-01T12:00:00Z', propiedad: property, entrega_estado: 'enviado', intentos: 1 }
const page = { items: [claim], total: 25, page: 1, page_size: 20, total_pages: 2,
  pendientes: 0, fallidos: 0, sin_configuracion: 0, propiedades: [property] }
const report = { reclamo_id: claim.id, numero: 1, ingresado_en: claim.creado_en,
  clasificado_en: claim.creado_en, propiedad: property, inquilino: { nombre: 'Contacto de prueba', email: 'tenant@example.com' },
  descripcion: claim.descripcion, urgencia: 'media', tipo_gasto: 'expensa',
  fundamento: 'Evaluación de instalación común.', origen: 'agente', confianza: 0.95 }
const detail = { ...claim, reporte: report, notas: [], envios: [{ id: 'delivery', canal: 'email',
  destinatario: 'agency@example.com', estado: 'enviado', intentos: 1, enviado_en: claim.creado_en }] }

function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
function mockData(value = page) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((url) => Promise.resolve(response(
    new URL(url).pathname.includes('/configuracion/') ? { email: 'agency@example.com', configurado: true } : value,
  )))
}
function show(path = '/expensas', role = 'administrador', layout = false) {
  const user = role ? { id: 'user', email: 'admin@example.com', rol: role, primer_ingreso: false } : null
  return render(<AuthContext.Provider value={{ user, isLoading: false, logout: vi.fn() }}>
    <MemoryRouter initialEntries={[path]}><Routes>
      <Route element={<ProtectedRoute allowedRoles={['administrador', 'operador']} />}>
        {layout ? <Route element={<ExpenseLayout />}><Route path="expensas" element={<ExpensesListPage />} /></Route>
          : <Route path="expensas" element={<ExpensesListPage />} />}
        <Route path="expensas/:reclamoId" element={<ExpenseDetailPage />} />
      </Route>
      <Route path="login" element={<h1>Login de prueba</h1>} />
      <Route path="inquilino" element={<h1>Portal del inquilino</h1>} />
    </Routes></MemoryRouter>
  </AuthContext.Provider>)
}

afterEach(() => vi.restoreAllMocks())

describe('HU14 expensas', () => {
  it('muestra tabla, situación, total y configuración solo administrativa', async () => {
    mockData()
    show()
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByText('25 expensas · 20 por página')).toBeInTheDocument()
    expect(screen.getByText('Reporte enviado')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver expensa #000001' })).toHaveAttribute('href', `/expensas/${claim.id}?page=1&situacion=derivados`)
    expect(screen.getByText('Correo de la inmobiliaria')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Actualizar' })).toBeEnabled()
  })
  it('muestra alertas aun cuando la vista de derivados esté vacía', async () => {
    mockData({ ...page, items: [], total: 0, total_pages: 1, fallidos: 2, sin_configuracion: 1 })
    show()
    expect(await screen.findByText('No hay expensas en esta vista')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Reportes que agotaron los tres intentos: 2. Sin destinatario válido: 1.')
    expect(screen.getByRole('link', { name: 'Revisar reportes no enviados' })).toHaveAttribute('href', '/expensas?page=1&situacion=fallidos')
  })
  it('preserva filtros al paginar y en el retorno desde el detalle', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      const target = new URL(url)
      return Promise.resolve(response(target.pathname.endsWith(claim.id) ? detail
        : target.pathname.includes('/configuracion/') ? { email: null, configurado: false }
          : { ...page, page: Number(target.searchParams.get('page') || 1) }))
    })
    show(`/expensas?propiedad_id=${property.id}&fecha_desde=2026-10-01&fecha_hasta=2026-10-01`)
    await screen.findByRole('table')
    await user.selectOptions(screen.getByLabelText('Situación del reporte'), 'todos')
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText('Página 2 de 2')
    const link = screen.getByRole('link', { name: 'Ver expensa #000001' })
    expect(link.getAttribute('href')).toContain('situacion=todos')
    await user.click(link)
    await screen.findByRole('heading', { name: 'Expensa #000001' })
    await user.click(screen.getByRole('link', { name: 'Volver a expensas' }))
    await screen.findByText('Página 2 de 2')
    const request = fetchMock.mock.calls.filter(([url]) => new URL(url).pathname === '/expensas').at(-1)[0]
    expect(Object.fromEntries(new URL(request).searchParams)).toEqual({ page: '2', situacion: 'todos',
      propiedad_id: property.id, fecha_desde: '2026-10-01', fecha_hasta: '2026-10-01' })
  })
  it('agrega una nota privada con autor y fecha, sin aceptar espacios vacíos', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => Promise.resolve(response(
      new URL(url).pathname.endsWith('/notas') ? { id: 'note', contenido: 'Revisar circuito común.',
        autor: 'Operador sintético', usuario_id: 'user', creado_en: claim.creado_en } : detail,
    )))
    show(`/expensas/${claim.id}`, 'operador')
    await screen.findByRole('heading', { name: 'Notas internas' })
    expect(screen.getByRole('button', { name: 'Guardar nota' })).toBeDisabled()
    await user.type(screen.getByLabelText('Nueva nota interna'), '   ')
    expect(screen.getByRole('button', { name: 'Guardar nota' })).toBeDisabled()
    await user.clear(screen.getByLabelText('Nueva nota interna'))
    await user.type(screen.getByLabelText('Nueva nota interna'), 'Revisar circuito común.')
    await user.click(screen.getByRole('button', { name: 'Guardar nota' }))
    expect(await screen.findByText('Nota interna guardada.')).toBeInTheDocument()
    expect(screen.getByText('Revisar circuito común.')).toBeInTheDocument()
    expect(screen.getByText(/Operador sintético/)).toBeInTheDocument()
    const options = fetchMock.mock.calls.find(([url]) => new URL(url).pathname.endsWith('/notas'))[1]
    expect(JSON.parse(options.body)).toEqual({ contenido: 'Revisar circuito común.' })
  })
  it('explica históricos sin reporte ni envío retroactivo', async () => {
    mockData({ ...detail, reporte: null, entrega_estado: 'historico', envios: [] })
    show(`/expensas/${claim.id}`)
    expect(await screen.findByText(/Registro histórico sin reporte estructurado/)).toBeInTheDocument()
    expect(screen.getByText('No hay envíos registrados para esta expensa.')).toBeInTheDocument()
  })
  it('operador accede desde su layout sin consultar configuración administrativa', async () => {
    const fetchMock = mockData()
    show('/expensas', 'operador', true)
    await screen.findByRole('table')
    expect(screen.getByRole('link', { name: 'Expensas' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByText('Correo de la inmobiliaria')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => url.includes('/configuracion/'))).toBe(false)
  })
  it('bloquea inquilinos antes de consultar reportes', async () => {
    const fetchMock = mockData()
    show('/expensas', 'inquilino')
    expect(await screen.findByRole('heading', { name: 'Portal del inquilino' })).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('bloquea una sesión ausente', async () => {
    const fetchMock = mockData()
    show('/expensas', null)
    expect(await screen.findByRole('heading', { name: 'Login de prueba' })).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('rechaza un rango invertido sin solicitar expensas', async () => {
    const fetchMock = mockData()
    show('/expensas?fecha_desde=2026-10-02&fecha_hasta=2026-10-01', 'operador')
    expect(screen.getByRole('alert')).toHaveTextContent('La fecha desde no puede ser posterior')
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('muestra el error de detalle y conserva la vuelta con filtros', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ detail: { message: 'No encontramos esa expensa.' } }, 404))
    show(`/expensas/${claim.id}?situacion=fallidos&page=2`)
    expect(await screen.findByRole('alert')).toHaveTextContent('No encontramos esa expensa.')
    expect(screen.getByRole('link', { name: 'Volver a expensas' })).toHaveAttribute('href', '/expensas?situacion=fallidos&page=2')
  })
  it('descarta la respuesta vieja al cambiar la situación', async () => {
    const user = userEvent.setup()
    let resolveOld
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce(response({ ...page, items: [{ ...claim, numero: 9 }], total: 1, total_pages: 1 }))
    show('/expensas', 'operador')
    await user.selectOptions(screen.getByLabelText('Situación del reporte'), 'pendientes')
    await screen.findByRole('link', { name: 'Ver expensa #000009' })
    await act(async () => resolveOld(response(page)))
    expect(screen.queryByRole('link', { name: 'Ver expensa #000001' })).not.toBeInTheDocument()
  })
  it('permite configurar el contacto sin confundirlo con el remitente', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((url, options) => Promise.resolve(response(
      url.includes('/configuracion/') ? { email: options?.method === 'PUT' ? 'other@example.com' : 'agency@example.com', configurado: true } : page,
    )))
    show()
    await screen.findByRole('table')
    await user.click(screen.getByText('Correo de la inmobiliaria'))
    const input = await screen.findByRole('textbox', { name: 'Correo de contacto de la inmobiliaria', exact: true })
    await user.clear(input)
    await user.type(input, 'other@example.com')
    await user.click(screen.getByRole('button', { name: 'Guardar correo' }))
    expect(await screen.findByText(/Correo actualizado/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.find(([, options]) => options?.method === 'PUT')[1].body).toBe(JSON.stringify({ email: 'other@example.com' }))
  })
})
