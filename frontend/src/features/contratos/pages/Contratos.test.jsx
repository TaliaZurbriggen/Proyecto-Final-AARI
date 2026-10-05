import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../auth/authContext.js'
import ContractFormPage from './ContractFormPage.jsx'
import ContractDetailPage from './ContractDetailPage.jsx'
import ContractsListPage from './ContractsListPage.jsx'
import { fileError, MAX_PDF_SIZE, nextDay, validateDates } from '../validation.js'
import { uploadContract } from '../api/contratosApi.js'

const contract = {
  id: 'contract-one', inquilino_id: 'tenant-one', propiedad_id: 'property-one',
  propietario_id: 'owner-one', inquilino_nombre: 'Inquilino de prueba',
  propietario_nombre: 'Propietario de prueba', direccion: 'Inmueble de prueba 123',
  localidad: 'Localidad de prueba', provincia: 'Córdoba', fecha_inicio: '2026-09-01',
  fecha_fin: '2027-08-31', fecha_finalizacion: null, contrato_anterior_id: null,
  estado: 'borrador', vigencia: 'Borrador', revision: 1, documentos: [],
}
const tenant = { id: 'tenant-one', nombre_completo: 'Inquilino de prueba',
  propiedad: { id: 'property-one', direccion: contract.direccion } }
const json = (body, status = 200) => ({ headers: { get: () => 'application/json' }, ok: status < 400, status, json: async () => body })
function renderRoute(path, role = 'administrador') {
  return render(<AuthContext.Provider value={{ user: { rol: role } }}>
    <MemoryRouter initialEntries={[path]}><Routes>
      <Route path="/contratos/nuevo" element={<ContractFormPage />} />
      <Route path="/contratos/:contractId/editar" element={<ContractFormPage />} />
      <Route path="/contratos/:contractId" element={<ContractDetailPage />} />
      <Route path="/contratos" element={<ContractsListPage />} />
      <Route path="/inquilino/contratos/:contractId" element={<ContractDetailPage />} />
      <Route path="/propietario/contratos/:contractId" element={<ContractDetailPage />} />
    </Routes></MemoryRouter>
  </AuthContext.Provider>)
}
afterEach(() => vi.restoreAllMocks())

