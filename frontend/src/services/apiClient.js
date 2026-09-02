const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(
  /\/$/,
  '',
)

export class ApiError extends Error {
  constructor(message, { body, status }) {
    super(message)
    this.name = 'ApiError'
    this.body = body
    this.status = status
  }
}

export async function apiRequest(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      credentials: 'include',
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError(
      'No pudimos conectarnos con el servidor. Verificá que el backend esté activo.',
      { body: null, status: 0 },
    )
  }

  if (response.status === 204) return null

  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json')
    ? await response.json()
    : null

  if (!response.ok) {
    const detail = body?.detail
    const message =
      (typeof detail === 'string' ? detail : detail?.message) ??
      'No pudimos completar la operación. Intentá nuevamente.'
    throw new ApiError(message, { body, status: response.status })
  }

  return body
}
