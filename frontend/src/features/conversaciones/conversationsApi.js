import { apiRequest } from '../../services/apiClient.js'

const base = (id, thread = false) => `/conversaciones/${thread ? 'hilos' : 'solicitudes'}/${encodeURIComponent(id)}`
export function getConversation(id, { before, after, signal, thread = false } = {}) {
  const query = new URLSearchParams({ limite: '30' })
  if (before != null) query.set('antes', String(before))
  if (after != null) query.set('despues', String(after))
  return apiRequest(`${base(id, thread)}?${query}`, { signal })
}
export function sendMessage(id, payload, { thread = false } = {}) {
  return apiRequest(`${base(id, thread)}/mensajes`, { method: 'POST', body: JSON.stringify(payload) })
}
export function markConversationRead(id, through, { signal, thread = false } = {}) {
  return apiRequest(`${base(id, thread)}/lectura`, { method: 'POST', body: JSON.stringify({ hasta_numero: through }), signal })
}
export const getInbox = (page = 1, { signal } = {}) => apiRequest(`/conversaciones/bandeja?page=${page}&page_size=20`, { signal })
export const openQuestions = (id, key) => apiRequest(`${base(id)}/consultas`, { method: 'POST', body: JSON.stringify({ request_id: key }) })
export const finishQuestions = (id, key) => apiRequest(`${base(id, true)}/finalizar-consultas`, { method: 'POST', body: JSON.stringify({ request_id: key }) })
export const questionsChanged = (id) => window.dispatchEvent(new CustomEvent('aari:consultas-cambiaron', { detail: id }))
