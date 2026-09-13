// Regresión responsive real de la cabecera compartida. Todas las APIs son dobles.
// npm run build + preview; Playwright externo opcional en AARI_BROWSER_MODULES.
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import assert from 'node:assert/strict'

const require = createRequire(process.env.AARI_BROWSER_MODULES ? resolve(process.env.AARI_BROWSER_MODULES, 'package.json') : import.meta.url)
const { chromium } = require('playwright')
const origin = process.env.AARI_PREVIEW_URL || 'http://localhost:5183'
const output = resolve('../backend/artifacts/hu29-ui')
const widths = [320, 390, 768, 820, 1024, 1280, 1312, 1320, 1366, 1440, 1441, 1536, 1920]
const modules = ['Propietarios', 'Propiedades', 'Inquilinos', 'Proveedores', 'Operadores', 'Contratos']
const browser = await chromium.launch({ channel: 'chrome', headless: true })
let profile = 'demo@example.com'
const errors = []
const results = []
try {
  const page = await browser.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.origin === origin) return route.continue()
    if (url.origin !== 'http://localhost:8000') return route.abort()
    if (url.pathname === '/auth/me') return route.fulfill({ json: { user: { id: 'qa-header', email: profile, rol: 'administrador', primer_ingreso: false } } })
    assert.equal(route.request().method(), 'GET', 'Esta prueba no escribe datos')
    if (url.pathname === '/especialidades') return route.fulfill({ json: [] })
    if (url.pathname === '/usuarios/operadores' || modules.some(name => url.pathname === '/' + name.toLowerCase())) {
      return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 10, total_pages: 1 } })
    }
    errors.push('API simulada no prevista: ' + url.pathname)
    return route.abort()
  })

  for (const longProfile of [false, true]) {
    profile = longProfile ? 'administracion.inmobiliaria.contratos@example.com' : 'demo@example.com'
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto(origin + '/contratos')
      await page.getByRole('heading', { name: 'Contratos de alquiler', exact: true }).waitFor()
      await page.evaluate(() => document.fonts.ready)
      for (const name of modules) {
        // Cambiar de módulo por navegación también debe conservar el ancho.
        const link = page.getByRole('navigation').getByRole('link', { name, exact: true })
        await link.click()
        await page.waitForURL('**/' + name.toLowerCase())
        await page.locator('h1').waitFor()
        await page.waitForFunction(() => {
          const nav = document.querySelector('header nav')
          const active = nav.querySelector('[aria-current="page"]')?.getBoundingClientRect()
          const bounds = nav.getBoundingClientRect()
          return active && active.left >= bounds.left - 1 && active.right <= bounds.right + 1
        })
        const state = await page.evaluate(() => {
          const viewport = document.documentElement.clientWidth
          const header = document.querySelector('header')
          const navigation = header.querySelector('nav').getBoundingClientRect()
          const brand = header.querySelector('a').getBoundingClientRect()
          const profile = header.querySelector('button[aria-label^="Abrir perfil"]').getBoundingClientRect()
          const controls = [...header.querySelectorAll('button,input')].filter(el => el.getClientRects().length)
          return {
            viewport, scrollWidth: document.documentElement.scrollWidth, scrollX, scrollY,
            accountOnBrandRow: Math.min(brand.bottom, profile.bottom) > Math.max(brand.top, profile.top),
            navFits: navigation.left >= -1 && navigation.right <= viewport + 1,
            controlsFit: controls.every(el => { const r = el.getBoundingClientRect(); return r.left >= -1 && r.right <= viewport + 1 }),
            overlap: controls.some((el, i) => controls.slice(i + 1).some(other => {
              const a = el.getBoundingClientRect(), b = other.getBoundingClientRect()
              return Math.min(a.right, b.right) > Math.max(a.left, b.left) && Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top)
            })),
          }
        })
        results.push({ width, longProfile, module: name, ...state })
        assert.ok(state.scrollWidth <= state.viewport, JSON.stringify(results.at(-1)))
        assert.ok(state.navFits && state.controlsFit && state.accountOnBrandRow && !state.overlap, JSON.stringify(results.at(-1)))
        assert.equal(state.scrollX, 0, 'No debe moverse horizontalmente la página')
        assert.equal(state.scrollY, 0, 'Centrar un enlace no debe mover verticalmente la página')
        assert.equal(await page.getByRole('button', { name: 'Abrir perfil de ' + profile }).count(), 1)
      }
    }
  }

  // El teclado permite llegar a todos los enlaces, incluso en el menú móvil.
  await page.setViewportSize({ width: 390, height: 900 })
  await page.goto(origin + '/contratos')
  await page.getByRole('heading', { name: 'Contratos de alquiler', exact: true }).waitFor()
  await page.getByRole('link', { name: 'Ir al inicio de AARI' }).focus()
  for (const name of modules) {
    await page.keyboard.press('Tab')
    assert.equal(await page.getByRole('navigation').getByRole('link', { name, exact: true }).evaluate(el => el === document.activeElement), true)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth && scrollX === 0), true)
  }
  await page.keyboard.press('Tab')
  assert.equal(await page.getByRole('searchbox', { name: 'Buscar en AARI' }).evaluate(el => el === document.activeElement), true)
  for (let tab = 0; tab < 3; tab++) await page.keyboard.press('Tab')
  assert.equal(await page.getByRole('button', { name: 'Cerrar sesión' }).evaluate(el => el === document.activeElement), true)
  assert.deepEqual(errors, [])
  await mkdir(output, { recursive: true })
  await writeFile(resolve(output, 'header-responsive.json'), JSON.stringify({ results, errors, keyboard: 'OK' }, null, 2))
  console.log(JSON.stringify({ checks: results.length, widths, profiles: 2, modules: 6, keyboard: 'OK', errors }))
} finally {
  await browser.close()
}
