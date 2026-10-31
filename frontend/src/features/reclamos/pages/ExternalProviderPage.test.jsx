import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ExternalProviderPage, { ExternalProviderHistory } from './ExternalProviderPage.jsx'
import ProviderChoicePage from './ProviderChoicePage.jsx'
import PropertyClaimDetailPage from './PropertyClaimDetailPage.jsx'
import { validateExternalProvider } from '../api/externalProvidersApi.js'

const id = '11bcb3e5-3804-4e97-a130-921d880b5280'
const choiceId = 'fd5e617e-6c06-41ab-adf1-ac38228bd830'
const record = { id: '60d05e22-0a57-4ac1-85c4-49da09171f99', nombre: 'Persona Sintética', telefono: '541155550100',
  created_at: '2026-10-29T18:00:00Z', actor_nombre: 'Responsable Sintético', eleccion_id: choiceId }
const detail = { reclamo_id: id, numero: 31, descripcion: 'Pérdida de agua en cañería.',
  estado: 'Pendiente de datos de proveedor propio', updated_at: '2026-10-29T17:00:00Z', eleccion_id: choiceId,
  propiedad: { id: '971eabce-599e-41d9-9e53-84438fb8c693', direccion: 'Unidad de prueba', localidad: 'Localidad Sintética' },
  puede_registrar: true, motivo_bloqueo: null, registro: null, registros: [] }
const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const saved = { reclamo_id: id, estado: 'Derivado a proveedor externo', registro: record }

function fixture(callback = () => null) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((url, opts = {}) => Promise.resolve(callback(String(url), opts)
    || json(opts.method === 'POST' ? saved : detail)))
}
function show(owner = false) {
  const role = owner ? 'propietario' : 'inquilino'
  return render(<MemoryRouter initialEntries={[`/${role}/reclamos/${id}/proveedor-externo`]}><Routes>
    <Route path={`/${role}/reclamos/:reclamoId/proveedor-externo`} element={<ExternalProviderPage ownerView={owner} />} />
  </Routes></MemoryRouter>)
}
async function fill() {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Nombre completo', { exact: false }), 'Persona Sintética')
  await user.type(screen.getByLabelText('Teléfono', { exact: false }), '+54 (11) 5555-0100')
  return user
}
afterEach(() => vi.restoreAllMocks())

