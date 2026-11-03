import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'
import ConversationPanel from './ConversationPanel.jsx'
import { DockContext } from './conversationContext.js'

afterEach(() => vi.restoreAllMocks())
it('el acceso a coordinar navega y solicita cerrar el panel flotante', async () => {
  const id = '11111111-1111-4111-8111-111111111111'
  const close = vi.fn()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ id, solicitud_id: null, finalidad: 'coordinacion', numero_reclamo: 1, coordinacion_url: `/visitas/${id}`, puede_enviar: false, puede_finalizar: false, motivo_solo_lectura: 'Todavía no hay acuerdo.', ultimo_numero: 0, leido_hasta: 0, no_leidos: 0, items: [], hay_anteriores: false, hay_nuevos: false }), { headers: { 'Content-Type': 'application/json' } }))
  render(<MemoryRouter><DockContext.Provider value={{ close }}><Routes><Route path="/" element={<ConversationPanel threadId={id} />} /><Route path="/visitas/:reclamoId" element={<h1>Pantalla de coordinación</h1>} /></Routes></DockContext.Provider></MemoryRouter>)
  await userEvent.click(await screen.findByRole('link', { name: 'Proponer o confirmar fecha y hora' }))
  expect(close).toHaveBeenCalledOnce()
  expect(screen.getByRole('heading', { name: 'Pantalla de coordinación' })).toBeVisible()
})
