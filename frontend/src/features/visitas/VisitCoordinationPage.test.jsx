import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import VisitCoordinationPage from './VisitCoordinationPage.jsx'
import { DockContext } from '../conversaciones/conversationContext.js'

const claim = '11111111-1111-4111-8111-111111111111'
const coordinator = '22222222-2222-4222-8222-222222222222'
const base = { id: coordinator, reclamo_id: claim, numero: 1, etapa: 'esperando_disponibilidad', version: 0, proveedor: 'Servicio Sintético', ubicacion: 'Unidad Sintética', urgencia: 'media', vence_en: null, fecha_confirmada: null, propuesta: null, opciones: [], acciones: ['disponibilidad'], vigente: true, vencida: false, hilo_id: '33333333-3333-4333-8333-333333333333', puede_conversar: false, motivo_solo_lectura: null }
const slots = [1, 2, 3].map((n) => ({ id: `option-${n}`, desde: `2099-11-${10 + n}T14:00:00-03:00`, hasta: `2099-11-${10 + n}T17:00:00-03:00` }))
const followup = { propuesta_pendiente: null, decisiones: [], reprogramaciones: [], ausencias: [] }
const confirmed = { ...base, etapa: 'confirmada', version: 9, fecha_confirmada: slots[0].desde, seguimiento: followup }
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
let current, fetch, posts, openThread
beforeEach(() => {
  current = { ...base }; posts = []; openThread = vi.fn()
  fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options = {}) => {
    if (options.method === 'POST') { posts.push(JSON.parse(options.body)); return Promise.resolve(json(current)) }
    return Promise.resolve(json(current))
  })
})
afterEach(() => vi.restoreAllMocks())
const show = () => render(<MemoryRouter initialEntries={[`/visitas/${claim}`]}><DockContext.Provider value={{ enabled: true, openThread }}><Routes><Route path="/visitas/:reclamoId" element={<VisitCoordinationPage />} /></Routes></DockContext.Provider></MemoryRouter>)

it('propone una nueva fecha sin cambiar el horario que se muestra como confirmado', async () => {
  current = { ...confirmed, acciones: ['reprogramar'], puede_conversar: true }
  show()
  expect(await screen.findByText(/Visita confirmada:.*11\/11\/99/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Abrir conversación de coordinación' }))
  expect(openThread).toHaveBeenCalledWith(base.hilo_id)
  fireEvent.change(screen.getByLabelText(/Nueva fecha/), { target: { value: '2099-11-20' } })
  fireEvent.change(screen.getByLabelText(/Nueva hora/), { target: { value: '15:00' } })
  await userEvent.type(screen.getByLabelText(/Motivo/), 'Cambio de disponibilidad')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar propuesta' }))
  expect(posts[0]).toMatchObject({ version_esperada: 9, fecha: '2099-11-20T15:00:00-03:00', motivo: 'Cambio de disponibilidad' })
})

it('muestra ambos horarios y envía la decisión para la propuesta exacta', async () => {
  current = { ...confirmed, acciones: ['decidir-reprogramacion'], seguimiento: { ...followup,
    propuesta_pendiente: { id: 'proposal', fecha_anterior: slots[0].desde, fecha_propuesta: slots[1].desde,
      vence_en: slots[0].desde, solicitante_rol: 'proveedor', motivo: 'Turno actualizado' }, decisiones: ['aceptar', 'rechazar'],
  } }
  show()
  expect(await screen.findByText('Horario vigente')).toBeVisible()
  expect(screen.getByText('Horario propuesto')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Retirar propuesta' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Aceptar nuevo horario' }))
  expect(posts[0]).toMatchObject({ propuesta_id: 'proposal', decision: 'aceptar', version_esperada: 9 })
})

it('registra el reporte del usuario y muestra el de la otra parte con su autor', async () => {
  current = { ...confirmed, acciones: ['informar-ausencia'], seguimiento: { ...followup, ausencias: [{
    id: 'report', fecha_visita: slots[0].desde, creada_en: slots[0].hasta, autor_rol: 'proveedor', tipo: 'no_realizada', observaciones: 'No pude acceder.',
  }] } }
  show()
  expect(await screen.findByText('Proveedor · La visita no se realizó')).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText(/Resultado informado/), 'contraparte_ausente')
  await userEvent.type(screen.getByLabelText(/Observaciones/), 'Esperé en la unidad.')
  await userEvent.click(screen.getByRole('button', { name: 'Registrar reporte' }))
  expect(posts[0]).toMatchObject({ tipo: 'contraparte_ausente', observaciones: 'Esperé en la unidad.', version_esperada: 9 })
})

