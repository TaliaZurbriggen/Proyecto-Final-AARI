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
})