describe('contratos: validaciones y formularios', () => {
  it('valida fechas y archivos antes de enviarlos', () => {
    expect(validateDates('', '')).toHaveProperty('fecha_inicio')
    expect(validateDates('2026-01-01', '2026-01-01')).toHaveProperty('fecha_fin')
    expect(validateDates('2026-01-01', '2026-01-02')).toEqual({})
    expect(fileError(null)).toBe('')
    expect(fileError(null, true)).toBeTruthy()
    expect(fileError({ name: 'x.exe', type: '', size: 1 })).toBeTruthy()
    expect(fileError({ name: 'x.pdf', type: 'application/pdf', size: MAX_PDF_SIZE + 1 })).toBeTruthy()
    expect(fileError({ name: 'x.pdf', type: 'application/pdf', size: MAX_PDF_SIZE })).toBe('')
    expect(nextDay('2028-02-28')).toBe('2028-02-29')
  })

  it('manda FormData sin forzar Content-Type y con credenciales', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(contract))
    await uploadContract(contract.id, { file: new File(['%PDF-'], 'a.pdf'), signed: true, revision: 1 })
    const options = fetch.mock.calls[0][1]
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.headers['Content-Type']).toBeUndefined()
    expect(options.credentials).toBe('include')
    expect(options.body.get('firmado')).toBe('true')
  })

  it('guarda borrador sin archivo y no pide fecha de firma', async () => {
    const ui = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
      if (url.includes('/inquilinos/tenant-one')) return json(tenant)
      if (url.endsWith('/contratos') && options.method === 'POST') return json(contract, 201)
      return json(contract)
    })
    renderRoute('/contratos/nuevo?inquilino_id=tenant-one')
    await screen.findByLabelText(/Inicio de vigencia/)
    expect(screen.queryByLabelText(/fecha de firma/i)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Inicio de vigencia/), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByLabelText(/Fin de vigencia/), { target: { value: '2027-08-31' } })
    await ui.click(screen.getByRole('button', { name: 'Guardar borrador' }))
    expect(await screen.findByText('El borrador se guardó. Podés completar el PDF firmado más adelante.')).toBeInTheDocument()
    expect(fetch.mock.calls.filter(([url, options]) => url.endsWith('/contratos') && options.method === 'POST')).toHaveLength(1)
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/documentos'))).toBe(false)
  })

  it('no duplica el contrato si falla la subida posterior al alta', async () => {
    const ui = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
      if (url.includes('/inquilinos/tenant-one')) return json(tenant)
      if (url.endsWith('/documentos')) return json({ detail: { message: 'Storage no disponible' } }, 503)
      if (url.endsWith('/contratos') && options.method === 'POST') return json(contract, 201)
      return json(contract)
    })
    renderRoute('/contratos/nuevo?inquilino_id=tenant-one')
    await screen.findByLabelText(/Inicio de vigencia/)
    fireEvent.change(screen.getByLabelText(/Inicio de vigencia/), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByLabelText(/Fin de vigencia/), { target: { value: '2027-08-31' } })
    await ui.upload(screen.getByLabelText('Documento del contrato'), new File(['%PDF-'], 'contrato.pdf', { type: 'application/pdf' }))
    await ui.click(screen.getByRole('checkbox'))
    await ui.click(screen.getByRole('button', { name: 'Guardar contrato firmado' }))
    expect(await screen.findByText(/Los datos quedaron guardados, pero no se pudo cargar el PDF/)).toBeInTheDocument()
    expect(screen.getByLabelText('Adjuntar documento')).toBeInTheDocument()
    expect(fetch.mock.calls.filter(([url, options]) => url.endsWith('/contratos') && options.method === 'POST')).toHaveLength(1)
  })

  it('muestra errores de validación y no envía un período inválido', async () => {
    const ui = userEvent.setup()
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(tenant))
    renderRoute('/contratos/nuevo?inquilino_id=tenant-one')
    await screen.findByLabelText(/Inicio de vigencia/)
    fireEvent.change(screen.getByLabelText(/Inicio de vigencia/), { target: { value: '2027-09-01' } })
    fireEvent.change(screen.getByLabelText(/Fin de vigencia/), { target: { value: '2026-08-31' } })
    await ui.click(screen.getByRole('button', { name: 'Guardar borrador' }))
    expect(screen.getByText('La finalización debe ser posterior al inicio.')).toBeInTheDocument()
    expect(fetch.mock.calls.every(([, options]) => options.method !== 'POST')).toBe(true)
  })

  it('impide confirmar firmado sin PDF', async () => {
    const ui = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(tenant))
    renderRoute('/contratos/nuevo?inquilino_id=tenant-one')
    await screen.findByLabelText(/Inicio de vigencia/)
    await ui.click(screen.getByRole('checkbox'))
    await ui.click(screen.getByRole('button', { name: 'Guardar contrato firmado' }))
    expect(screen.getByText('Seleccioná el PDF del contrato.')).toBeInTheDocument()
  })

  it('prepara una renovación sin modificar el contrato anterior', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...contract, estado: 'firmado' }))
    renderRoute('/contratos/nuevo?anterior=contract-one')
    expect(await screen.findByLabelText(/Inicio de vigencia/)).toHaveValue('2027-09-01')
    expect(screen.getByLabelText(/Fin de vigencia/)).toHaveValue('')
    expect(screen.queryByRole('button', { name: 'Cambiar inquilino' })).not.toBeInTheDocument()
  })
})