describe('HU18 formulario y normalización', () => {
  it.each(['', '43428013', 'Juan123', '<script>'])('rechaza nombre inválido %s', (nombre) => {
    expect(validateExternalProvider({ nombre, telefono: '12345678' }).errors.nombre).toBeTruthy()
  })
  it.each(['1234567', '1234567890123456', '1234hola5678', '54+1155550100', '１２３４５６７８'])('rechaza teléfono inválido %s', (telefono) => {
    expect(validateExternalProvider({ nombre: 'Persona Sintética', telefono }).errors.telefono).toBeTruthy()
  })
  it('normaliza acentos, espacios y formato de teléfono sin eliminar letras silenciosamente', () => {
    expect(validateExternalProvider({ nombre: '  Jose\u0301   Pérez ', telefono: '+54 (11) 5555-0100' })).toEqual({ errors: {}, normalized: { nombre: 'José Pérez', telefono: '541155550100' } })
  })
  it('los campos vacíos no envían y devuelven el foco al primero', async () => {
    const fetch = fixture()
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'Confirmar datos del proveedor' }))
    expect(screen.getByLabelText('Nombre completo', { exact: false })).toHaveFocus()
    expect(screen.getByLabelText('Teléfono', { exact: false })).toHaveAttribute('aria-invalid', 'true')
    expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  })
  it.each([false, true])('confirma en un paso y conserva el contacto tras recargar (propietario=%s)', async (owner) => {
    let registered = false
    const fetch = fixture((_url, opts) => {
      if (opts.method === 'POST') { registered = true; return json(saved) }
      return json(registered ? { ...detail, estado: saved.estado, registro: record, registros: [record], puede_registrar: false } : detail)
    })
    const view = show(owner)
    const user = await fill()
    expect(screen.queryByRole('button', { name: 'Revisar datos' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Volver a la elección de proveedor' })).toHaveAttribute('href', `/${owner ? 'propietario' : 'inquilino'}/reclamos/${id}/tipo-proveedor`)
    await user.click(screen.getByRole('button', { name: 'Confirmar datos del proveedor' }))
    expect(await screen.findByRole('heading', { name: 'Contacto confirmado' })).toBeVisible()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Contacto confirmado' })).toHaveFocus())
    const success = screen.getByText(/Proveedor externo confirmado:/)
    expect(success).toHaveTextContent('Proveedor externo confirmado: Persona Sintética atenderá este reclamo.')
    expect(success.querySelector('strong')).toHaveTextContent(record.nombre)
    const posts = fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST')
    expect(JSON.parse(posts[0][1].body)).toEqual({ request_id: expect.any(String), eleccion_id: choiceId,
      expected_updated_at: detail.updated_at, nombre: 'Persona Sintética', telefono: '541155550100' })
    view.unmount()
    show(owner)
    expect(await screen.findByText('Responsable Sintético')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Confirmar datos del proveedor' })).not.toBeInTheDocument()
    expect(fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(1)
  })
  it('una respuesta perdida conserva el UUID y bloquea editar los datos del reintento', async () => {
    let posts = 0
    const fetch = fixture((_url, options) => options.method === 'POST'
      ? ++posts === 1 ? Promise.reject(new TypeError('network')) : json(saved) : null)
    show()
    const user = await fill()
    await user.click(screen.getByRole('button', { name: 'Confirmar datos del proveedor' }))
    expect(await screen.findByRole('button', { name: 'Reintentar confirmación' })).toBeVisible()
    expect(screen.getByLabelText('Nombre completo', { exact: false })).toBeDisabled()
    expect(screen.getByLabelText('Teléfono', { exact: false })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Reintentar confirmación' }))
    expect(await screen.findByRole('heading', { name: 'Contacto confirmado' })).toBeVisible()
    const bodies = fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST').map(([, opts]) => JSON.parse(opts.body))
    expect(bodies).toHaveLength(2)
    expect(bodies[0]).toEqual(bodies[1])
  })
  it('doble confirmación envía una sola operación', async () => {
    let finish
    const fetch = fixture((_url, opts) => opts.method === 'POST' ? new Promise(resolve => { finish = resolve }) : null)
    show()
    await fill()
    const button = screen.getByRole('button', { name: 'Confirmar datos del proveedor' })
    fireEvent.click(button); fireEvent.click(button)
    expect(fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(1)
    expect(screen.getByLabelText('Nombre completo', { exact: false })).toBeDisabled()
    expect(screen.getByLabelText('Teléfono', { exact: false })).toBeDisabled()
    await act(async () => finish(json(saved)))
    expect(screen.getByRole('heading', { name: 'Contacto confirmado' })).toBeVisible()
  })
  it('no muestra formulario si el reclamo dejó de admitir la operación', async () => {
    fixture(() => json({ ...detail, puede_registrar: false, motivo_bloqueo: 'El reclamo ya fue resuelto.', estado: 'Resuelto' }))
    show()
    expect(await screen.findByText('El reclamo ya fue resuelto.')).toBeVisible()
    expect(screen.queryByLabelText('Nombre completo', { exact: false })).not.toBeInTheDocument()
  })
  it('un conflicto vuelve a consultar y no sobrescribe una confirmación ajena', async () => {
    let conflict = false
    fixture((_url, opts) => {
      if (opts.method === 'POST') { conflict = true; return json({ detail: { message: 'El reclamo cambió.' } }, 409) }
      return json(conflict ? { ...detail, puede_registrar: false, motivo_bloqueo: 'La etapa cambió.', estado: 'Resuelto' } : detail)
    })
    show()
    const user = await fill()
    await user.click(screen.getByRole('button', { name: 'Confirmar datos del proveedor' }))
    expect(await screen.findByText('La etapa cambió.')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Confirmar datos del proveedor' })).not.toBeInTheDocument()
  })
  it('un acceso denegado no muestra datos ni el formulario', async () => {
    fixture(() => json({ detail: { message: 'No encontramos ese reclamo para tu cuenta.' } }, 404))
    show()
    expect(await screen.findByText('No encontramos ese reclamo para tu cuenta.')).toBeVisible()
    expect(screen.queryByText(detail.descripcion)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Teléfono', { exact: false })).not.toBeInTheDocument()
  })
  it('un nombre numérico se rechaza en el formulario sin guardar', async () => {
    const fetch = fixture()
    show()
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Nombre completo', { exact: false }), '43428013')
    await user.type(screen.getByLabelText('Teléfono', { exact: false }), '12345678')
    await user.click(screen.getByRole('button', { name: 'Confirmar datos del proveedor' }))
    expect(screen.getByLabelText('Nombre completo', { exact: false })).toHaveFocus()
    expect(screen.getByText(/Ingresá un nombre completo/)).toBeVisible()
    expect(fetch.mock.calls.some(([, opts]) => opts?.method === 'POST')).toBe(false)
  })
  it('un 422 permite corregir en el mismo formulario y confirmar con un UUID nuevo', async () => {
    let posts = 0
    const fetch = fixture((_url, opts) => opts.method === 'POST' && ++posts === 1
      ? json({ detail: [{ loc: ['body', 'telefono'], msg: 'Revisá este teléfono.' }] }, 422) : null)
    show()
    const user = await fill()
    await user.click(screen.getByRole('button', { name: 'Confirmar datos del proveedor' }))
    expect(await screen.findByText('Revisá este teléfono.')).toBeVisible()
    const phone = screen.getByLabelText('Teléfono', { exact: false })
    await waitFor(() => expect(phone).toHaveFocus())
    expect(phone).toBeEnabled()
    await user.clear(phone)
    await user.type(phone, '12345678')
    await user.click(screen.getByRole('button', { name: 'Confirmar datos del proveedor' }))
    expect(await screen.findByRole('heading', { name: 'Contacto confirmado' })).toBeVisible()
    const bodies = fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST').map(([, opts]) => JSON.parse(opts.body))
    expect(bodies).toHaveLength(2)
    expect(bodies[1].telefono).toBe('12345678')
    expect(bodies[1].request_id).not.toBe(bodies[0].request_id)
  })
  it('un 503 conserva datos y UUID al reintentar desde el mismo formulario', async () => {
    let posts = 0
    const fetch = fixture((_url, opts) => opts.method === 'POST' && ++posts === 1
      ? json({ detail: { message: 'No se pudo confirmar el guardado.' } }, 503) : null)
    show()
    const user = await fill()
    await user.click(screen.getByRole('button', { name: 'Confirmar datos del proveedor' }))
    expect(await screen.findByRole('button', { name: 'Reintentar confirmación' })).toBeVisible()
    expect(screen.getByLabelText('Nombre completo', { exact: false })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Reintentar confirmación' }))
    expect(await screen.findByRole('heading', { name: 'Contacto confirmado' })).toBeVisible()
    const bodies = fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST').map(([, opts]) => JSON.parse(opts.body))
    expect(bodies).toHaveLength(2)
    expect(bodies[0]).toEqual(bodies[1])
  })
  it('consultar tras una respuesta perdida recupera la confirmación sin otro POST', async () => {
    let stored = false
    const fetch = fixture((_url, opts) => {
      if (opts.method === 'POST') { stored = true; return Promise.reject(new TypeError('network')) }
      return json(stored ? { ...detail, registro: record, registros: [record], puede_registrar: false, estado: saved.estado } : detail)
    })
    show()
    const user = await fill()
    await user.click(screen.getByRole('button', { name: 'Confirmar datos del proveedor' }))
    await user.click(await screen.findByRole('button', { name: 'Consultar estado' }))
    expect(await screen.findByText(/Proveedor externo confirmado:/)).toHaveTextContent(record.nombre)
    expect(screen.queryByRole('button', { name: 'Reintentar confirmación' })).not.toBeInTheDocument()
    expect(fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(1)
  })
})

describe('HU18 integración de navegación e historial', () => {
  it('la elección real de proveedor propio lleva al formulario real', async () => {
    fixture((url) => json(url.includes('/tipo-proveedor') ? { ...detail, solicitud_id: choiceId, actor_tipo: 'inquilino', decision: {
      tipo_proveedor: 'propio', actor_nombre: 'Responsable Sintético', decidido_en: detail.updated_at } } : detail))
    render(<MemoryRouter initialEntries={[`/inquilino/reclamos/${id}/tipo-proveedor`]}><Routes>
      <Route path="/inquilino/reclamos/:reclamoId/tipo-proveedor" element={<ProviderChoicePage />} />
      <Route path="/inquilino/reclamos/:reclamoId/proveedor-externo" element={<ExternalProviderPage />} />
    </Routes></MemoryRouter>)
    await userEvent.click(await screen.findByRole('link', { name: 'Cargar datos del proveedor' }))
    expect(await screen.findByRole('heading', { name: 'Cargá los datos de tu proveedor' })).toBeVisible()
    expect(await screen.findByLabelText('Teléfono', { exact: false })).toBeVisible()
  })
  it('admin ve el contacto desde el detalle real y el inquilino del historial no lo hereda', async () => {
    const claim = { ...detail, id, estado: 'Derivado a proveedor externo', urgencia: 'media', tipo_gasto: 'ordinario',
      creado_en: detail.updated_at, historial: [{ estado_nuevo: 'Derivado a proveedor externo', timestamp: detail.updated_at, origen: 'inquilino' }] }
    const fetch = fixture(url => json(url.includes('/proveedor-externo') ? { ...detail, registros: [record] } : claim))
    const mount = (tenant) => render(<MemoryRouter initialEntries={[`/propiedades/${detail.propiedad.id}/reclamos/${id}?page=2`]}><Routes>
      <Route path="/propiedades/:propiedadId/reclamos/:reclamoId" element={<PropertyClaimDetailPage tenantView={tenant} />} />
    </Routes></MemoryRouter>)
    const view = mount(false)
    expect(await screen.findByText('Responsable Sintético')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Volver al historial' })).toHaveAttribute('href', `/propiedades/${detail.propiedad.id}/reclamos?page=2`)
    view.unmount(); fetch.mockClear(); mount(true)
    await screen.findByRole('heading', { name: 'Reclamo #000031' })
    expect(screen.queryByText('541155550100')).not.toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/proveedor-externo'))).toBe(false)
  })
  it('un registro legado conserva la ausencia de autor sin inventarlo', async () => {
    fixture(() => json({ ...detail, registros: [{ ...record, actor_nombre: null, eleccion_id: null }] }))
    render(<ExternalProviderHistory claimId={id} />)
    expect(await screen.findByText('Registro histórico sin autor informado')).toBeVisible()
  })
})
