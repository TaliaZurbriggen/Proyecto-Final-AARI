import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from './apiClient.js'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiClient', () => {
  it('usa localhost y envía la cookie de sesión por defecto', async () => {
    const response = new Response(JSON.stringify({ status: 'ok' }), {
      headers: { 'Content-Type': 'application/json' },
      status: 200,
    })
    const fetchMock = vi.fn().mockResolvedValue(response)
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/health')

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/health',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('deja que el navegador defina el límite multipart para FormData', async () => {
    const response = new Response(JSON.stringify({ status: 'ok' }), {
      headers: { 'Content-Type': 'application/json' },
      status: 200,
    })
    const fetchMock = vi.fn().mockResolvedValue(response)
    vi.stubGlobal('fetch', fetchMock)
    const body = new FormData()
    body.append('descripcion', 'Descripción suficientemente extensa.')

    await apiRequest('/reclamos', { body, method: 'POST' })

    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty('Content-Type')
  })
})
