import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'

export function useListFilters(fields) {
  const [searchParams, setSearchParams] = useSearchParams()
  const filterKey = JSON.stringify(fields.map(({ name }) => searchParams.get(name) ?? ''))
  const filters = useMemo(() => Object.fromEntries(fields.map(({ name }, index) => [name, JSON.parse(filterKey)[index]])), [fields, filterKey])
  const search = searchParams.get('search') ?? ''
  const requestedPage = Number(searchParams.get('page'))
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const queryKey = JSON.stringify([page, search, filterKey])
  const panelKey = JSON.stringify([filterKey, search])
  const hasFilters = Boolean(search || Object.values(filters).some(Boolean))

  const applyFilters = (draft, draftSearch = search) => {
    const params = new URLSearchParams(searchParams)
    params.delete('page')
    const normalizedSearch = draftSearch.trim()
    if (normalizedSearch) params.set('search', normalizedSearch)
    else params.delete('search')
    fields.forEach(({ name }) => {
      const value = draft[name]?.trim() ?? ''
      if (value) params.set(name, value)
      else params.delete(name)
    })
    setSearchParams(params)
  }
  const clearFilters = () => {
    const params = new URLSearchParams(searchParams)
    for (const name of ['page', 'search', ...fields.map(({ name }) => name)]) params.delete(name)
    setSearchParams(params)
  }
  const goToPage = useCallback((nextPage, options) => {
    const params = new URLSearchParams(searchParams)
    params.set('page', String(nextPage))
    setSearchParams(params, options)
  }, [searchParams, setSearchParams])
  // También recupera una última página que desapareció tras eliminar registros.
  const normalizePage = useCallback((totalPages) => {
    if (!Number.isInteger(totalPages) || totalPages < 0) return false
    const lastPage = Math.max(1, totalPages)
    if (page <= lastPage) return false
    goToPage(lastPage, { replace: true })
    return true
  }, [page, goToPage])
  return { page, search, filters, panelKey, queryKey, hasFilters, applyFilters, clearFilters, goToPage, normalizePage }
}
