import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import EscalatedClaimsPage from './EscalatedClaimsPage.jsx'
import EscalatedClaimDetailPage from './EscalatedClaimDetailPage.jsx'
import { validateManualDecision, escalationReason } from '../escalados.js'

const claim = {
  id: '00000000-0000-0000-0000-000000000101', numero: 25,
  descripcion: 'La canilla pierde agua, pero todavía no se pudo confirmar la causa.',
  estado: 'Escalado', urgencia: 'media', creado_en: '2026-10-01T10:00:00Z',
  escalado_en: '2026-10-01T12:00:00Z', updated_at: '2026-10-01T12:00:00.123456Z',
  motivo_escalado: 'confianza_insuficiente', confianza_clasificacion: 0.55,
  fundamento_clasificacion: 'No se confirmó si hay desgaste o mal uso.',
  propiedad: { direccion: 'Unidad de prueba 100', provincia: 'Córdoba', localidad: 'Localidad de prueba', tipo: 'casa' },
  inquilino_nombre: 'Inquilino de prueba', puede_resolver: true, fotos: [], decisiones: [],
  historial: [{ estado_nuevo: 'Escalado', estado_anterior: 'Recibido', origen: 'agente', timestamp: '2026-10-01T12:00:00Z' }],
}
const page = { items: [claim], total: 1, page: 1, page_size: 20, total_pages: 1 }
function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
function show({ detail = false, operator = false, query = '' } = {}) {
  const base = operator ? '/operador/escalados' : '/escalados'
  return render(<MemoryRouter initialEntries={[`${base}${detail ? `/${claim.id}` : ''}${query}`]}><Routes>
    <Route path={base} element={<EscalatedClaimsPage operatorView={operator} />} />
    <Route path={`${base}/:reclamoId`} element={<EscalatedClaimDetailPage operatorView={operator} />} />
  </Routes></MemoryRouter>)
}
afterEach(() => vi.restoreAllMocks())

