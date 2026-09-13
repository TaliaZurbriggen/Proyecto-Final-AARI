// QA visual optativa: navegador aislado y respuestas API sintéticas; sin Supabase.
// Requiere Playwright disponible en AARI_BROWSER_MODULES o node_modules local.
import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import assert from 'node:assert/strict'

const require = createRequire(process.env.AARI_BROWSER_MODULES ? resolve(process.env.AARI_BROWSER_MODULES, 'package.json') : import.meta.url)
const { chromium } = require('playwright')
const origin = process.env.AARI_PREVIEW_URL || 'http://localhost:5183'
const output = resolve('../backend/artifacts/hu29-ui')
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage()
const issues = []
page.on('pageerror', error => issues.push(error.message))
let role = 'administrador'
let contract = {
  id: '00000000-0000-0000-0000-000000000101', inquilino_id: '00000000-0000-0000-0000-000000000103',
  propietario_id: '00000000-0000-0000-0000-000000000102', propiedad_id: '00000000-0000-0000-0000-000000000120',
  inquilino_nombre: 'Inquilino de demostración', propietario_nombre: 'Propietario de demostración',
  direccion: 'Inmueble de demostración 123', localidad: 'San Francisco', provincia: 'Córdoba',
  fecha_inicio: '2026-09-01', fecha_fin: '2027-08-31', fecha_finalizacion: null,
  contrato_anterior_id: null, estado: 'borrador', vigencia: 'Borrador', revision: 1, documentos: [],
}
const tenant = { id: contract.inquilino_id, nombre_completo: contract.inquilino_nombre,
  propiedad: { id: contract.propiedad_id, direccion: contract.direccion } }
await page.route('**/*', async route => {
  const request = route.request()
  const url = new URL(request.url())
  if (url.origin === origin) return route.continue()
  if (url.origin !== 'http://localhost:8000') return route.abort()
  const json = data => route.fulfill({ json: data })
  if (url.pathname === '/auth/me') return json({ user: { id: contract.inquilino_id, email: 'administracion.inmobiliaria@example.com', rol: role, primer_ingreso: false } })
  if (url.pathname.startsWith('/inquilinos/')) return json(tenant)
  if (url.pathname === '/inquilinos') return json({ items: [tenant], total: 1, total_pages: 1 })
  if (url.pathname === '/contratos' && request.method() === 'POST') {
    contract = { ...contract, ...request.postDataJSON() }
    return json(contract)
  }
  if (url.pathname === '/contratos') return json({ items: [contract], total: 1, page: 1, page_size: 10, total_pages: 1 })
  if (url.pathname === '/contratos/' + contract.id) return json(contract)
  if (url.pathname.endsWith('/documentos')) {
    contract = { ...contract, estado: 'firmado', vigencia: 'Vigente', revision: 2,
      documentos: [{ id: 'doc-demo', version: 1, nombre_archivo: 'contrato-demo.pdf', tamano: 400, firmado: true, created_at: '2026-09-13T12:00:00Z' }] }
    return json(contract)
  }
  throw new Error('Unexpected synthetic API route: ' + url.pathname)
})
const results = []
try {
  for (const width of [320, 390, 768, 820, 1024, 1280, 1312, 1320, 1366, 1440, 1536, 1920]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const [name, path, heading] of [
      ['listado', '/contratos', 'Contratos de alquiler'],
      ['carga', '/contratos/nuevo?inquilino_id=' + tenant.id, 'Cargar contrato'],
      ['detalle', '/contratos/' + contract.id, contract.direccion],
    ]) {
      await page.goto(origin + path)
      await page.getByRole('heading', { name: heading, exact: true }).waitFor()
      if (name === 'carga') await page.getByText(tenant.nombre_completo, { exact: true }).waitFor()
      await page.evaluate(() => document.fonts.ready)
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
      assert.equal(await page.evaluate(() => scrollX), 0, 'La cabecera no debe desplazar la página')
      if ([390, 768, 1440, 1536].includes(width)) {
        await page.screenshot({ path: resolve(output, name + '-' + width + '.png'), fullPage: true })
      }
      results.push({ name, width, overflow })
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto(origin + '/contratos/nuevo?inquilino_id=' + tenant.id)
  await page.getByLabel('Inicio de vigencia').fill('2026-09-01')
  // Los controles de fecha nativos tienen segmentos internos (día/mes/año).
  for (let tabs = 0; tabs < 6; tabs++) {
    await page.keyboard.press('Tab')
    if (await page.getByLabel('Fin de vigencia').evaluate(el => el === document.activeElement)) break
  }
  assert.equal(await page.getByLabel('Fin de vigencia').evaluate(el => el === document.activeElement), true)
  await page.getByLabel('Fin de vigencia').fill('2027-08-31')
  await page.getByRole('button', { name: 'Guardar borrador' }).click()
  await page.getByText('El borrador se guardó.', { exact: false }).waitFor()
  await page.getByLabel('Adjuntar documento').setInputFiles({ name: 'contrato-demo.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-synthetic-browser-test') })
  await page.getByRole('checkbox', { name: 'Este PDF es el contrato firmado' }).check()
  await page.getByRole('button', { name: 'Guardar PDF' }).click()
  await page.getByRole('button', { name: 'Descargar versión 1' }).waitFor()
  for (const currentRole of ['inquilino', 'propietario']) {
    role = currentRole
    await page.goto(origin + '/' + role + '/contratos/' + contract.id)
    await page.getByRole('button', { name: 'Descargar versión 1' }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Guardar PDF' }).count(), 0)
    assert.equal(await page.getByText('Registrar renovación', { exact: true }).count(), 0)
    await page.screenshot({ path: resolve(output, role + '-lectura.png'), fullPage: true })
  }
  console.log(JSON.stringify({ screens: results, browserErrors: issues, flow: 'create draft -> attach signed -> read-only portals', screenshots: output }, null, 2))
  assert.deepEqual(issues, [])
  assert.equal(results.some(result => result.overflow), false, 'Horizontal overflow detected')
} finally {
  await browser.close()
}
