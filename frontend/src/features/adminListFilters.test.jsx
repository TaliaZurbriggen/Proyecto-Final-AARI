import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PropiedadesListPage from './propiedades/pages/PropiedadesListPage.jsx'
import PropietariosListPage from './propietarios/pages/PropietariosListPage.jsx'
import InquilinosListPage from './inquilinos/pages/InquilinosListPage.jsx'
import AdminLayout from '../layouts/AdminLayout.jsx'
import { listQuery } from '../services/listQuery.js'

vi.mock('./auth/authContext.js', () => ({ useAuth: () => ({
  user: { email: 'admin@example.com', rol: 'administrador' }, logout: vi.fn(),
}) }))

const timestamp = '2026-10-05T12:00:00Z'
const person = { id: '00000000-0000-0000-0000-000000000001', nombre_completo: 'Persona Sintetica',
  dni: '10000001', email: 'person@example.com', telefono: '+543564000000',
  created_at: timestamp, updated_at: timestamp }
const property = { id: '00000000-0000-0000-0000-000000000002', direccion: 'Calle Ficticia 10',
  provincia: 'Córdoba', localidad: 'San Francisco', barrio: 'Centro', tipo: 'casa',
  propietario: person, piso: null, numero: null, cantidad_reclamos: 0,
  tiene_inquilino_activo: false, created_at: timestamp, updated_at: timestamp }
const cases = [
  { path: 'propiedades', Page: PropiedadesListPage, row: property, name: property.direccion,
    label: 'Tipo de inmueble', key: 'tipo', value: 'departamento', oldValue: 'casa' },
  { path: 'propietarios', Page: PropietariosListPage, row: { ...person, cantidad_inmuebles: 2 }, name: person.nombre_completo,
    label: 'Inmuebles asociados', key: 'con_inmuebles', value: 'false', oldValue: 'true', searchLabel: 'Buscar propietario' },
  { path: 'inquilinos', Page: InquilinosListPage, row: { ...person, propiedad: property, estado: 'activo', cantidad_reclamos: 0 },
    name: person.nombre_completo, label: 'Asignación de propiedad', key: 'estado', value: 'sin_propiedad_asignada', oldValue: 'activo', searchLabel: 'Buscar inquilino' },
]
const response = (row, status = 200, total = row ? 21 : 0, page = 1) => new Response(JSON.stringify(status === 200
  ? { items: row ? [row] : [], total, page, page_size: 10, total_pages: Math.ceil(total / 10) }
  : { detail: 'Consulta fallida de prueba.' }), { status, headers: { 'Content-Type': 'application/json' } })

