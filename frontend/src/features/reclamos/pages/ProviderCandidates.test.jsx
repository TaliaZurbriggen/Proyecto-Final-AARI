import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PendingAssignmentPage from './PendingAssignmentPage.jsx'
import ProviderCandidatesPage from './ProviderCandidatesPage.jsx'

const id = '00000000-0000-0000-0000-000000000101'
const specialty = '00000000-0000-0000-0000-000000000201'
const provider = {
  id: '00000000-0000-0000-0000-000000000301', nombre_razon_social: 'Proveedor Sintetico',
  telefono: '+543564000001', hora_inicio: '08:00:00', hora_fin: '17:00:00',
  especialidades: [{ id: specialty, nombre: 'Plomería' }],
}
const claim = {
  id, numero: 42, descripcion: 'Pérdida sintética en la canilla.',
  creado_en: '2026-10-09T12:00:00Z', updated_at: '2026-10-09T12:00:00.000001Z',
  estado: 'Pendiente de asignación', tipo_gasto: 'ordinario', puede_buscar: true,
  propiedad: { direccion: 'Unidad ficticia 100', provincia: 'Córdoba', localidad: 'Localidad de prueba', tipo: 'casa', barrio: 'Centro' },
  especialidad: null, resultado: 'especialidad_pendiente',
  candidatos: [], total: 0, page: 1, page_size: 20, total_pages: 1, historial_busquedas: [], historial_total: 0,
}
const queue = { items: [claim], total: 21, page: 2, page_size: 20, total_pages: 2 }
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
function show({ detail = false, operator = false, query = '' } = {}) {
  const base = operator ? '/operador/pendientes-asignacion' : '/pendientes-asignacion'
  render(<MemoryRouter initialEntries={[`${base}${detail ? `/${id}` : ''}${query}`]}><Routes>
    <Route path={base} element={<PendingAssignmentPage operatorView={operator} />} />
    <Route path={`${base}/:reclamoId`} element={<ProviderCandidatesPage operatorView={operator} />} />
  </Routes></MemoryRouter>)
}
function installFetch({ detail = claim, post } = {}) {
  const mock = vi.fn().mockImplementation((url, options = {}) => {
    if (options.method === 'POST') return post ? post(url, options) : Promise.resolve(json({ resultado: 'sin_candidatos', aviso_operador: 'encolado' }))
    const path = new URL(url).pathname
    return Promise.resolve(json(path.endsWith('especialidades-proveedores')
      ? [{ id: specialty, nombre: 'Plomería' }]
      : path.endsWith('proveedores-candidatos') ? detail : queue))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
afterEach(() => vi.unstubAllGlobals())

describe('HU15: asignación y candidatos', () => {
  it.each([false, true])('conserva búsqueda y página usando el detalle real (operador %s)', async (operator) => {
    const user = userEvent.setup()
    const fetch = installFetch()
    show({ operator, query: '?page=2&search=canilla' })
    const link = await screen.findByRole('link', { name: 'Revisar proveedores del reclamo #000042' })
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
    link.focus()
    await user.keyboard('{Enter}')
    await screen.findByRole('heading', { name: 'Proveedores para #000042' })
    await user.click(screen.getByRole('link', { name: 'Volver a pendientes de asignación' }))
    expect(await screen.findByRole('searchbox')).toHaveValue('canilla')
    expect(await screen.findByText('Página 2 de 2')).toBeInTheDocument()
    expect(fetch.mock.calls.every(([, options]) => !options.method)).toBe(true)
  })

  it('acceso directo tiene retorno seguro y no registra búsquedas al leer', async () => {
    const fetch = installFetch()
    show({ detail: true, query: '?page=-1&return=https://example.com' })
    expect(await screen.findByRole('link', { name: 'Volver a pendientes de asignación' }))
      .toHaveAttribute('href', '/pendientes-asignacion?page=1&search=')
    expect(await screen.findByLabelText(/Especialidad requerida/)).toHaveValue('')
    expect(screen.getByText(/Abrir esta pantalla no registra/)).toBeInTheDocument()
    expect(fetch.mock.calls.every(([, options]) => options.method !== 'POST')).toBe(true)
  })

  it('valida el catálogo antes de escribir y guarda especialidad + versión + idempotencia', async () => {
    const user = userEvent.setup()
    const fetch = installFetch()
    show({ detail: true })
    const button = await screen.findByRole('button', { name: 'Guardar especialidad y buscar' })
    await user.click(button)
    expect(screen.getByText('Seleccioná la especialidad requerida.')).toBeInTheDocument()
    expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(0)
    await user.selectOptions(screen.getByLabelText(/Especialidad requerida/), specialty)
    await user.click(button)
    await screen.findByText(/Aviso al operador encolado/)
    const [, options] = fetch.mock.calls.find(([, o]) => o.method === 'POST')
    const body = JSON.parse(options.body)
    expect(body).toEqual({ especialidad_id: specialty, expected_updated_at: claim.updated_at, request_id: expect.any(String) })
    expect(body.request_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(body).not.toHaveProperty('autorizado')
  })

  it('reintento de red mantiene el ID para no duplicar el intento', async () => {
    const user = userEvent.setup()
    const fetch = installFetch({ post: () => Promise.reject(new TypeError('Fallo sintético')) })
    show({ detail: true })
    await user.selectOptions(await screen.findByLabelText(/Especialidad requerida/), specialty)
    await user.click(screen.getByRole('button', { name: 'Guardar especialidad y buscar' }))
    await screen.findByText(/No pudimos conectarnos/)
    await user.click(screen.getByRole('button', { name: 'Guardar especialidad y buscar' }))
    await waitFor(() => expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(2))
    const bodies = fetch.mock.calls.filter(([, o]) => o.method === 'POST').map(([, o]) => JSON.parse(o.body))
    expect(bodies[0].request_id).toBe(bodies[1].request_id)
  })

  it.each([409, 422])('muestra rechazo del servidor (%s) y no afirma que guardó', async (status) => {
    const user = userEvent.setup()
    installFetch({ post: () => Promise.resolve(json({ detail: {
      message: 'Actualizá el dato antes de continuar.', field: status === 422 ? 'especialidad_id' : undefined,
    } }, status)) })
    show({ detail: true })
    await user.selectOptions(await screen.findByLabelText(/Especialidad requerida/), specialty)
    await user.click(screen.getByRole('button', { name: 'Guardar especialidad y buscar' }))
    expect(await screen.findByText('Actualizá el dato antes de continuar.')).toBeInTheDocument()
    expect(screen.queryByText(/Aviso al operador encolado/)).not.toBeInTheDocument()
    if (status === 422) expect(screen.getByLabelText(/Especialidad requerida/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('no ofrece guardar en un reclamo cerrado', async () => {
    installFetch({ detail: { ...claim, estado: 'Resuelto', puede_buscar: false } })
    show({ detail: true })
    expect(await screen.findByRole('button', { name: 'Guardar especialidad y buscar' })).toBeDisabled()
    expect(screen.getByText(/El reclamo está cerrado/)).toBeInTheDocument()
  })

  it('permite obtener candidatos desde Recibido sin autorización ni clasificación de gasto', async () => {
    installFetch({ detail: { ...claim, estado: 'Recibido', tipo_gasto: null,
      tarea_agente: 'revision', motivo_agente: 'Falta identificar la especialidad.' } })
    show({ detail: true })
    expect(await screen.findByRole('button', { name: 'Guardar especialidad y buscar' })).toBeEnabled()
    expect(screen.getByText(/La búsqueda necesita revisión/)).toBeInTheDocument()
    expect(screen.queryByText(/decisiones previas/)).not.toBeInTheDocument()
  })

  it('muestra el resultado automático sin obligar a buscar manualmente', async () => {
    installFetch({ detail: { ...claim, tarea_agente: 'completada', estado: 'Recibido', tipo_gasto: null,
      especialidad: { id: specialty, nombre: 'Plomería' }, resultado: 'candidatos_encontrados',
      total: 1, candidatos: [provider] } })
    show({ detail: true })
    expect(await screen.findByText(/El agente completó la búsqueda/)).toBeInTheDocument()
    expect(screen.getByText('Proveedor Sintetico')).toBeInTheDocument()
    expect(screen.getByText('Corregir especialidad o repetir búsqueda').closest('details')).not.toHaveAttribute('open')
  })

  it.each(['pendiente', 'procesando'])('explica el estado del agente (%s) sin afirmar que terminó', async (state) => {
    installFetch({ detail: { ...claim, tarea_agente: state } })
    show({ detail: true })
    expect(await screen.findByText(state === 'pendiente' ? /pendiente de procesamiento/ : /El agente está identificando/)).toBeInTheDocument()
    expect(screen.queryByText(/El agente completó/)).not.toBeInTheDocument()
  })

  it('muestra horario como referencia y no promete disponibilidad o asignación', async () => {
    installFetch({ detail: { ...claim, especialidad: { id: specialty, nombre: 'Plomería' },
      resultado: 'candidatos_encontrados', total: 21, total_pages: 2, candidatos: [provider],
      propiedad: { ...claim.propiedad, barrio: null } } })
    show({ detail: true })
    expect(await screen.findByText('Proveedor Sintetico')).toBeInTheDocument()
    expect(screen.getByText('Horario habitual: 08:00 a 17:00')).toBeInTheDocument()
    expect(screen.getByText(/Sin barrio informado/)).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Paginación de candidatos' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Asignar|Reservar|WhatsApp/ })).not.toBeInTheDocument()
  })

  it('no mantiene resultados anteriores al fallar una nueva consulta', async () => {
    const user = userEvent.setup()
    let fail = false
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(
      fail ? json({ detail: { message: 'Fallo sintético de consulta' } }, 503) : json(queue),
    )))
    show()
    await screen.findByRole('table')
    fail = true
    await user.click(screen.getByRole('button', { name: 'Actualizar' }))
    await screen.findByText('Fallo sintético de consulta')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('audita faltantes y aclara cuando no se pudo encolar el aviso', async () => {
    installFetch({ detail: { ...claim, historial_total: 1, historial_busquedas: [{
      id: 'audit', buscado_en: '2026-10-09T13:00:00Z', origen: 'operador',
      resultado: 'sin_candidatos', candidato_ids: [], aviso_operador: 'sin_destinatario',
      provincia: 'Córdoba', localidad: 'Localidad de prueba', barrio: 'Centro',
    }] } })
    show({ detail: true })
    expect(await screen.findByText(/No se pudo encolar el aviso/)).toBeInTheDocument()
    expect(screen.getByText('Ver criterios e identificadores').closest('details')).toBeInTheDocument()
  })

  it('protege contra respuestas tardías al cambiar la búsqueda', async () => {
    const user = userEvent.setup()
    let resolve
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => new URL(url).searchParams.get('search') === ''
      ? new Promise((done) => { resolve = done })
      : Promise.resolve(json({ ...queue, items: [], total: 0, total_pages: 1 }))))
    show()
    await user.type(screen.getByRole('searchbox'), 'nuevo')
    await screen.findByText('Sin coincidencias')
    await act(async () => resolve(json(queue)))
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