describe('cola de revisión humana', () => {
  it('muestra columnas y motivo claro, conservando el acceso del operador', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(page))
    show({ operator: true })
    await screen.findByRole('table')
    expect(screen.getByText('Motivo de revisión')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Acciones' })).toBeInTheDocument()
    expect(screen.getByText(escalationReason('confianza_insuficiente'))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Revisar reclamo #000025' })).toHaveAttribute('href', `/operador/escalados/${claim.id}?page=1&search=`)
    expect(screen.getByRole('link', { name: 'Resolver clasificación del reclamo #000025' }))
      .toHaveAttribute('href', `/operador/escalados/${claim.id}?page=1&search=`)
  })

  it.each([false, true])('abre y vuelve sin perder búsqueda o página ni guardar una decisión (operador: %s)', async (operator) => {
    const user = userEvent.setup()
    const base = operator ? '/operador/escalados' : '/escalados'
    const query = new URLSearchParams({ page: '2', search: 'canilla de prueba' }).toString()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => Promise.resolve(response(
      new URL(url).pathname.endsWith(claim.id) ? claim : { ...page, page: 2, total: 21, total_pages: 2 },
    )))
    show({ operator, query: `?${query}` })
    const action = await screen.findByRole('link', { name: 'Resolver clasificación del reclamo #000025' })
    expect(action).toHaveTextContent('Resolver clasificación')
    expect(action).toHaveAttribute('href', `${base}/${claim.id}?${query}`)
    action.focus()
    expect(action).toHaveFocus()
    await user.keyboard('{Enter}')
    await screen.findByRole('heading', { name: 'Reclamo #000025' })
    const back = screen.getByRole('link', { name: 'Volver a casos escalados' })
    expect(back).toHaveAttribute('href', `${base}?${query}`)
    await user.click(back)
    expect(await screen.findByRole('searchbox', { name: 'Buscar casos escalados' })).toHaveValue('canilla de prueba')
    expect(await screen.findByText('Página 2 de 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeEnabled()
    expect(fetchMock.mock.calls.every(([, options]) => (options.method ?? 'GET') === 'GET')).toBe(true)
    expect(new URL(fetchMock.mock.calls.at(-1)[0]).search).toBe(`?${query}`)
  })

  it('identifica la acción de cada caso y conserva el acceso por número', async () => {
    const another = { ...claim, id: '00000000-0000-0000-0000-000000000102', numero: 26 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ ...page, items: [claim, another], total: 2 }))
    show()
    await screen.findByRole('table')
    for (const item of [claim, another]) {
      const number = `#${String(item.numero).padStart(6, '0')}`
      expect(screen.getByRole('link', { name: `Resolver clasificación del reclamo ${number}` }))
        .toHaveAttribute('href', `/escalados/${item.id}?page=1&search=`)
      expect(screen.getByRole('link', { name: `Revisar reclamo ${number}` }))
        .toHaveAttribute('href', `/escalados/${item.id}?page=1&search=`)
    }
  })

  it('permite búsqueda y paginación sin mostrar resultados viejos cuando falla', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => Promise.resolve(
      new URL(url).searchParams.get('search') ? response({ detail: { message: 'No pudimos buscar.' } }, 503) : response({ ...page, total: 21, total_pages: 2 }),
    ))
    show({ query: '?page=2' })
    await screen.findByRole('table')
    await user.type(screen.getByRole('searchbox', { name: 'Buscar casos escalados' }), 'canilla')
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos buscar.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(new URL(fetchMock.mock.calls.at(-1)[0]).searchParams.get('page')).toBe('1')
  })

  it('ignora una respuesta tardía de una búsqueda anterior', async () => {
    const user = userEvent.setup()
    let delayed
    vi.spyOn(globalThis, 'fetch').mockImplementation((url) => new URL(url).searchParams.get('search')
      ? Promise.resolve(response({ ...page, items: [], total: 0 }))
      : new Promise((resolve) => { delayed = resolve }))
    show()
    await user.type(screen.getByRole('searchbox'), 'otro')
    await screen.findByText('Sin coincidencias')
    await act(async () => delayed(response(page)))
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('muestra el estado vacío sin simular datos', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ ...page, items: [], total: 0 }))
    show()
    expect(await screen.findByText('No hay casos en esta página')).toBeInTheDocument()
  })
})