function Detail() {
  const navigate = useNavigate()
  return <button onClick={() => navigate(-1)}>Volver al listado</button>
}
function Location() { return <output aria-label="URL actual">{useLocation().search}</output> }
function setup(testCase, suffix = '') {
  const { path, Page } = testCase
  render(<MemoryRouter initialEntries={[`/${path}${suffix}`]}>
    <Location /><Routes><Route element={<AdminLayout />}>
      <Route path={path} element={<Page />} />
      <Route path={`${path}/:id`} element={<Detail />} />
    </Route></Routes>
  </MemoryRouter>)
}
function requestedParams(fetchMock) { return new URL(fetchMock.mock.calls.at(-1)[0]).searchParams }
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe.each(cases)('filtros de $path', (testCase) => {
  it('restaura valores de la URL y pagina sin perderlos', async () => {
    const fetchMock = vi.fn(async () => response(testCase.row))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?${testCase.key}=${testCase.value}&search=Sintetica`)
    await screen.findByRole('link', { name: testCase.name, exact: true })
    expect(screen.getByLabelText(testCase.label)).toHaveValue(testCase.value)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(requestedParams(fetchMock).get('page')).toBe('2'))
    expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value)
    expect(requestedParams(fetchMock).get('search')).toBe('Sintetica')
  })

  it('aplica el borrador únicamente al confirmar y vuelve a la página uno', async () => {
    const fetchMock = vi.fn(async () => response(testCase.row))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, '?page=3&search=Prueba')
    await screen.findByRole('link', { name: testCase.name, exact: true })
    const user = userEvent.setup()
    const toggle = screen.getByRole('button', { name: /^Filtros/ })
    if (toggle.getAttribute('aria-expanded') === 'false') await user.click(toggle)
    const before = fetchMock.mock.calls.length
    await user.selectOptions(screen.getByLabelText(testCase.label), testCase.value)
    expect(fetchMock).toHaveBeenCalledTimes(before)
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value))
    expect(requestedParams(fetchMock).get('page')).toBe('1')
    expect(requestedParams(fetchMock).get('search')).toBe('Prueba')
  })

  it('el buscador de la cabecera conserva los filtros y reinicia la paginación', async () => {
    const fetchMock = vi.fn(async () => response(testCase.row))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?${testCase.key}=${testCase.value}&page=2`)
    await screen.findByRole('link', { name: testCase.name, exact: true })
    await userEvent.setup().type(screen.getByRole('searchbox'), 'Ana Sintetica')
    await waitFor(() => expect(requestedParams(fetchMock).get('search')).toBe('Ana Sintetica'))
    expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value)
    expect(requestedParams(fetchMock).get('page')).toBe('1')
  })

  it('limpia también un borrador que todavía no se aplicó', async () => {
    const fetchMock = vi.fn(async () => response(testCase.row))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase)
    await screen.findByRole('link', { name: testCase.name, exact: true })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /^Filtros/ }))
    await user.selectOptions(screen.getByLabelText(testCase.label), testCase.value)
    if (testCase.searchLabel) await user.type(screen.getByLabelText(testCase.searchLabel), 'Ana')
    await user.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(screen.getByLabelText(testCase.label)).toHaveValue('')
    if (testCase.searchLabel) expect(screen.getByLabelText(testCase.searchLabel)).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Limpiar filtros' })).toBeDisabled()
    expect(requestedParams(fetchMock).get(testCase.key)).toBeNull()
  })

  it('limpia búsqueda y filtros y no confunde sin resultados con base vacía', async () => {
    const fetchMock = vi.fn(async () => response(null))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?${testCase.key}=${testCase.value}&search=Ana&page=2`)
    expect(await screen.findByRole('heading', { name: 'Sin resultados' })).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Limpiar búsqueda y filtros' }))
    await waitFor(() => expect(screen.getByLabelText('URL actual')).toHaveTextContent(''))
    expect(requestedParams(fetchMock).get('search')).toBeNull()
    expect(requestedParams(fetchMock).get(testCase.key)).toBeNull()
  })

  it('conserva los filtros al abrir un detalle y volver', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(testCase.row)))
    setup(testCase, `?${testCase.key}=${testCase.value}&search=Ana&page=2`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('link', { name: testCase.name, exact: true }))
    await user.click(screen.getByRole('button', { name: 'Volver al listado' }))
    await screen.findByRole('link', { name: testCase.name, exact: true })
    expect(screen.getByLabelText(testCase.label)).toHaveValue(testCase.value)
    expect(screen.getByLabelText('URL actual')).toHaveTextContent('page=2')
  })

  it('retira resultados viejos si falla la consulta con nuevos filtros', async () => {
    const fetchMock = vi.fn().mockImplementationOnce(async () => response(testCase.row))
      .mockImplementation(async () => response(null, 503))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?${testCase.key}=${testCase.oldValue}`)
    await screen.findByRole('link', { name: testCase.name, exact: true })
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText(testCase.label), testCase.value)
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Consulta fallida de prueba.')
    expect(screen.queryByRole('link', { name: testCase.name, exact: true })).not.toBeInTheDocument()
  })

  it('ignora la respuesta atrasada de una consulta cancelada', async () => {
    let resolveOld
    let oldSignal
    const fetchMock = vi.fn().mockImplementationOnce((_, options) => {
      oldSignal = options.signal
      return new Promise((resolve) => { resolveOld = resolve })
    }).mockImplementation(async () => response(null))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?${testCase.key}=${testCase.oldValue}`)
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText(testCase.label), testCase.value)
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await screen.findByRole('heading', { name: 'Sin resultados' })
    expect(oldSignal.aborted).toBe(true)
    await act(async () => resolveOld(response(testCase.row)))
    expect(screen.queryByRole('link', { name: testCase.name, exact: true })).not.toBeInTheDocument()
  })

  it('recorre primera y última página conservando filtros, búsqueda y total', async () => {
    const fetchMock = vi.fn(async (url) => response(testCase.row, 200, 21, Number(new URL(url).searchParams.get('page'))))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?${testCase.key}=${testCase.value}&search=Sintetica`)
    await screen.findByText('Página 1 de 3')
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
    const user = userEvent.setup()
    for (const page of [2, 3]) {
      await user.click(screen.getByRole('button', { name: 'Siguiente' }))
      await screen.findByText(`Página ${page} de 3`)
      expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value)
      expect(requestedParams(fetchMock).get('search')).toBe('Sintetica')
      expect(screen.getByText('21 coincidencias')).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
    for (const page of [2, 1]) {
      await user.click(screen.getByRole('button', { name: 'Anterior' }))
      await screen.findByText(`Página ${page} de 3`)
    }
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
    expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value)
  })

  it.each(['0', '-2', 'texto', '1.5'])('trata la página inválida %s como la primera', async (page) => {
    const fetchMock = vi.fn(async () => response(testCase.row))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?page=${page}&${testCase.key}=${testCase.value}`)
    await screen.findByText('Página 1 de 3')
    expect(requestedParams(fetchMock).get('page')).toBe('1')
    expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value)
  })

  it('recupera una página fuera de rango sin perder la búsqueda ni filtros', async () => {
    const fetchMock = vi.fn(async (url) => {
      const page = Number(new URL(url).searchParams.get('page'))
      return response(page > 3 ? null : testCase.row, 200, 21, page)
    })
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?page=9&${testCase.key}=${testCase.value}&search=Sintetica`)
    await screen.findByText('Página 3 de 3')
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
    expect(requestedParams(fetchMock).get('page')).toBe('3')
    expect(requestedParams(fetchMock).get('search')).toBe('Sintetica')
    expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('vuelve a página uno cuando no hay coincidencias, sin mostrar navegación vacía', async () => {
    const fetchMock = vi.fn(async () => response(null))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?page=3&${testCase.key}=${testCase.value}`)
    await screen.findByRole('heading', { name: 'Sin resultados' })
    expect(requestedParams(fetchMock).get('page')).toBe('1')
    expect(screen.queryByRole('button', { name: 'Siguiente' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anterior' })).not.toBeInTheDocument()
  })

  it('recupera la última página válida si se elimina su único registro', async () => {
    let deleted = false
    const fetchMock = vi.fn(async (url, options) => {
      if (options.method === 'DELETE') {
        deleted = true
        return new Response(null, { status: 204 })
      }
      const page = Number(new URL(url).searchParams.get('page'))
      const total = deleted ? 20 : 21
      return response(deleted && page === 3 ? null : testCase.row, 200, total, page)
    })
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?page=3&${testCase.key}=${testCase.value}&search=Sintetica`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: `Eliminar ${testCase.name}`, exact: true }))
    const singular = { propiedades: 'propiedad', propietarios: 'propietario', inquilinos: 'inquilino' }[testCase.path]
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: `Eliminar ${singular}`, exact: true }))
    await screen.findByText('Página 2 de 2')
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
    expect(screen.getByText(/se eliminó correctamente/)).toBeInTheDocument()
    expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value)
    expect(requestedParams(fetchMock).get('search')).toBe('Sintetica')
    expect(requestedParams(fetchMock).get('page')).toBe('2')
  })
})

