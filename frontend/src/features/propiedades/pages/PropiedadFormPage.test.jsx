import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PropiedadFormPage from './PropiedadFormPage.jsx'

const owner = {
  id: '66db32fa-5f16-4ba7-872d-adc80c8a381f',
  nombre_completo: 'Ana Martínez',
  dni: '30123456',
}

const ownerPage = {
  items: [owner],
  page: 1,
  page_size: 100,
  total: 1,
  total_pages: 1,
}

const propertyResponse = {
  id: '4fd4e07c-6259-45f1-b8b3-6a607235cc89',
  direccion: 'Av. San Martín 120',
  provincia: 'Santa Fe',
  localidad: 'San Francisco',
  barrio: 'Centro',
  tipo: 'departamento',
  piso: 0,
  numero: 'B',
  propietario: owner,
  cantidad_reclamos: 0,
  tiene_inquilino_activo: false,
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

function renderForm() {
  return render(
    <MemoryRouter initialEntries={['/propiedades/nueva']}>
      <Routes>
        <Route path="propiedades/nueva" element={<PropiedadFormPage />} />
        <Route path="propiedades/:propiedadId" element={<p>Detalle listo</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

function renderEditForm() {
  return render(
    <MemoryRouter
      initialEntries={[
        `/propiedades/${propertyResponse.id}/editar`,
      ]}
    >
      <Routes>
        <Route
          path="propiedades/:propiedadId/editar"
          element={<PropiedadFormPage />}
        />
        <Route path="propiedades/:propiedadId" element={<p>Detalle listo</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('formulario de propiedad', () => {
  it('muestra validaciones sin enviar datos incompletos', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(ownerPage))
    renderForm()
    await screen.findByRole('combobox', { name: /Propietario/ })

    fireEvent.click(screen.getByRole('button', { name: 'Guardar propiedad' }))

    expect(await screen.findByText('Ingresá la dirección de la propiedad.')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Dirección/ })).toHaveFocus()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('envía el departamento normalizado y redirige al detalle', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(ownerPage))
      .mockResolvedValueOnce(jsonResponse(propertyResponse, 201))
    renderForm()

    await user.type(
      await screen.findByRole('textbox', { name: /Dirección/ }),
      ' Av. San Martín   120 ',
    )
    await user.selectOptions(
      screen.getByRole('combobox', { name: /Provincia/ }),
      'Santa Fe',
    )
    await user.type(
      screen.getByRole('textbox', { name: /Localidad/ }),
      ' San   Francisco ',
    )
    await user.type(screen.getByRole('textbox', { name: /Barrio/ }), ' Centro ')
    await user.selectOptions(screen.getByRole('combobox', { name: /Tipo/ }), 'departamento')
    await user.selectOptions(
      screen.getByRole('combobox', { name: /Propietario/ }),
      owner.id,
    )
    await user.type(screen.getByRole('spinbutton', { name: /Piso/ }), '0')
    await user.type(
      screen.getByRole('textbox', { name: /Unidad \/ departamento/ }),
      ' B ',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar propiedad' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
      direccion: 'Av. San Martín 120',
      provincia: 'Santa Fe',
      localidad: 'San Francisco',
      barrio: 'Centro',
      tipo: 'departamento',
      piso: 0,
      numero: 'B',
      propietario_id: owner.id,
    })
    expect(await screen.findByText('Detalle listo')).toBeInTheDocument()
  })

  it('edita una propiedad cuando el backend devuelve el piso como número', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(ownerPage))
      .mockResolvedValueOnce(jsonResponse(propertyResponse))
      .mockResolvedValueOnce(jsonResponse(propertyResponse))
    renderEditForm()

    expect(
      await screen.findByRole('heading', { name: 'Editar propiedad' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /Piso/ })).toHaveValue(0)

    await user.click(screen.getByRole('button', { name: 'Guardar propiedad' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(fetchMock.mock.calls[2][0]).toContain(
      `/propiedades/${propertyResponse.id}`,
    )
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: 'PUT' })
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toMatchObject({
      piso: 0,
      numero: 'B',
    })
    expect(await screen.findByText('Detalle listo')).toBeInTheDocument()
  })
})
