import { describe, expect, it } from 'vitest'
import { detailUrlWithListReturn, getSafeListReturnUrl } from './listNavigation.js'

describe.each(['/propietarios', '/propiedades', '/inquilinos'])('retorno seguro a %s', (listPath) => {
  it('conserva la URL completa y caracteres especiales sin doble decodificación', () => {
    const search = `?${new URLSearchParams({ search: 'José & Ana + 10%', page: '3', con_inmuebles: 'false' })}`
    const detail = detailUrlWithListReturn(`${listPath}/id-sintetico`, { pathname: listPath, search })
    const query = detail.slice(detail.indexOf('?'))
    expect(getSafeListReturnUrl(listPath, query)).toBe(`${listPath}${search}`)
    expect(new URLSearchParams(getSafeListReturnUrl(listPath, query).split('?')[1]).get('search'))
      .toBe('José & Ana + 10%')
  })

  it('genera un retorno al listado incluso si no tiene filtros', () => {
    const detail = detailUrlWithListReturn(`${listPath}/id-sintetico`, { pathname: listPath })
    expect(getSafeListReturnUrl(listPath, detail.slice(detail.indexOf('?')))).toBe(listPath)
  })

  it.each([
    '', 'https://example.com/propietarios', '//example.com/propietarios',
    'javascript:alert(1)', '/login', '/propietarios-extra',
    '/propietarios/../login', '/propietarios\\..\\login', '%2Fpropietarios',
  ])('rechaza un retorno ajeno al listado: %s', (returnTo) => {
    expect(getSafeListReturnUrl(listPath, `?${new URLSearchParams({ returnTo })}`)).toBe(listPath)
  })

  it.each(['#ancla', '\\externo', '\n', '\t', '\u007f'])('rechaza caracteres ambiguos %j', (suffix) => {
    const returnTo = `${listPath}?search=Ana${suffix}`
    expect(getSafeListReturnUrl(listPath, `?${new URLSearchParams({ returnTo })}`)).toBe(listPath)
  })

  it('rechaza rutas de otro módulo aunque sean internas', () => {
    const returnTo = listPath === '/inquilinos' ? '/propiedades' : '/inquilinos'
    expect(getSafeListReturnUrl(listPath, `?${new URLSearchParams({ returnTo })}`)).toBe(listPath)
  })

  it('vuelve al listado si el retorno falta o está duplicado', () => {
    expect(getSafeListReturnUrl(listPath, '?search=Ana&page=2')).toBe(listPath)
    const query = new URLSearchParams({ returnTo: `${listPath}?page=2` })
    query.append('returnTo', `${listPath}?page=3`)
    expect(getSafeListReturnUrl(listPath, query.toString())).toBe(listPath)
  })
})
