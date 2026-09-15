import { useEffect, useState } from 'react'

export const CLAIMS_POLLING_INTERVAL_MS = 30_000

export function usePollingResource(load, initialData) {
  const [data, setData] = useState(initialData)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let controller = null
    let disposed = false
    let inFlight = false

    const refresh = async () => {
      if (inFlight) return
      inFlight = true
      controller = new AbortController()

      try {
        const response = await load(controller.signal)
        if (!disposed) {
          setData(response)
          setError('')
        }
      } catch (requestError) {
        if (!disposed && requestError.name !== 'AbortError') {
          setError(requestError.message)
        }
      } finally {
        inFlight = false
        if (!disposed) setIsLoading(false)
      }
    }

    void refresh()
    const intervalId = window.setInterval(refresh, CLAIMS_POLLING_INTERVAL_MS)

    return () => {
      disposed = true
      window.clearInterval(intervalId)
      controller?.abort()
    }
  }, [load])

  return { data, error, isLoading }
}
