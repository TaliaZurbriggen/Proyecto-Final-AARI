import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PropertyClaimsHistoryPage from './PropertyClaimsHistoryPage.jsx'
import PropertyClaimDetailPage from './PropertyClaimDetailPage.jsx'

const property = {
  id: 'f2d70de1-a4d5-4f32-a2b3-04dbd22620ed', direccion: 'Unidad de prueba 100',
  provincia: 'Córdoba', localidad: 'Localidad de prueba', tipo: 'casa',
}
const claim = {
  id: 'c24d3cec-5de2-45bd-968d-2ded0f4c1828', numero: 25,
  descripcion: 'Descripción completa del reclamo para la prueba de historial.',
  estado: 'Recibido', tipo_gasto: null, urgencia: 'media',
  creado_en: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T12:00:00Z',
}
const page = { propiedad: property, items: [claim], total: 25, page: 1, page_size: 20, total_pages: 2 }
const detail = {
  ...claim, propiedad: property,
  historial: [
    { estado_anterior: null, estado_nuevo: 'Recibido', origen: 'inquilino', timestamp: '2026-10-01T10:00:00Z' },
    { estado_anterior: 'Recibido', estado_nuevo: 'Clasificado', origen: 'agente', timestamp: '2026-10-01T12:00:00Z' },
  ],
}

function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function show(query = '', tenantView = false, isDetail = false) {
  const prefix = tenantView ? '/inquilino' : ''
  const base = `${prefix}/propiedades/${property.id}/reclamos`
  return render(
    <MemoryRouter initialEntries={[`${base}${isDetail ? `/${claim.id}` : ''}${query}`]}>
      <Routes>
        <Route path={`${prefix}/propiedades/:propiedadId/reclamos`} element={<PropertyClaimsHistoryPage tenantView={tenantView} />} />
        <Route path={`${prefix}/propiedades/:propiedadId/reclamos/:reclamoId`} element={<PropertyClaimDetailPage tenantView={tenantView} />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('historial por propiedad', () => {
  it('muestra columnas, sin clasificar, total y acceso al detalle', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(page))
    show()
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByText('25 reclamos · 20 por página')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('Sin clasificar')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver reclamo #000025' })).toHaveAttribute('href', `/propiedades/${property.id}/reclamos/${claim.id}?page=1`)
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
  })

  it('combina filtros, reinicia la página y solicita otra página conservándolos', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      const urlPage = new URL(url).searchParams.get('page')
      return Promise.resolve(response({ ...page, page: Number(urlPage) }))
    })
    show('?page=2')
    await screen.findByRole('table')
    await user.selectOptions(screen.getByLabelText('Estado'), 'Resuelto')
    await screen.findByRole('table')
    await user.selectOptions(screen.getByLabelText('Tipo de gasto'), 'ordinario')
    await screen.findByRole('table')
    await user.type(screen.getByLabelText('Fecha de ingreso desde'), '2026-10-01')
    await user.type(screen.getByLabelText('Fecha de ingreso hasta'), '2026-10-02')
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText('Página 2 de 2')
    const params = new URL(fetchMock.mock.calls.at(-1)[0]).searchParams
    expect(Object.fromEntries(params)).toEqual({ page: '2', estado: 'Resuelto', tipo_gasto: 'ordinario', fecha_desde: '2026-10-01', fecha_hasta: '2026-10-02' })
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  })

  it('mantiene los filtros al abrir el detalle y regresar al listado', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation((url) => Promise.resolve(response(
      new URL(url).pathname.endsWith(claim.id) ? detail : page,
    )))
    show('?estado=Recibido&tipo_gasto=sin_clasificar')
    await user.click(await screen.findByRole('link', { name: 'Ver reclamo #000025' }))
    expect(await screen.findByRole('heading', { name: 'Reclamo #000025' })).toBeInTheDocument()
    expect(screen.getByText(claim.descripcion)).toBeInTheDocument()
    const entries = within(screen.getByRole('list')).getAllByRole('listitem')
    expect(entries[0]).toHaveTextContent('Clasificado')
    expect(entries[1]).toHaveTextContent('Recibido')
    await user.click(screen.getByRole('link', { name: 'Volver al historial' }))
    await screen.findByRole('table')
    expect(screen.getByLabelText('Estado')).toHaveValue('Recibido')
    expect(screen.getByLabelText('Tipo de gasto')).toHaveValue('sin_clasificar')
  })

  it('muestra el alcance propio y enlaces dentro del portal del inquilino', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(page))
    show('', true)
    const link = await screen.findByRole('link', { name: 'Ver reclamo #000025' })
    expect(link).toHaveAttribute('href', `/inquilino/propiedades/${property.id}/reclamos/${claim.id}?page=1`)
    expect(screen.getByText(/únicamente los reclamos que vos presentaste/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Volver a mis reclamos' })).toHaveAttribute('href', '/inquilino/reclamos')
  })

  it('explica el vacío y permite limpiar los filtros', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(response({ ...page, items: [], total: 0, total_pages: 1 })))
    show('?tipo_gasto=expensa')
    expect(await screen.findByText('Sin coincidencias')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(await screen.findByText('Todavía no hay reclamos')).toBeInTheDocument()
    expect(new URL(fetchMock.mock.calls.at(-1)[0]).searchParams.has('tipo_gasto')).toBe(false)
  })

  it('bloquea el rango invertido antes de enviar la consulta', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    show('?fecha_desde=2026-10-02&fecha_hasta=2026-10-01')
    expect(screen.getByText(/La fecha desde no puede ser posterior/)).toBeInTheDocument()
    expect(screen.getByLabelText('Fecha de ingreso hasta')).toHaveAttribute('aria-invalid', 'true')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('muestra el error de autorización sin presentar resultados', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ detail: { message: 'No tenés permiso para consultar este historial.' } }, 403))
    show('', true)
    expect(await screen.findByRole('alert')).toHaveTextContent('No tenés permiso')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('descarta una respuesta antigua si el filtro cambia mientras carga', async () => {
    const user = userEvent.setup()
    let finishOld
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve }))
      .mockResolvedValueOnce(response({ ...page, items: [{ ...claim, numero: 99 }], total: 1, total_pages: 1 }))
    show()
    await user.selectOptions(screen.getByLabelText('Estado'), 'Resuelto')
    await screen.findByRole('link', { name: 'Ver reclamo #000099' })
    await act(async () => { finishOld(response(page)) })
    expect(screen.queryByRole('link', { name: 'Ver reclamo #000025' })).not.toBeInTheDocument()
  })

  it('permite regresar a la primera página si el total se redujo', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(response({ ...page, items: [], total: 0, total_pages: 1 })))
    show('?page=3')
    await user.click(await screen.findByRole('button', { name: 'Volver a la primera página' }))
    await waitFor(() => expect(new URL(fetchMock.mock.calls.at(-1)[0]).searchParams.get('page')).toBe('1'))
  })

  it('conserva la navegación cuando el detalle no existe', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ detail: { message: 'No encontramos ese reclamo.' } }, 404))
    show('?page=2', true, true)
    expect(await screen.findByRole('alert')).toHaveTextContent('No encontramos ese reclamo')
    expect(screen.getByRole('link', { name: 'Volver al historial' })).toHaveAttribute('href', `/inquilino/propiedades/${property.id}/reclamos?page=2`)
  })
})
