import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ReclamoConfirmationPage from './ReclamoConfirmationPage.jsx'
import ReclamoFormPage from './ReclamoFormPage.jsx'

const context = {
  inquilino_nombre: 'Lucía Pérez',
  inquilino_email: 'lucia@example.com',
  propiedad: {
    id: '4fd4e07c-6259-45f1-b8b3-6a607235cc89',
    direccion: 'Av. San Martín 120',
    provincia: 'Santa Fe',
    localidad: 'San Francisco',
    barrio: 'Centro',
    tipo: 'departamento',
    piso: 0,
    numero: 'B',
  },
}

const claim = {
  id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
  numero: 15,
  estado: 'Recibido',
  creado_en: '2026-09-04T13:00:00Z',
  notificacion_estado: 'pendiente',
  fotos_adjuntas: 1,
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/inquilino/reclamos/nuevo']}>
      <Routes>
        <Route path="inquilino" element={<p>Inicio del inquilino</p>} />
        <Route path="inquilino/reclamos/nuevo" element={<ReclamoFormPage />} />
        <Route
          path="inquilino/reclamos/confirmacion"
          element={<ReclamoConfirmationPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('alta de reclamo del inquilino', () => {
  it('muestra la identidad y la unidad antes de completar el formulario', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(context))
    renderPage()

    expect(await screen.findByText('Lucía Pérez')).toBeInTheDocument()
    expect(
      screen.getByText('Av. San Martín 120 · PB · Unidad B · San Francisco · Santa Fe'),
    ).toBeInTheDocument()
    expect(screen.getByText('lucia@example.com')).toBeInTheDocument()
  })

  it('valida campos obligatorios sin intentar crear el reclamo', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(context))
    renderPage()
    await screen.findByRole('heading', { name: 'Detalle del problema' })

    fireEvent.click(screen.getByRole('button', { name: 'Enviar reclamo' }))

    expect(
      await screen.findByText('Describí el problema usando entre 20 y 1000 caracteres.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/Descripción/)).toHaveFocus()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('envía FormData y muestra número, estado y aviso de correo', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(context))
      .mockResolvedValueOnce(jsonResponse(claim, 201))
    renderPage()
    await screen.findByText('Lucía Pérez')

    await user.type(
      screen.getByLabelText(/Descripción/),
      'La canilla de la cocina pierde agua desde ayer.',
    )
    await user.selectOptions(screen.getByLabelText(/Urgencia/), 'media')
    const photo = new File(['imagen'], 'cocina.png', { type: 'image/png' })
    await user.upload(screen.getByLabelText(/Fotos/), photo)
    await user.click(screen.getByRole('button', { name: 'Enviar reclamo' }))

    expect(await screen.findByText('#000015')).toBeInTheDocument()
    expect(screen.getByText('Recibido')).toBeInTheDocument()
    expect(screen.getByText(/Si el correo falla/)).toBeInTheDocument()

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const options = fetchMock.mock.calls[1][1]
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.get('descripcion')).toBe(
      'La canilla de la cocina pierde agua desde ayer.',
    )
    expect(options.body.get('urgencia')).toBe('media')
    expect(options.body.getAll('fotos')).toHaveLength(1)
    expect(options.headers).not.toHaveProperty('Content-Type')
  })

  it('explica cuando ya existe un reclamo activo', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(context))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: {
              code: 'active_claim_exists',
              message: 'Ya tenés un reclamo activo para esta unidad.',
            },
          },
          409,
        ),
      )
    renderPage()
    await screen.findByText('Lucía Pérez')
    await user.type(
      screen.getByLabelText(/Descripción/),
      'La canilla de la cocina pierde agua desde ayer.',
    )
    await user.selectOptions(screen.getByLabelText(/Urgencia/), 'media')
    await user.click(screen.getByRole('button', { name: 'Enviar reclamo' }))

    expect(
      await screen.findByText('Ya tenés un reclamo activo para esta unidad.'),
    ).toBeInTheDocument()
  })
})
