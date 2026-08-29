import { apiRequest } from '../../../services/apiClient.js'

export function login(credentials) {
  return apiRequest('/auth/login', {
    body: JSON.stringify(credentials),
    method: 'POST',
  })
}

export function getCurrentUser() {
  return apiRequest('/auth/me')
}

export function logout() {
  return apiRequest('/auth/logout', { method: 'POST' })
}