describe('consulta y gestión de contratos', () => {
  it.each(['inquilino', 'propietario'])('solo ofrece lectura al %s', async role => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...contract, estado: 'firmado', vigencia: 'Vigente', documentos: [{ id: 'doc-one', version: 1, nombre_archivo: 'contrato.pdf', tamano: 500, firmado: true, created_at: '2026-09-12' }] }))
    renderRoute(`/${role}/contratos/contract-one`, role)
    expect(await screen.findByRole('button', { name: 'Descargar versión 1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar PDF' })).not.toBeInTheDocument()
    expect(screen.queryByText('Registrar renovación')).not.toBeInTheDocument()
    expect(screen.queryByText('Editar borrador')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Fecha de finalización')).not.toBeInTheDocument()
  })

  it('un error en una búsqueda no deja resultados de los filtros anteriores', async () => {
    const ui = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
      if (url.includes('search=')) return json({ detail: 'No se pudo actualizar la búsqueda.' }, 503)
      return json({ items: [contract], total: 1, page: 1, page_size: 10, total_pages: 1 })
    })
    renderRoute('/contratos')
    expect(await screen.findByText(contract.direccion)).toBeInTheDocument()
    await ui.type(screen.getByLabelText('Buscar contratos'), 'Otro')
    await waitFor(() => expect(screen.getByText('No se pudo actualizar la búsqueda.')).toBeInTheDocument())
    expect(screen.queryByText(contract.direccion)).not.toBeInTheDocument()
  })

  it('no permite editar las fechas de un contrato firmado por URL directa', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...contract, estado: 'firmado' }))
    renderRoute('/contratos/contract-one/editar')
    expect(await screen.findByText('Solo se pueden editar las fechas de un borrador.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Guardar/ })).not.toBeInTheDocument()
  })

  it('inicia el análisis de la última versión firmada sin confirmar cláusulas automáticamente', async () => {
    const ui = userEvent.setup()
    const signedContract = { ...contract, estado: 'firmado', vigencia: 'Vigente', documentos: [{ id: 'doc-one', version: 2, nombre_archivo: 'contrato.pdf', tamano: 500, firmado: true, created_at: '2026-09-12' }] }
    const pending = { id: 'analysis-one', contrato_id: contract.id, documento_id: 'doc-one', estado: 'pendiente', completo: false, paginas_total: null, lectura_paginas: [], intentos: 0, ultimo_error: null, created_at: '2026-09-21', updated_at: '2026-09-21', clausulas: [] }
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
      if (url.endsWith('/analisis') && options.method === 'POST') return json(pending, 202)
      if (url.endsWith('/analisis')) return json(null)
      return json(signedContract)
    })
    renderRoute('/contratos/contract-one')
    await ui.click(await screen.findByRole('button', { name: 'Analizar cláusulas' }))
    expect(await screen.findByText(/Analizando el contrato/)).toBeInTheDocument()
    expect(fetch.mock.calls.some(([url, options]) => url.endsWith('/analisis') && options.method === 'POST')).toBe(true)
    expect(screen.queryByText('Confirmada')).not.toBeInTheDocument()
  })

  it('confirma una propuesta sólo como contexto, incluso si una versión anterior la marcó operativa', async () => {
    const ui = userEvent.setup()
    const signedContract = { ...contract, estado: 'firmado', vigencia: 'Vigente', documentos: [{ id: 'doc-one', version: 1, nombre_archivo: 'contrato.pdf', tamano: 500, firmado: true, created_at: '2026-09-12' }] }
    const clause = { id: 'clause-one', ordinal: 1, numero: 'NOVENA', titulo: 'Daños', paginas: [5, 6], evidencias: [{ pagina: 5, texto: 'El inquilino responde' }, { pagina: 6, texto: 'cuando el daño le resulte imputable.' }], texto_original: 'El inquilino responde\n\ncuando el daño le resulte imputable.', resumen: 'La responsabilidad depende de que el daño sea imputable.', categoria: 'danio', responsable: 'condicional', uso_clasificador: 'operativa', condiciones: 'Debe existir imputabilidad.', referencias: [], confianza: 0.91, estado_revision: 'pendiente', revision: 1, revisado_por: null, revisado_en: null }
    const analysis = { id: 'analysis-one', contrato_id: contract.id, documento_id: 'doc-one', estado: 'completado', completo: true, paginas_total: 13, lectura_paginas: [], intentos: 1, ultimo_error: null, created_at: '2026-09-21', updated_at: '2026-09-21', clausulas: [clause] }
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (url.includes('/clausulas/')) return json({ ...analysis, clausulas: [{ ...clause, uso_clasificador: 'contexto', estado_revision: 'confirmada', revision: 2 }] })
      if (url.endsWith('/analisis')) return json(analysis)
      return json(signedContract)
    })
    renderRoute('/contratos/contract-one')
    await ui.click(await screen.findByRole('button', { name: 'Confirmar como contexto' }))
    expect(await screen.findByText('Confirmada')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Editar revisión' })).toBeInTheDocument()
    const call = fetch.mock.calls.find(([url]) => url.includes('/clausulas/'))
    expect(JSON.parse(call[1].body)).toEqual({ accion: 'confirmar', revision: 1 })
  })

  it('permite corregir una propuesta antes de confirmarla', async () => {
    const ui = userEvent.setup()
    const signedContract = { ...contract, estado: 'firmado', vigencia: 'Vigente', documentos: [{ id: 'doc-one', version: 1, nombre_archivo: 'contrato.pdf', tamano: 500, firmado: true, created_at: '2026-09-12' }] }
    const clause = { id: 'clause-one', ordinal: 1, numero: 'NOVENA', titulo: 'Daños', paginas: [5], evidencias: [{ pagina: 5, texto: 'El inquilino responde cuando el daño le resulte imputable.' }], texto_original: 'El inquilino responde cuando el daño le resulte imputable.', resumen: 'Resumen propuesto.', categoria: 'danio', responsable: 'condicional', uso_clasificador: 'operativa', condiciones: 'Debe existir imputabilidad.', referencias: [], confianza: 0.91, estado_revision: 'pendiente', revision: 1, revisado_por: null, revisado_en: null }
    const analysis = { id: 'analysis-one', contrato_id: contract.id, documento_id: 'doc-one', estado: 'completado', completo: true, paginas_total: 13, lectura_paginas: [], intentos: 1, ultimo_error: null, created_at: '2026-09-21', updated_at: '2026-09-21', clausulas: [clause] }
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (url.includes('/clausulas/')) return json({ ...analysis, clausulas: [{ ...clause, resumen: 'Resumen corregido.', estado_revision: 'editada', revision: 2 }] })
      if (url.endsWith('/analisis')) return json(analysis)
      return json(signedContract)
    })
    renderRoute('/contratos/contract-one')
    await ui.click(await screen.findByRole('button', { name: 'Editar', exact: true }))
    const summary = await screen.findByLabelText(/Resumen/)
    await ui.clear(summary)
    await ui.type(summary, 'Resumen corregido.')
    expect(screen.getByLabelText(/Uso en reclamos/)).toHaveValue('contexto')
    await ui.click(screen.getByRole('button', { name: 'Guardar revisión' }))
    expect(await screen.findByText('Editada')).toBeInTheDocument()
    const call = fetch.mock.calls.find(([url]) => url.includes('/clausulas/'))
    expect(JSON.parse(call[1].body)).toMatchObject({
      accion: 'editar', revision: 1, resumen: 'Resumen corregido.',
      categoria: 'danio', responsable: 'condicional', uso_clasificador: 'contexto',
    })
  })

  it('exige seleccionar operativa en el editor para habilitar una propuesta', async () => {
    const ui = userEvent.setup()
    const signedContract = { ...contract, estado: 'firmado', vigencia: 'Vigente', documentos: [{ id: 'doc-one', version: 1, nombre_archivo: 'contrato.pdf', tamano: 500, firmado: true, created_at: '2026-09-12' }] }
    const clause = { id: 'clause-one', ordinal: 1, numero: 'SEXTA', titulo: 'Gastos', paginas: [2], evidencias: [{ pagina: 2, texto: 'Texto sujeto a revisión.' }], texto_original: 'Texto sujeto a revisión.', resumen: 'Resumen propuesto.', categoria: 'expensa', responsable: 'condicional', uso_clasificador: 'contexto', condiciones: 'Revisar la excepción.', referencias: [], confianza: 0.6, estado_revision: 'pendiente', revision: 1, habilitada_para_reclamos: false }
    const analysis = { id: 'analysis-one', contrato_id: contract.id, documento_id: 'doc-one', estado: 'completado', completo: true, paginas_total: 2, lectura_paginas: [], intentos: 1, ultimo_error: null, created_at: '2026-09-21', updated_at: '2026-09-21', clausulas: [clause] }
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (url.includes('/clausulas/')) return json({ ...analysis, clausulas: [{ ...clause, uso_clasificador: 'operativa', estado_revision: 'editada', revision: 2, habilitada_para_reclamos: true }] })
      if (url.endsWith('/analisis')) return json(analysis)
      return json(signedContract)
    })

    renderRoute('/contratos/contract-one')
    await ui.click(await screen.findByRole('button', { name: 'Editar', exact: true }))
    expect(screen.getByLabelText(/Uso en reclamos/)).toHaveValue('contexto')
    await ui.selectOptions(screen.getByLabelText(/Uso en reclamos/), 'operativa')
    expect(screen.getByText(/Compará la interpretación y las excepciones/)).toBeInTheDocument()
    await ui.click(screen.getByRole('button', { name: 'Guardar y habilitar' }))

    const call = fetch.mock.calls.find(([url]) => url.includes('/clausulas/'))
    expect(JSON.parse(call[1].body)).toMatchObject({ accion: 'editar', revision: 1, uso_clasificador: 'operativa' })
    expect(await screen.findByText('Habilitada para reclamos')).toBeInTheDocument()
  })

  it('permite descartar una propuesta sin incorporarla al contexto', async () => {
    const ui = userEvent.setup()
    const signedContract = { ...contract, estado: 'firmado', vigencia: 'Vigente', documentos: [{ id: 'doc-one', version: 1, nombre_archivo: 'contrato.pdf', tamano: 500, firmado: true, created_at: '2026-09-12' }] }
    const clause = { id: 'clause-one', ordinal: 1, numero: 'NOVENA', titulo: 'Daños', paginas: [5], evidencias: [{ pagina: 5, texto: 'Texto contractual.' }], texto_original: 'Texto contractual.', resumen: 'Resumen propuesto.', categoria: 'danio', responsable: 'no_especificado', uso_clasificador: 'contexto', condiciones: null, referencias: [], confianza: 0.7, estado_revision: 'pendiente', revision: 3, revisado_por: null, revisado_en: null }
    const analysis = { id: 'analysis-one', contrato_id: contract.id, documento_id: 'doc-one', estado: 'completado', completo: true, paginas_total: 13, lectura_paginas: [], intentos: 1, ultimo_error: null, created_at: '2026-09-21', updated_at: '2026-09-21', clausulas: [clause] }
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (url.includes('/clausulas/')) return json({ ...analysis, clausulas: [{ ...clause, estado_revision: 'descartada', revision: 4 }] })
      if (url.endsWith('/analisis')) return json(analysis)
      return json(signedContract)
    })
    renderRoute('/contratos/contract-one')
    await ui.click(await screen.findByRole('button', { name: 'Descartar' }))
    expect(await screen.findByText('Descartada')).toBeInTheDocument()
    const call = fetch.mock.calls.find(([url]) => url.includes('/clausulas/'))
    expect(JSON.parse(call[1].body)).toEqual({ accion: 'descartar', revision: 3 })
  })

  it('conserva propuestas rechazadas como auditoría sin acciones de confirmación', async () => {
    const signedContract = { ...contract, estado: 'firmado', vigencia: 'Vigente', documentos: [{ id: 'doc-one', version: 1, nombre_archivo: 'contrato.pdf', tamano: 500, firmado: true, created_at: '2026-09-12' }] }
    const proposal = { numero: 'NOVENA (d)', titulo: 'Roturas imputables', evidencias: [{ pagina: 5, texto: 'Texto no verificable' }], paginas: [5], texto_original: 'Texto no verificable', resumen: 'Responsabilidad condicionada.', categoria: 'reparacion', responsable: 'condicional', uso_clasificador: 'operativa', condiciones: 'Causa imputable.', referencias: [], confianza: 0.8 }
    const analysis = { id: 'analysis-one', contrato_id: contract.id, documento_id: 'doc-one', estado: 'incompleto', completo: false, paginas_total: 13, lectura_paginas: [], intentos: 1, ultimo_error: 'Una propuesta requiere revisión.', created_at: '2026-09-21', updated_at: '2026-09-21', clausulas: [], propuestas_rechazadas: [{ ordinal: 1, propuesta: proposal, motivo: 'El fragmento no es literal.', evidencias_invalidas: proposal.evidencias }] }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async url => url.endsWith('/analisis') ? json(analysis) : json(signedContract))

    renderRoute('/contratos/contract-one')

    expect(await screen.findByText('Propuestas que requieren auditoría')).toBeInTheDocument()
    expect(screen.getByText('El fragmento no es literal.')).toBeInTheDocument()
    expect(screen.getByText('Texto no verificable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirmar' })).not.toBeInTheDocument()
  })
})
