import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InquilinoFormPage from './InquilinoFormPage.jsx'

const property = {
  id: '4fd4e07c-6259-45f1-b8b3-6a607235cc89',
  direccion: 'Av. San Martín 120',
  provincia: 'Santa Fe',
  localidad: 'San Francisco',
  barrio: 'Centro',
  tipo: 'departamento',
  piso: 0,
  numero: 'B',
  tiene_inquilino_activo: false,
}

const propertyPage = {
  items: [property],
  page: 1,
  page_size: 100,
  total: 1,
  total_pages: 1,
}

const tenantResponse = {
  id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
  nombre_completo: 'Lucía Pérez',
  dni: '30123456',
  email: 'lucia@example.com',
  telefono: '+54 9 3564 555555',
  propiedad: property,
  estado: 'activo',
  cantidad_reclamos: 0,
  created_at: '2026-08-23T12:00:00Z',
  updated_at: '2026-08-23T12:00:00Z',
}

function jsonResponse(body, status = 200) {
  return {
    headers: { get: () => 'application/json' },
    json: async () => body,
    ok: status >= 200 && status < 300,
    status,
  }
}

function renderForm(entry = '/inquilinos/nuevo') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="inquilinos/nuevo" element={<InquilinoFormPage />} />
        <Route path="inquilinos/:inquilinoId" element={<p>Detalle listo</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('formulario de inquilino', () => {
  it('muestra validaciones sin enviar datos incompletos', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(propertyPage))
    renderForm()
    await screen.findByRole('combobox', { name: /Propiedad/ })

    fireEvent.click(screen.getByRole('button', { name: 'Guardar inquilino' }))

    expect(
      await screen.findByText('Ingresá el nombre completo del inquilino.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Nombre completo/ })).toHaveFocus()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('rechaza un DNI ingresado como nombre y no envía el alta', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(propertyPage))
    renderForm()
    await screen.findByRole('combobox', { name: /Propiedad/ })

    await user.type(screen.getByRole('textbox', { name: /Nombre completo/ }), '43428013')
    await user.click(screen.getByRole('button', { name: 'Guardar inquilino' }))

    expect(
      await screen.findByText(
        'Ingresá un nombre válido usando solo letras, espacios, apóstrofes o guiones.',
      ),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('preselecciona la propiedad, normaliza y registra el inquilino', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(propertyPage))
      .mockResolvedValueOnce(jsonResponse(tenantResponse, 201))
    renderForm(`/inquilinos/nuevo?propiedad_id=${property.id}`)

    expect(await screen.findByRole('combobox', { name: /Propiedad/ })).toHaveValue(
      property.id,
    )
    await user.type(screen.getByRole('textbox', { name: /Nombre completo/ }), ' Lucía   Pérez ')
    await user.type(screen.getByRole('textbox', { name: /DNI/ }), '30123456')
    await user.type(screen.getByRole('textbox', { name: /Email/ }), 'LUCIA@EXAMPLE.COM')
    await user.type(screen.getByRole('textbox', { name: /Teléfono/ }), '+54 9 3564 555555')
    await user.click(screen.getByRole('button', { name: 'Guardar inquilino' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
      nombre_completo: 'Lucía Pérez',
      dni: '30123456',
      email: 'lucia@example.com',
      propiedad_id: property.id,
    })
    expect(await screen.findByText('Detalle listo')).toBeInTheDocument()
  })
})
