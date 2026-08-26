import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PropietarioFormPage from './PropietarioFormPage.jsx'

const ownerResponse = {
  id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
  nombre_completo: 'Ana Martínez',
  dni: '30123456',
  email: 'ana@example.com',
  telefono: '+54 3564 555555',
  cantidad_inmuebles: 0,
  created_at: '2026-08-22T12:00:00Z',
  updated_at: '2026-08-22T12:00:00Z',
}

function jsonResponse(body, status = 200) {
  return {
    headers: { get: () => 'application/json' },
    json: async () => body,
    ok: status >= 200 && status < 300,
    status,
  }
}

function renderForm() {
  return render(
    <MemoryRouter initialEntries={['/propietarios/nuevo']}>
      <Routes>
        <Route path="propietarios/nuevo" element={<PropietarioFormPage />} />
        <Route path="propietarios/:propietarioId" element={<p>Detalle listo</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('formulario de propietario', () => {
  it('muestra validaciones sin llamar a la API cuando faltan datos', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderForm()

    fireEvent.click(screen.getByRole('button', { name: 'Guardar propietario' }))

    expect(
      await screen.findByText('Ingresá un DNI de 7 u 8 números, sin puntos ni espacios.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Nombre completo/ })).toHaveFocus()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rechaza un DNI ingresado como nombre y no llama a la API', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderForm()

    await user.type(screen.getByRole('textbox', { name: /Nombre completo/ }), '43428013')
    await user.click(screen.getByRole('button', { name: 'Guardar propietario' }))

    expect(
      await screen.findByText(
        'Ingresá un nombre válido usando solo letras, espacios, apóstrofes o guiones.',
      ),
    ).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('normaliza, envía y redirige después de un alta correcta', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(ownerResponse, 201))
    renderForm()

    await user.type(screen.getByRole('textbox', { name: /Nombre completo/ }), 'Ana Martínez')
    await user.type(screen.getByRole('textbox', { name: /DNI/ }), '30123456')
    await user.type(screen.getByRole('textbox', { name: /Email/ }), 'ANA@EXAMPLE.COM')
    await user.type(screen.getByRole('textbox', { name: /Teléfono/ }), '+54 3564 555555')
    await user.click(screen.getByRole('button', { name: 'Guardar propietario' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    const request = fetchMock.mock.calls[0][1]
    expect(JSON.parse(request.body)).toMatchObject({
      email: 'ana@example.com',
      dni: '30123456',
    })
    expect(await screen.findByText('Detalle listo')).toBeInTheDocument()
  })
})
