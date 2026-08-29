import { useEffect, useMemo, useState } from 'react'
import * as authApi from './api/authApi.js'
import { AuthContext } from './authContext.js'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let active = true
    authApi
      .getCurrentUser()
      .then(({ user: currentUser }) => {
        if (active) setUser(currentUser)
      })
      .catch(() => {
        if (active) setUser(null)
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const value = useMemo(
    () => ({
      isLoading,
      user,
      async login(credentials) {
        const response = await authApi.login(credentials)
        setUser(response.user)
        return response.user
      },
      async logout() {
        try {
          await authApi.logout()
        } finally {
          setUser(null)
        }
      },
    }),
    [isLoading, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
