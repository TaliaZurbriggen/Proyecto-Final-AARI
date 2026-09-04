import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OperadorFormPage from './OperadorFormPage.jsx'
import OperadoresListPage from './OperadoresListPage.jsx'
import { normalizeOperador, validateOperador } from '../validation.js'
import App from '../../../App.jsx'

const operator = {
  id: '00000000-0000-0000-0000-000000000007', nombre_completo: 'Ana Prueba',
  email: 'operador@example.com', activo: true,
  acceso: { estado: 'enviado', primer_ingreso: true, intentos: 1 },
}
const page = (items = [operator], extra = {}) => ({ items, total: items.length, page: 1, page_size: 10, total_pages: 1, ...extra })
const json = (body, status = 200) => ({ headers: { get: () => 'application/json' }, json: async () => body, ok: status < 400, status })
const fetchMock = (body) => vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body))
function Notice() {
  const { state } = useLocation()
  return <p>{state?.notice?.message}</p>
}
function form() {
  return render(<MemoryRouter initialEntries={['/operadores/nuevo']}><Routes>
    <Route path="operadores/nuevo" element={<OperadorFormPage />} />
    <Route path="operadores" element={<Notice />} />
  </Routes></MemoryRouter>)
}
function list(path = '/operadores') {
  return render(<MemoryRouter initialEntries={[path]}><OperadoresListPage /></MemoryRouter>)
}
afterEach(() => vi.restoreAllMocks())

describe('HU7 — formulario', () => {
  it('normaliza y valida sin solicitar contraseñas al administrador', () => {
    expect(normalizeOperador({ nombre_completo: ' Ana   Prueba ', email: ' ANA@EXAMPLE.COM ' }))
      .toEqual({ nombre_completo: 'Ana Prueba', email: 'ana@example.com' })
    expect(validateOperador({ nombre_completo: '43434343', email: 'invalid' })).toHaveProperty('nombre_completo')
    const request = fetchMock({})
    form()
    fireEvent.click(screen.getByRole('button', { name: 'Crear operador' }))
    expect(screen.getByRole('textbox', { name: /Nombre completo/ })).toHaveFocus()
    expect(request).not.toHaveBeenCalled()
    expect(document.querySelector('input[type=password]')).toBeNull()
  })
  it.each(['enviado', 'fallido'])('crea una cuenta aunque el correo quede %s', async (status) => {
    const request = fetchMock({ ...operator, acceso: { ...operator.acceso, estado: status } })
    form()
    fireEvent.change(screen.getByRole('textbox', { name: /Nombre completo/ }), { target: { value: 'Ana Prueba' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Email/ }), { target: { value: 'OPERADOR@EXAMPLE.COM' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear operador' }))
    await screen.findByText(status === 'enviado' ? /Operador creado. Se enviaron/ : /Operador creado, pero/)
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ nombre_completo: 'Ana Prueba', email: 'operador@example.com' })
  })
  it('muestra el conflicto de email en el campo y conserva los valores', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: { field: 'email', message: 'Ese email ya está registrado.' } }, 409))
    form()
    fireEvent.change(screen.getByRole('textbox', { name: /Nombre completo/ }), { target: { value: 'Ana Prueba' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Email/ }), { target: { value: 'operador@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear operador' }))
    expect(await screen.findByText('Ese email ya está registrado.')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Email/ })).toHaveFocus()
    expect(screen.getByRole('textbox', { name: /Nombre completo/ })).toHaveValue('Ana Prueba')
  })
})