describe.each(cases.filter(({ searchLabel }) => searchLabel))('búsqueda visible de $path', (testCase) => {
  it('combina el nombre con filtros, sincroniza cabecera y reinicia página', async () => {
    const fetchMock = vi.fn(async () => response(testCase.row))
    vi.stubGlobal('fetch', fetchMock)
    setup(testCase, `?page=3&${testCase.key}=${testCase.value}&search=Anterior`)
    await screen.findByRole('link', { name: testCase.name, exact: true })
    const user = userEvent.setup()
    const input = screen.getByLabelText(testCase.searchLabel)
    expect(input).toHaveValue('Anterior')
    await user.clear(input)
    await user.type(input, '  Persona Sintetica  ')
    expect(requestedParams(fetchMock).get('search')).toBe('Anterior')
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(requestedParams(fetchMock).get('search')).toBe('Persona Sintetica'))
    expect(requestedParams(fetchMock).get('page')).toBe('1')
    expect(requestedParams(fetchMock).get(testCase.key)).toBe(testCase.value)
    expect(screen.getByRole('searchbox')).toHaveValue('Persona Sintetica')
    expect(screen.getByLabelText(testCase.searchLabel)).toHaveValue('Persona Sintetica')
    await user.clear(screen.getByRole('searchbox'))
    await user.type(screen.getByRole('searchbox'), 'Ana')
    await waitFor(() => expect(screen.getByLabelText(testCase.searchLabel)).toHaveValue('Ana'))
    await user.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    await waitFor(() => expect(screen.getByRole('searchbox')).toHaveValue(''))
    expect(requestedParams(fetchMock).get('search')).toBeNull()
    expect(requestedParams(fetchMock).get(testCase.key)).toBeNull()
  })
})

it('envía filtros false explícitos y omite vacíos', () => {
  const params = new URLSearchParams(listQuery({ page: 1, pageSize: 10, search: ' Ana ',
    filters: { con_inmuebles: false, localidad: '', propietario: ' owner@example.com ' } }))
  expect(params.get('con_inmuebles')).toBe('false')
  expect(params.get('localidad')).toBeNull()
  expect(params.get('propietario')).toBe('owner@example.com')
})
