// QA HU13/HU14: navegación real del build con APIs ficticias y sin backend.
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import assert from 'node:assert/strict'

const require = createRequire(process.env.AARI_BROWSER_MODULES
  ? resolve(process.env.AARI_BROWSER_MODULES, 'package.json') : import.meta.url)
const { chromium } = require('playwright')
const origin = process.env.AARI_PREVIEW_URL || 'http://localhost:5185'
assert.ok(['localhost', '127.0.0.1'].includes(new URL(origin).hostname), 'Sólo preview local')
const output = resolve('../backend/artifacts/hu13-pr29-navigation')
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const results = []
try {
  await mkdir(output, { recursive: true })
  for (const role of ['administrador', 'operador']) {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } })
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await page.route('**/*', async route => {
        const url = new URL(route.request().url())
        if (url.origin === origin) return route.continue()
        if (!['localhost', '127.0.0.1'].includes(url.hostname)) return route.abort()
        assert.equal(route.request().method(), 'GET', 'Esta prueba no escribe datos')
        if (url.pathname === '/auth/me') return route.fulfill({ json: { user: {
          id: 'qa-staff', email: 'personal.sintetico@example.com', rol: role, primer_ingreso: false,
        } } })
        if (url.pathname === '/reclamos/escalados') return route.fulfill({ json: {
          items: [], total: 0, page: 1, page_size: 20, total_pages: 1,
        } })
        if (url.pathname === '/expensas') return route.fulfill({ json: {
          items: [], total: 0, page: 1, page_size: 20, total_pages: 1, fallidos: 0, propiedades: [],
        } })
        if (url.pathname === '/configuracion/correo-inmobiliaria') return route.fulfill({ json: {
          email: 'agency@example.com', valido: true,
        } })
        errors.push('API simulada no prevista: ' + url.pathname)
        return route.abort()
      })
      const queuePath = role === 'operador' ? '/operador/escalados' : '/escalados'
      await page.goto(origin + queuePath)
      for (const module of ['Casos escalados', 'Expensas']) {
        const nav = page.getByRole('navigation', { name: 'Navegación principal' })
        await nav.getByRole('link', { name: module, exact: true }).click()
        await page.getByRole('heading', { name: module, exact: true, level: 1 }).waitFor()
        await page.evaluate(() => document.fonts.ready)
        assert.equal(await nav.getByRole('link', { name: module, exact: true }).getAttribute('aria-current'), 'page')
        assert.equal(await page.getByRole('searchbox', { name: 'Buscar en AARI' }).count(), 0)
        const fits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
        assert.ok(fits, `${role}/${width}/${module}: sin scroll horizontal de página`)
        await page.screenshot({ path: resolve(output, `${role}-${width}-${module === 'Expensas' ? 'expensas' : 'escalados'}.png`) })
        results.push({ role, width, module, noHorizontalOverflow: fits })
      }
      await page.getByRole('link', { name: 'Ir al inicio de AARI' }).focus()
      const links = await page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link').all()
      for (const link of links) {
        await page.keyboard.press('Tab')
        assert.ok(await link.evaluate(element => element === document.activeElement), 'Orden de foco de navegación')
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth))
      }
      assert.deepEqual(errors, [])
      await page.close()
    }
  }
  await writeFile(resolve(output, 'results.json'), JSON.stringify({ results, keyboard: 'OK', realExternalCalls: 0 }, null, 2))
  console.log(JSON.stringify({ checks: results.length, roles: 2, widths: [390, 1440], keyboard: 'OK', realExternalCalls: 0 }))
} finally {
  await browser.close()
}