it('rechaza formulario vacío y devuelve foco sin POST', async () => {
  show()
  await userEvent.click(await screen.findByRole('button', { name: 'Enviar horarios al proveedor' }))
  expect(screen.getByRole('alert')).toHaveTextContent('tres fechas distintas')
  expect(screen.getAllByLabelText('Fecha', { exact: false })[0]).toHaveFocus()
  expect(posts).toHaveLength(0)
})

it('envía tres intervalos explícitos de Argentina con versión y clave', async () => {
  show()
  await screen.findByRole('button', { name: 'Enviar horarios al proveedor' })
  const groups = screen.getAllByRole('group')
  groups.forEach((group, i) => {
    fireEvent.change(within(group).getByLabelText('Fecha', { exact: false }), { target: { value: `2099-11-${11 + i}` } })
    fireEvent.change(within(group).getByLabelText('Desde', { exact: false }), { target: { value: '14:00' } })
    fireEvent.change(within(group).getByLabelText('Hasta', { exact: false }), { target: { value: '17:00' } })
  })
  await userEvent.click(screen.getByRole('button', { name: 'Enviar horarios al proveedor' }))
  await waitFor(() => expect(posts).toHaveLength(1))
  expect(posts[0]).toMatchObject({ coordinacion_id: coordinator, version_esperada: 0, opciones: [{ desde: '2099-11-11T14:00:00-03:00', hasta: '2099-11-11T17:00:00-03:00' }, { desde: '2099-11-12T14:00:00-03:00', hasta: '2099-11-12T17:00:00-03:00' }, { desde: '2099-11-13T14:00:00-03:00', hasta: '2099-11-13T17:00:00-03:00' }] })
  expect(posts[0].request_id).toBeTruthy()
})

it('no ofrece chat de negociación hasta indicar incompatibilidad', async () => {
  current = { ...base, etapa: 'esperando_confirmacion', version: 1, opciones: slots, acciones: ['confirmar', 'sin-coincidencia'] }
  show()
  expect(await screen.findByRole('button', { name: 'No puedo en estos horarios' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Abrir conversación de coordinación' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'No puedo en estos horarios' }))
  expect(posts).toHaveLength(1)
})

it('abre el hilo correcto y confirma sólo la propuesta ajena mostrada', async () => {
  current = { ...base, etapa: 'negociando', version: 3, opciones: slots, propuesta: { fecha: '2099-11-15T18:00:00-03:00', version: 3, propia: false }, acciones: ['proponer', 'confirmar'] }
  show()
  await userEvent.click(await screen.findByRole('button', { name: 'Abrir conversación de coordinación' }))
  expect(openThread).toHaveBeenCalledWith(base.hilo_id)
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar esta propuesta' }))
  expect(posts[0]).toMatchObject({ propuesta_version: 3, version_esperada: 3 })
  expect(posts[0]).not.toHaveProperty('fecha')
})

it('la propuesta propia no tiene botón de auto-confirmación', async () => {
  current = { ...base, etapa: 'negociando', acciones: ['proponer'], propuesta: { fecha: '2099-11-15T18:00:00-03:00', version: 3, propia: true } }
  show()
  expect(await screen.findByText('Esperando la confirmación de la otra persona.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Confirmar esta propuesta' })).not.toBeInTheDocument()
})

it('ante respuesta incierta reintenta el mismo payload sin nueva decisión', async () => {
  current = { ...base, etapa: 'esperando_confirmacion', version: 1, opciones: slots, acciones: ['sin-coincidencia'] }
  fetch.mockImplementation((_url, options = {}) => {
    if (options.method === 'POST') { posts.push(JSON.parse(options.body)); return Promise.reject(new TypeError('network')) }
    return Promise.resolve(json(current))
  })
  show()
  await userEvent.click(await screen.findByRole('button', { name: 'No puedo en estos horarios' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Reintentar el mismo envío' }))
  expect(posts).toHaveLength(2)
  expect(posts[0]).toEqual(posts[1])
})

it('un error de lectura no conserva acciones sobre datos anteriores', async () => {
  show()
  await screen.findByRole('button', { name: 'Enviar horarios al proveedor' })
  fetch.mockResolvedValue(json({ detail: { message: 'No disponible' } }, 503))
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar' }))
  expect(await screen.findByText('No disponible')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Enviar horarios al proveedor' })).not.toBeInTheDocument()
})

it('confirmada muestra el encuentro y no ofrece otra confirmación', async () => {
  current = { ...base, etapa: 'confirmada', fecha_confirmada: '2099-11-15T18:00:00-03:00', acciones: [] }
  show()
  expect(await screen.findByText(/Visita confirmada:/)).toHaveTextContent('reparación todavía no está marcada como resuelta')
  expect(screen.queryByRole('button', { name: 'Confirmar visita' })).not.toBeInTheDocument()
})
