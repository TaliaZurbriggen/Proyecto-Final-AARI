// El retorno viaja en el enlace, no depende de una entrada previa en el historial.
export function detailUrlWithListReturn(detailPath, { pathname, search = '' }) {
  const params = new URLSearchParams({ returnTo: `${pathname}${search}` })
  return `${detailPath}?${params}`
}

export function getSafeListReturnUrl(listPath, detailSearch) {
  const values = new URLSearchParams(detailSearch).getAll('returnTo')
  if (values.length !== 1) return listPath
  const returnTo = values[0]
  // Sólo el listado exacto del módulo y su query: nunca otra ruta o un origen externo.
  const hasControlCharacters = [...returnTo].some((character) => {
    const code = character.charCodeAt(0)
    return code < 32 || code === 127
  })
  if (returnTo.includes('\\') || returnTo.includes('#') || hasControlCharacters) return listPath
  return returnTo === listPath || returnTo.startsWith(`${listPath}?`)
    ? returnTo
    : listPath
}
