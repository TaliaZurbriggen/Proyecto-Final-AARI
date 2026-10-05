import { useEffect, useState } from 'react'

// Cada respuesta pertenece a una consulta; una respuesta tardía no reemplaza otra.
export function useHistoryResource(key, load, enabled = true) {
  const [result, setResult] = useState({ key: null, data: null, error: '' })

  useEffect(() => {
    if (!enabled) return undefined
    const controller = new AbortController()
    let active = true
    load(controller.signal)
      .then((data) => {
        if (active) setResult({ key, data, error: '' })
      })
      .catch((error) => {
        if (active && error.name !== 'AbortError') {
          setResult({ key, data: null, error: error.message })
        }
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [key, load, enabled])

  return {
    data: enabled && result.key === key ? result.data : null,
    error: enabled && result.key === key ? result.error : '',
    isLoading: enabled && result.key !== key,
  }
}
