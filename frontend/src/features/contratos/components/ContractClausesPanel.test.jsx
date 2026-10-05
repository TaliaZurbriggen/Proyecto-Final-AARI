import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ContractClausesPanel from './ContractClausesPanel.jsx'
import { getContractAnalysis, reviewContractClause, startContractAnalysis } from '../api/contratosApi.js'

vi.mock('../api/contratosApi.js', () => ({
  getContractAnalysis: vi.fn(), startContractAnalysis: vi.fn(), reviewContractClause: vi.fn(),
}))
const clause = { id: 'literal-one', ordinal: 1, numero: 'QUINTA', titulo: 'Cláusula QUINTA',
  paginas: [1, 2], evidencias: [{ pagina: 1, texto: 'El locador conserva' },
    { pagina: 2, texto: 'la aptitud para el uso durante la vigencia.' }],
  resumen: 'Interpretación pendiente. Revisá el texto original antes de completar esta cláusula.',
  categoria: 'otro', responsable: 'no_especificado', uso_clasificador: 'contexto',
  origen: 'literal', estado_revision: 'pendiente', revision: 1, habilitada_para_reclamos: false }
const analysis = { id: 'analysis-one', estado: 'completado', modo: 'literal',
  clausulas: [clause], historial_intentos: [], propuestas_rechazadas: [] }
function show() { render(<ContractClausesPanel contractId="contract-one" document={{ id: 'doc-one', version: 1 }} />) }
beforeEach(() => vi.resetAllMocks())

describe('extracción asistida y respaldo literal', () => {
  it('ofrece extracción local explícita desde el estado vacío', async () => {
    getContractAnalysis.mockResolvedValue(null)
    startContractAnalysis.mockResolvedValue(analysis)
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'Extraer sin IA' }))
    expect(startContractAnalysis).toHaveBeenCalledExactlyOnceWith('contract-one', 'doc-one', 'literal')
    expect(await screen.findByText(/Extracción local sin IA/)).toBeInTheDocument()
    expect(screen.getByText('Página 2')).toBeInTheDocument()
    expect(reviewContractClause).not.toHaveBeenCalled()
  })

  it('permite continuar sin IA después de un fallo sin ocultar lo revisado', async () => {
    const reviewed = { ...clause, id: 'old-one', origen: 'ia', estado_revision: 'editada',
      resumen: 'Interpretación ya revisada.', habilitada_para_reclamos: true }
    getContractAnalysis.mockResolvedValue({ ...analysis, modo: 'ia', estado: 'fallido',
      ultimo_error: 'Gemini no disponible.', clausulas: [reviewed] })
    startContractAnalysis.mockResolvedValue({ ...analysis, clausulas: [reviewed, clause],
      historial_intentos: [{ id: 'attempt-one', modo: 'ia', estado: 'fallido', error: 'Gemini no disponible.' }] })
    show()
    expect(await screen.findByRole('button', { name: 'Reintentar análisis' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Extraer sin IA' }))
    expect(await screen.findByText('Interpretación ya revisada.')).toBeInTheDocument()
    expect(screen.getByText('Habilitada para reclamos')).toBeInTheDocument()
    expect(screen.getByText('Historial de intentos (1)')).toBeInTheDocument()
  })

  it('abre el editor literal vacío y exige completar el resumen', async () => {
    getContractAnalysis.mockResolvedValue(analysis)
    reviewContractClause.mockResolvedValue({ ...analysis, clausulas: [{ ...clause, estado_revision: 'editada',
      resumen: 'El locador conserva la aptitud para el uso durante la vigencia.' }] })
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'Editar', exact: true }))
    const summary = screen.getByLabelText(/Resumen/)
    expect(summary).toHaveValue('')
    expect(summary).toBeRequired()
    expect(screen.getByLabelText(/Uso en reclamos/)).toHaveValue('contexto')
    fireEvent.change(summary, { target: { value: 'El locador conserva la aptitud para el uso durante la vigencia.' } })
    await userEvent.click(screen.getByRole('button', { name: 'Guardar revisión' }))
    expect(reviewContractClause.mock.calls[0][2]).toMatchObject({ accion: 'editar', uso_clasificador: 'contexto' })
    expect(await screen.findByText('Interpretación revisada de extracción literal')).toBeInTheDocument()
  })

  it('no cambia a otro modo mientras el intento sigue procesando', async () => {
    getContractAnalysis.mockResolvedValue({ ...analysis, estado: 'procesando', clausulas: [] })
    show()
    await screen.findByText(/Analizando el contrato/)
    expect(screen.queryByRole('button', { name: 'Extraer sin IA' })).not.toBeInTheDocument()
    expect(startContractAnalysis).not.toHaveBeenCalled()
  })

  it('rechaza un resumen formado sólo por espacios sin enviar la revisión', async () => {
    getContractAnalysis.mockResolvedValue(analysis)
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'Editar', exact: true }))
    fireEvent.change(screen.getByLabelText(/Resumen/), { target: { value: '   ' } })
    await userEvent.click(screen.getByRole('button', { name: 'Guardar revisión' }))
    expect(await screen.findByText('Completá el resumen de la cláusula.')).toBeInTheDocument()
    expect(reviewContractClause).not.toHaveBeenCalled()
  })

  it('muestra un error de la acción sin eliminar la evidencia anterior', async () => {
    getContractAnalysis.mockResolvedValue(analysis)
    startContractAnalysis.mockRejectedValue(new Error('No se pudo solicitar la extracción.'))
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'Extraer sin IA' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo solicitar la extracción.')
    expect(screen.getByText('El locador conserva')).toBeInTheDocument()
  })
})