describe('HU7 — listado', () => {
  it('muestra los estados y no permite acciones sobre inactivos', async () => {
    fetchMock(page([operator, { ...operator, id: 'inactive', nombre_completo: 'Otro Operador', activo: false }]))
    list()
    expect(await screen.findByText('Ana Prueba')).toBeInTheDocument()
    expect(screen.getByText('Activo')).toBeInTheDocument()
    expect(screen.getByText('Inactivo')).toBeInTheDocument()
    expect(screen.getByText('Espera primer ingreso')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Desactivar a Otro Operador' })).not.toBeInTheDocument()
  })
  it('pide confirmación y permite cancelar sin desactivar', async () => {
    const user = userEvent.setup()
    const request = fetchMock(page())
    list()
    await user.click(await screen.findByRole('button', { name: 'Desactivar a Ana Prueba' }))
    const dialog = screen.getByRole('alertdialog')
    expect(within(dialog).getByText(/historial se conserva/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
    expect(request).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Desactivar a Ana Prueba' })).toHaveFocus()
  })
  it('desactiva y muestra la cantidad de reclamos liberados', async () => {
    const user = userEvent.setup()
    const request = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(page()))
      .mockResolvedValueOnce(json({ operador: { ...operator, activo: false }, reclamos_liberados: 2 }))
      .mockResolvedValue(json(page([{ ...operator, activo: false }])))
    list()
    await user.click(await screen.findByRole('button', { name: 'Desactivar a Ana Prueba' }))
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Desactivar operador' }))
    expect(await screen.findByText(/Reclamos devueltos a la cola general: 2/)).toBeInTheDocument()
    expect(await screen.findByText('Inactivo')).toBeInTheDocument()
    expect(request.mock.calls[1][1].method).toBe('PATCH')
    await waitFor(() => expect(screen.getByText(/Reclamos devueltos a la cola general: 2/).closest('[tabindex="-1"]')).toHaveFocus())
  })
  it('mantiene el foco dentro de la confirmación y vuelve al disparador con Escape', async () => {
    const user = userEvent.setup()
    fetchMock(page())
    list()
    await user.click(await screen.findByRole('button', { name: 'Desactivar a Ana Prueba' }))
    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Desactivar operador' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.getByRole('button', { name: 'Desactivar a Ana Prueba' })).toHaveFocus()
  })
  it('restaura el foco y muestra el error cuando una acción falla', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(page()))
      .mockResolvedValueOnce(json({ detail: 'No se pudo desactivar.' }, 503))
    list()
    await user.click(await screen.findByRole('button', { name: 'Desactivar a Ana Prueba' }))
    await user.click(screen.getByRole('button', { name: 'Desactivar operador' }))
    expect(await screen.findByText('No se pudo desactivar.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Desactivar a Ana Prueba' })).toHaveFocus()
  })
  it('advierte que reenviar invalida la clave anterior incluso si falla el correo', async () => {
    const user = userEvent.setup()
    const request = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(page()))
      .mockResolvedValueOnce(json({ ...operator, acceso: { ...operator.acceso, estado: 'fallido' } }))
      .mockResolvedValue(json(page([{ ...operator, acceso: { ...operator.acceso, estado: 'fallido' } }])))
    list()
    await user.click(await screen.findByRole('button', { name: 'Reenviar credenciales de Ana Prueba' }))
    expect(screen.getByText(/incluso si el correo falla/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Generar y enviar' }))
    expect(await screen.findByText(/La cuenta se conserva/)).toBeInTheDocument()
    expect(request.mock.calls[1][0]).toContain('/acceso/reintentar')
  })
  it('cubre carga, error de red y reintento', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('network')).mockResolvedValue(json(page([])))
    list()
    expect(screen.getByLabelText('Cargando operadores')).toBeInTheDocument()
    expect(await screen.findByText(/No pudimos conectarnos/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar carga' }))
    expect(await screen.findByText('Todavía no hay operadores')).toBeInTheDocument()
  })
  it('busca y pagina manteniendo la búsqueda', async () => {
    const request = fetchMock(page([operator], { total: 12, total_pages: 2 }))
    list('/operadores?search=ana')
    await screen.findByText('Ana Prueba')
    expect(request.mock.calls[0][0]).toContain('search=ana')
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2))
    expect(request.mock.calls[1][0]).toContain('page=2')
    expect(request.mock.calls[1][0]).toContain('search=ana')
  })
  it('no ofrece reenvío cuando el usuario ya cambió la contraseña', async () => {
    fetchMock(page([{ ...operator, acceso: { ...operator.acceso, primer_ingreso: false } }]))
    list()
    await screen.findByText('Contraseña actualizada')
    expect(screen.queryByRole('button', { name: /Reenviar/ })).not.toBeInTheDocument()
  })
})

describe('rutas de operadores', () => {
  it('impide al operador acceder a la gestión administrativa', async () => {
    const request = fetchMock({ user: { id: operator.id, email: operator.email, rol: 'operador', primer_ingreso: false } })
    render(<MemoryRouter initialEntries={['/operadores']}><App /></MemoryRouter>)
    expect(await screen.findByText('Portal de operación')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Nuevo operador' })).not.toBeInTheDocument()
    expect(request).toHaveBeenCalledTimes(1)
  })
})