describe('decisión manual', () => {
  it('no preselecciona una clasificación y exige fundamento', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(claim))
    show({ detail: true })
    const select = await screen.findByLabelText(/Tipo de gasto/)
    expect(select).toHaveValue('')
    const button = screen.getByRole('button', { name: 'Confirmar clasificación' })
    expect(button).toBeDisabled()
    await user.selectOptions(select, 'extraordinario')
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText(/Fundamento de la decisión/), 'Desgaste natural confirmado en la revisión.')
    expect(button).toBeEnabled()
    expect(screen.getByText(/se notificará al propietario/)).toBeInTheDocument()
  })

  it('envía la versión exacta, bloquea doble confirmación y muestra éxito sin cerrar la reparación', async () => {
    const user = userEvent.setup()
    let finish
    let saved = false
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) => {
      if (options.method === 'POST') return new Promise((resolve) => { finish = () => { saved = true; resolve(response({})) } })
      return Promise.resolve(response(saved ? { ...claim, puede_resolver: false, estado: 'Pendiente de respuesta del responsable' } : claim))
    })
    show({ detail: true })
    await user.selectOptions(await screen.findByLabelText(/Tipo de gasto/), 'ordinario')
    await user.type(screen.getByLabelText(/Fundamento de la decisión/), '  El inquilino confirmó la causa del desperfecto.  ')
    await user.dblClick(screen.getByRole('button', { name: 'Confirmar clasificación' }))
    expect(screen.getByRole('button', { name: 'Guardando decisión…' })).toBeDisabled()
    const posts = fetchMock.mock.calls.filter(([, options]) => options.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(JSON.parse(posts[0][1].body)).toEqual({ tipo_gasto: 'ordinario', fundamento: 'El inquilino confirmó la causa del desperfecto.', expected_updated_at: claim.updated_at })
    await act(async () => finish())
    expect(await screen.findByText(/la reparación todavía no está resuelta/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirmar clasificación' })).not.toBeInTheDocument()
  })

  it('conserva lo escrito cuando falla el guardado', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) => Promise.resolve(
      options.method === 'POST' ? response({ detail: { message: 'Error al guardar.' } }, 503) : response(claim),
    ))
    show({ detail: true })
    await user.selectOptions(await screen.findByLabelText(/Tipo de gasto/), 'expensa')
    await user.type(screen.getByLabelText(/Fundamento de la decisión/), 'El desperfecto pertenece al espacio común.')
    await user.click(screen.getByRole('button', { name: 'Confirmar clasificación' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Error al guardar.')
    expect(screen.getByLabelText(/Fundamento de la decisión/)).toHaveValue('El desperfecto pertenece al espacio común.')
    expect(screen.getByRole('button', { name: 'Confirmar clasificación' })).toBeEnabled()
  })

  it('bloquea una decisión desactualizada y exige revisar nuevamente', async () => {
    const user = userEvent.setup()
    let changed = false
    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) => {
      if (options.method === 'POST') { changed = true; return Promise.resolve(response({ detail: { message: 'El reclamo ya fue clasificado.' } }, 409)) }
      return Promise.resolve(response({ ...claim, puede_resolver: !changed }))
    })
    show({ detail: true })
    await user.selectOptions(await screen.findByLabelText(/Tipo de gasto/), 'expensa')
    await user.type(screen.getByLabelText(/Fundamento de la decisión/), 'El desperfecto pertenece al espacio común.')
    await user.click(screen.getByRole('button', { name: 'Confirmar clasificación' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('El reclamo ya fue clasificado.')
    expect(screen.getByRole('button', { name: 'Confirmar clasificación' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Actualizar el caso' }))
    expect(await screen.findByText(/No se puede reemplazar su gestión/)).toBeInTheDocument()
  })

  it('muestra la evidencia anterior sin atribuir confianza a la persona', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ ...claim, puede_resolver: false, confianza_clasificacion: null, motivo_escalado: null,
      decisiones: [{ id: 'audit', usuario_nombre: 'Operador de prueba', rol: 'operador', decidido_en: claim.updated_at,
        tipo_gasto: 'ordinario', fundamento: 'Se confirmó mal uso.', resultado_anterior: { confianza: 0.55, motivo_escalado: 'confianza_insuficiente', fundamento: 'Causa no confirmada.' } }],
    }))
    show({ detail: true })
    expect(await screen.findByText('Decisión manual: Ordinario')).toBeInTheDocument()
    expect(screen.getByText('Confianza original: 55 %.')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Tipo de gasto/)).not.toBeInTheDocument()
  })

  it('permite volver a abrir una foto cuando falla la vista previa privada', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ ...claim,
      fotos: [{ id: 'photo-one', formato: 'PNG' }],
    }))
    show({ detail: true })
    fireEvent.error(await screen.findByRole('img', { name: 'Foto 1 del reclamo' }))
    expect(screen.getByText(/No se pudo cargar la foto/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Abrir foto 1/ })).toHaveAttribute('href',
      `http://localhost:8000/reclamos/escalados/${claim.id}/fotos/photo-one`)
  })

  it('valida entradas vacías, desconocidas y longitudes límite', () => {
    expect(validateManualDecision('', '  ')).toHaveProperty('tipo_gasto')
    expect(validateManualDecision('constructor', 'Fundamento válido')).toHaveProperty('tipo_gasto')
    expect(validateManualDecision('ordinario', 'x'.repeat(1001))).toHaveProperty('fundamento')
    expect(validateManualDecision('ordinario', 'x'.repeat(10))).toEqual({})
  })
})
