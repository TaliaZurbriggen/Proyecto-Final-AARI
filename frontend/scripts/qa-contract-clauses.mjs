// Revisión de HU30 con API sintética: no usa sesiones, documentos o servicios reales.
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import assert from 'node:assert/strict'

const require = createRequire(resolve(process.env.AARI_BROWSER_MODULES, 'package.json'))
const { chromium } = require('playwright')
const origin = process.env.AARI_PREVIEW_URL || 'http://127.0.0.1:5184'
const output = resolve('../backend/artifacts/hu30-asistida-ui')
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage()
const browserErrors = []
page.on('pageerror', error => browserErrors.push(error.message))
const contract = { id: '00000000-0000-0000-0000-000000000101', estado: 'firmado',
  inquilino_nombre: 'Inquilino de demostración', propietario_nombre: 'Propietario de demostración',
  direccion: 'Inmueble de demostración 123', localidad: 'San Francisco', provincia: 'Córdoba',
  fecha_inicio: '2026-09-01', fecha_fin: '2027-08-31', fecha_finalizacion: null,
  vigencia: 'Vigente', revision: 1, documentos: [{ id: 'doc-demo', version: 1,
    nombre_archivo: 'contrato-demo.pdf', tamano: 400, firmado: true, created_at: '2026-10-05T12:00:00Z' }] }
const clause = { id: 'literal-demo', ordinal: 1, numero: 'QUINTA', titulo: 'Cláusula 5',
  paginas: [1, 2], evidencias: [{ pagina: 1, texto: 'QUINTA: El locador conserva el inmueble' },
    { pagina: 2, texto: 'apto para el uso durante la vigencia.' }],
  resumen: 'Interpretación pendiente. Revisá el texto original antes de completar esta cláusula.',
  categoria: 'otro', responsable: 'no_especificado', uso_clasificador: 'contexto',
  origen: 'literal', estado_revision: 'pendiente', revision: 1, habilitada_para_reclamos: false }
let analysis = null
let requests = []
await page.route('**/*', async route => {
  const request = route.request()
  const url = new URL(request.url())
  if (url.origin === origin) return route.continue()
  if (!['localhost', '127.0.0.1'].includes(url.hostname) || url.port !== '8000') return route.abort()
  const json = data => route.fulfill({ json: data })
  if (url.pathname === '/auth/me') return json({ user: { id: contract.id,
    email: 'administracion@example.test', rol: 'administrador', primer_ingreso: false } })
  if (url.pathname.endsWith('/analisis')) {
    if (request.method() === 'POST') {
      requests.push(request.postDataJSON())
      analysis = { estado: 'completado', modo: 'literal', clausulas: [clause],
        historial_intentos: [{ id: 'old-attempt', modo: 'ia', estado: 'fallido', error: 'Servicio no disponible.' }],
        propuestas_rechazadas: [] }
    }
    return json(analysis)
  }
  if (url.pathname.includes('/clausulas/')) {
    const payload = request.postDataJSON()
    requests.push(payload)
    analysis = { ...analysis, clausulas: [{ ...clause, ...payload, estado_revision: 'editada',
      habilitada_para_reclamos: payload.uso_clasificador === 'operativa', revision: 2 }] }
    return json(analysis)
  }
  if (url.pathname === '/contratos/' + contract.id) return json(contract)
  throw new Error('Ruta sintética no prevista: ' + url.pathname)
})
const checks = []
try {
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 950 })
    for (const state of ['vacio', 'fallido', 'literal']) {
      analysis = state === 'vacio' ? null : state === 'fallido'
        ? { estado: 'fallido', modo: 'ia', ultimo_error: 'Servicio no disponible.', clausulas: [], historial_intentos: [] }
        : { estado: 'completado', modo: 'literal', clausulas: [clause], historial_intentos: [] }
      await page.goto(origin + '/contratos/' + contract.id)
      await page.getByRole('button', { name: 'Extraer sin IA' }).waitFor()
      await page.evaluate(() => document.fonts.ready)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)
      const button = page.getByRole('button', { name: 'Extraer sin IA' })
      assert.ok((await button.boundingBox()).height >= 44)
      await page.screenshot({ path: resolve(output, `${state}-${width}.png`), fullPage: true })
      if (state === 'literal') {
        await page.getByRole('button', { name: 'Editar', exact: true }).click()
        const summary = page.getByLabel('Resumen', { exact: false })
        await summary.waitFor()
        const selects = await Promise.all(['Categoría', 'Responsable indicado', 'Uso en reclamos']
          .map(name => page.getByRole('combobox', { name, exact: true }).boundingBox()))
        assert.ok(selects.every(box => Math.abs(box.height - selects[0].height) <= 1))
        if (width >= 768) assert.ok(selects.every(box => Math.abs(box.y - selects[0].y) <= 1))
        assert.equal(await summary.inputValue(), '')
        await summary.fill('El locador conserva el inmueble apto para el uso durante la vigencia.')
        await summary.focus()
        await page.keyboard.press('Tab')
        assert.equal(await page.getByLabel('Categoría', { exact: false }).evaluate(el => el === document.activeElement), true)
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)
        await page.evaluate(() => window.scrollTo(0, 0))
        await page.screenshot({ path: resolve(output, `editor-${width}.png`), fullPage: true })
        await page.getByRole('button', { name: 'Guardar revisión' }).click()
        await page.getByText('Interpretación revisada de extracción literal').waitFor()
        assert.equal(requests.at(-1).uso_clasificador, 'contexto')
      }
      checks.push({ width, state, horizontalOverflow: false, touchTarget: '>=44px' })
    }
  }
  analysis = { estado: 'fallido', modo: 'ia', ultimo_error: 'Servicio no disponible.', clausulas: [] }
  await page.goto(origin + '/contratos/' + contract.id)
  await page.getByRole('button', { name: 'Extraer sin IA' }).click()
  await page.getByText('Historial de intentos (1)').waitFor()
  assert.deepEqual(requests.at(-1), { modo: 'literal' })
  assert.deepEqual(browserErrors, [])
  const result = { checks, keyboard: 'Resumen -> Categoría: OK', browserErrors,
    flow: 'fallo IA -> extracción literal -> edición como contexto', externalServices: 0, screenshots: output }
  await writeFile(resolve(output, 'resultado.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result, null, 2))
} finally { await browser.close() }
