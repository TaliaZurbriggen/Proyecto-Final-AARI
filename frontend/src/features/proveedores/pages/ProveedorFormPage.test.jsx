import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProveedorFormPage from './ProveedorFormPage.jsx'

const specialty = {
  id: '10000000-0000-0000-0000-000000000001',
  nombre: 'plomería',
}

const provider = {
  id: '30000000-0000-0000-0000-000000000001',
  nombre_razon_social: 'Servicios del Centro',
  matricula: 'MP 1234',
  telefono: '+5493564555555',
  activo: true,
  hora_inicio: '08:00:00',
  hora_fin: '17:30:00',
  especialidades: [specialty],
  coberturas: [
    {
      id: '40000000-0000-0000-0000-000000000001',
      provincia: 'Córdoba',
      localidad: 'San Francisco',
      cubre_toda_localidad: true,
      barrios: [],
    },
  ],
  created_at: '2026-08-29T12:00:00Z',
  updated_at: '2026-08-29T12:00:00Z',
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
    <MemoryRouter initialEntries={['/proveedores/nuevo']}>
      <Routes>
        <Route path="proveedores/nuevo" element={<ProveedorFormPage />} />
        <Route path="proveedores/:proveedorId" element={<p>Detalle listo</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('formulario de proveedor', () => {
  it('valida los campos obligatorios antes de enviar', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse([specialty]))
    renderForm()
    await screen.findByText('plomería')

    fireEvent.click(screen.getByRole('button', { name: 'Guardar proveedor' }))

    expect(await screen.findByText('Ingresá el nombre o la razón social.')).toBeInTheDocument()
    expect(screen.getByText('Seleccioná o agregá al menos una especialidad.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('envía contacto, especialidad, horario y cobertura normalizados', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse([specialty]))
      .mockResolvedValueOnce(jsonResponse(provider, 201))
    renderForm()

    await user.type(await screen.findByRole('textbox', { name: /Nombre o razón social/ }), ' Servicios del Centro ')
    await user.type(screen.getByRole('textbox', { name: /Matrícula/ }), ' mp 1234 ')
    await user.type(screen.getByRole('textbox', { name: /Teléfono de WhatsApp/ }), '+54 9 3564 555555')
    await user.click(screen.getByRole('checkbox', { name: 'plomería' }))
    await user.selectOptions(screen.getByRole('combobox', { name: /Provincia/ }), 'Córdoba')
    await user.type(screen.getByRole('textbox', { name: /Localidad/ }), ' San Francisco ')
    fireEvent.change(document.getElementById('hora_inicio'), { target: { value: '08:00' } })
    fireEvent.change(document.getElementById('hora_fin'), { target: { value: '17:30' } })
    await user.click(screen.getByRole('button', { name: 'Guardar proveedor' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
      nombre_razon_social: 'Servicios del Centro',
      matricula: 'MP 1234',
      telefono: '+5493564555555',
      hora_inicio: '08:00',
      hora_fin: '17:30',
      especialidad_ids: [specialty.id],
      coberturas: [
        {
          provincia: 'Córdoba',
          localidad: 'San Francisco',
          cubre_toda_localidad: true,
          barrios: [],
        },
      ],
    })
    expect(await screen.findByText('Detalle listo')).toBeInTheDocument()
  })
})
