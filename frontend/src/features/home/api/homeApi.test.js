import { afterEach, describe, expect, it, vi } from 'vitest'
import { getAdminSummary } from './homeApi.js'

const valid = {
  consultado_en: '2026-10-05T15:30:00Z',
  propietarios: { total: 1 }, propiedades: { total: 2 }, inquilinos: { total: 3 },
  proveedores: { total: 4, activos: 2 }, operadores: { total: 2, activos: 1 },
  reclamos: { activos: 10, pendientes_clasificacion: 2 },
}
afterEach(() => vi.unstubAllGlobals())

describe('contrato del resumen administrativo', () => {
  it('recibe el resumen completo y transmite la cancelación de la consulta', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(valid), {
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    expect(await getAdminSummary({ signal: controller.signal })).toEqual(valid)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/admin/resumen'),
      expect.objectContaining({ signal: controller.signal }))
  })

  it.each([
    ['nulo', () => null],
    ['total negativo', (data) => ({ ...data, propietarios: { total: -1 } })],
    ['total decimal', (data) => ({ ...data, propiedades: { total: 1.5 } })],
    ['activos mayor que total', (data) => ({ ...data, operadores: { total: 1, activos: 2 } })],
    ['pendientes mayor que activos', (data) => ({ ...data, reclamos: { activos: 1, pendientes_clasificacion: 2 } })],
    ['fecha inválida', (data) => ({ ...data, consultado_en: 'no es una fecha' })],
    ['campo faltante', (data) => ({ ...data, inquilinos: {} })],
  ])('rechaza %s sin convertirlo en ceros', async (_, change) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(change(valid)), {
      headers: { 'Content-Type': 'application/json' },
    })))
    await expect(getAdminSummary()).rejects.toThrow('El resumen recibido está incompleto.')
  })
})
