export function listQuery({ page, pageSize, search, filters = {} }) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (search.trim()) params.set('search', search.trim())
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) params.set(key, String(value).trim())
  })
  return params.toString()
}
