import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProviderQuoteDetailPage from './ProviderQuoteDetailPage.jsx'
import ProviderQuoteRequests from '../components/ProviderQuoteRequests.jsx'
import ClaimQuoteSummary from '../components/ClaimQuoteSummary.jsx'
import { positiveAmount, quoteAmount } from '../quotePresentation.js'

const id='00000000-0000-0000-0000-000000000019'
const item={id,numero:19,reclamo_id:'claim',descripcion:'Pierde agua la cañería de la cocina.',
  ubicacion:'Unidad sintética, Localidad de prueba',estado:'pendiente',puede_responder:true,
  publicada_en:'2026-10-27T10:00:00Z',vence_en:'2026-10-28T10:00:00Z',presupuesto:null}
const saved={id:'quote',monto:'10000.50',moneda:'ARS',tipo_importe:'minimo',descripcion:'Reparación de cañería con materiales',recibido_en:'2026-10-27T11:00:00Z'}
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}})
function show(path=`/proveedor/solicitudes/${id}?page=2`) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/proveedor" element={<ProviderQuoteRequests />} />
    <Route path="/proveedor/solicitudes/:requestId" element={<ProviderQuoteDetailPage />} />
  </Routes></MemoryRouter>)
}
async function fill(kind='minimo') {
  const user=userEvent.setup()
  await user.selectOptions(await screen.findByLabelText(/Tipo de importe/),kind)
  await user.selectOptions(screen.getByLabelText(/Moneda/),'ARS')
  await user.type(screen.getByLabelText(kind==='minimo' ? /Importe mínimo/ : /^Importe/),'10000,50')
  await user.type(screen.getByLabelText(/Descripción y alcance/),saved.descripcion)
  await user.click(screen.getByRole('button',{name:'Revisar presupuesto'}))
  return user
}
afterEach(()=>vi.restoreAllMocks())

describe('importes explícitos',()=>{
  it.each(['0','-10','1e4','$10000','10.000','10000.123','10000000000','NaN'])('rechaza %s sin reinterpretarlo',(value)=>{
    expect(positiveAmount(value)).toBeNull()
  })
  it('conserva el decimal enviado como texto y distingue el mínimo',()=>{
    expect(positiveAmount('10000,50')).toBe('10000.50')
    expect(quoteAmount(saved)).toMatch(/^Desde /)
    expect(quoteAmount({...saved,tipo_importe:'exacto'})).not.toMatch(/Desde/)
  })
})

describe('formulario del proveedor',()=>{
  it.each(['exacto','minimo'])('revisa y confirma importe %s sin contratar',async(kind)=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockImplementation((_url,opts)=>Promise.resolve(json(opts?.method==='POST' ? {...item,estado:'respondida',puede_responder:false,presupuesto:{...saved,tipo_importe:kind}} : item)))
    show()
    const user=await fill(kind)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Revisá antes de confirmar')).toBeVisible()
    await user.click(screen.getByRole('button',{name:'Confirmar presupuesto'}))
    expect(await screen.findByRole('heading',{name:'Tu presupuesto enviado'})).toBeVisible()
    const body=JSON.parse(fetch.mock.calls[1][1].body)
    expect(body).toEqual({request_id:expect.any(String),monto:'10000.50',moneda:'ARS',tipo_importe:kind,descripcion:saved.descripcion})
    expect(screen.queryByRole('button',{name:'Confirmar presupuesto'})).not.toBeInTheDocument()
    expect(screen.getByRole('link',{name:'Volver a mis solicitudes'})).toHaveAttribute('href','/proveedor?page=2&estado=pendientes')
    if(kind==='minimo') expect(screen.getByText(/No es un máximo autorizado/)).toBeVisible()
  })

  it('señala campos inválidos sin enviar',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValue(json(item))
    show()
    await userEvent.click(await screen.findByRole('button',{name:'Revisar presupuesto'}))
    expect(screen.getAllByRole('alert')).toHaveLength(4)
    expect(screen.getByLabelText(/Tipo de importe/)).toHaveAttribute('aria-invalid','true')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('permite corregir antes de enviar y bloquea doble confirmación',async()=>{
    let complete
    const fetch=vi.spyOn(globalThis,'fetch').mockImplementation((_url,opts)=>opts?.method==='POST' ? new Promise((resolve)=>{complete=resolve}) : Promise.resolve(json(item)))
    show()
    const user=await fill()
    await user.click(screen.getByRole('button',{name:'Corregir'}))
    expect(screen.queryByRole('button',{name:'Confirmar presupuesto'})).not.toBeInTheDocument()
    await user.click(screen.getByRole('button',{name:'Revisar presupuesto'}))
    await user.dblClick(screen.getByRole('button',{name:'Confirmar presupuesto'}))
    expect(fetch).toHaveBeenCalledTimes(2)
    await act(async()=>complete(json({...item,estado:'respondida',puede_responder:false,presupuesto:saved})))
    expect(await screen.findByRole('heading',{name:'Tu presupuesto enviado'})).toBeVisible()
  })

  it('reutiliza el identificador cuando se pierde la respuesta',async()=>{
    let posts=0
    const fetch=vi.spyOn(globalThis,'fetch').mockImplementation((_url,opts)=>{
      if(opts?.method!=='POST') return Promise.resolve(json(item))
      posts++
      return posts===1 ? Promise.reject(new TypeError('network')) : Promise.resolve(json({...item,estado:'respondida',puede_responder:false,presupuesto:saved}))
    })
    show()
    const user=await fill()
    await user.click(screen.getByRole('button',{name:'Confirmar presupuesto'}))
    expect(await screen.findByText(/No pudimos conectarnos/)).toBeVisible()
    await user.click(screen.getByRole('button',{name:'Revisar presupuesto'}))
    await user.click(screen.getByRole('button',{name:'Confirmar presupuesto'}))
    await screen.findByRole('heading',{name:'Tu presupuesto enviado'})
    const bodies=fetch.mock.calls.filter(([,opts])=>opts?.method==='POST').map(([,opts])=>JSON.parse(opts.body))
    expect(bodies[0]).toEqual(bodies[1])
  })

  it.each(['vencida','cancelada'])('no ofrece responder si está %s',async(estado)=>{
    vi.spyOn(globalThis,'fetch').mockResolvedValue(json({...item,estado,puede_responder:false}))
    show()
    expect(await screen.findByText(/ya no está habilitada para responder/)).toBeVisible()
    expect(screen.queryByRole('button',{name:'Revisar presupuesto'})).not.toBeInTheDocument()
  })

  it('un detalle ajeno tiene error y retorno seguro',async()=>{
    vi.spyOn(globalThis,'fetch').mockResolvedValue(json({detail:{message:'No encontramos esa solicitud.'}},404))
    show(`/proveedor/solicitudes/${id}?page=https://evil.example`)
    expect(await screen.findByRole('alert')).toHaveTextContent('No encontramos esa solicitud.')
    expect(screen.getByRole('link',{name:'Volver a mis solicitudes'})).toHaveAttribute('href','/proveedor?page=1&estado=pendientes')
  })
})

describe('listado y responsable',()=>{
  it('agrupa título, filtros y actualización en una misma cabecera',async()=>{
    vi.spyOn(globalThis,'fetch').mockResolvedValue(json({items:[],total:0}))
    show('/proveedor')
    await screen.findByText('No tenés solicitudes pendientes')
    const toolbar=screen.getByRole('heading',{name:'Solicitudes de presupuesto'}).parentElement
    expect(within(toolbar).getByRole('group',{name:'Filtrar solicitudes'})).toBeVisible()
    expect(within(toolbar).getByRole('button',{name:'Actualizar'})).toBeVisible()
    expect(within(toolbar).getAllByRole('button')).toHaveLength(4)
  })

  it('pagina conservando el retorno y no muestra resultados viejos si falla',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValueOnce(json({items:[item],total:21})).mockResolvedValueOnce(json({detail:{message:'Error de consulta.'}},500))
    show('/proveedor?page=2')
    expect(await screen.findByRole('link',{name:'Ver solicitud'})).toHaveAttribute('href',`/proveedor/solicitudes/${id}?page=2&estado=pendientes`)
    await userEvent.click(screen.getByRole('button',{name:'Ver siguientes'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Error de consulta.')
    expect(screen.queryByText(item.descripcion)).not.toBeInTheDocument()
    expect(fetch.mock.calls[1][0]).toContain('page=3')
    expect(fetch.mock.calls[1][0]).toContain('estado=pendientes')
  })
  it('una página fuera de rango permite volver al inicio',async()=>{
    vi.spyOn(globalThis,'fetch').mockResolvedValue(json({items:[],total:2}))
    show('/proveedor?page=3')
    expect(await screen.findByRole('button',{name:'Volver a la primera página'})).toBeVisible()
    expect(screen.getByRole('button',{name:'Ver siguientes'})).toBeDisabled()
  })
  it('el responsable ve un mínimo como piso, no precio final',async()=>{
    vi.spyOn(globalThis,'fetch').mockResolvedValue(json({items:[{...item,proveedor:'Servicio Sintético',presupuesto:saved}]}))
    render(<ClaimQuoteSummary claimId="claim" />)
    expect(await screen.findByText(/Desde .*Importe mínimo/)).toBeVisible()
    expect(screen.getByText(/no un precio final ni un máximo autorizado/)).toBeVisible()
    expect(screen.queryByRole('button',{name:/Seleccionar|Contratar/})).not.toBeInTheDocument()
  })
  it('abortar una consulta no reemplaza la siguiente página',async()=>{
    let finish
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValueOnce(json({items:[item],total:21})).mockImplementationOnce(()=>new Promise((resolve)=>{finish=resolve})).mockResolvedValueOnce(json({items:[],total:21}))
    show('/proveedor?page=1')
    await screen.findByText(item.descripcion)
    await userEvent.click(screen.getByRole('button',{name:'Ver siguientes'}))
    // El botón Actualizar genera una consulta nueva y cancela la anterior.
    await userEvent.click(screen.getByRole('button',{name:'Actualizar'}))
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(3))
    await act(async()=>finish(json({items:[item],total:21})))
    expect(screen.queryByText(item.descripcion)).not.toBeInTheDocument()
  })

  it('abre pendientes por defecto y distingue un vacío filtrado',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValue(json({items:[],total:0}))
    show('/proveedor')
    expect(await screen.findByText('No tenés solicitudes pendientes')).toBeVisible()
    expect(screen.getByRole('button',{name:'Pendientes',exact:true})).toHaveAttribute('aria-pressed','true')
    expect(fetch.mock.calls[0][0]).toContain('estado=pendientes')
    expect(screen.queryByRole('navigation',{name:'Paginación de solicitudes'})).not.toBeInTheDocument()
  })

  it.each(['Enviadas','Todas'])('al cambiar a %s vuelve a página uno',async(label)=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockImplementation(()=>Promise.resolve(json({items:[item],total:21})))
    show('/proveedor?page=2&estado=pendientes')
    await screen.findByRole('link',{name:'Ver solicitud'})
    await userEvent.click(screen.getByRole('button',{name:label,exact:true}))
    await screen.findByRole('link',{name:'Ver solicitud'})
    const last=new URL(fetch.mock.calls.at(-1)[0])
    expect(last.searchParams.get('page')).toBe('1')
    expect(last.searchParams.get('estado')).toBe(label.toLowerCase())
    expect(screen.getByRole('button',{name:label,exact:true})).toHaveAttribute('aria-pressed','true')
  })

  it('conserva enviadas y página al volver usando el detalle real',async()=>{
    const sent={...item,estado:'respondida',puede_responder:false,presupuesto:saved}
    const fetch=vi.spyOn(globalThis,'fetch').mockImplementation((url)=>Promise.resolve(json(
      new URL(url).pathname.endsWith('/solicitudes') ? {items:[sent],total:21} : sent)))
    show('/proveedor?page=2&estado=enviadas')
    await userEvent.click(await screen.findByRole('link',{name:'Ver solicitud'}))
    await screen.findByRole('heading',{name:'Tu presupuesto enviado'})
    expect(screen.getByRole('link',{name:'Volver a mis solicitudes'})).toHaveAttribute('href','/proveedor?page=2&estado=enviadas')
    await userEvent.click(screen.getByRole('link',{name:'Volver a mis solicitudes'}))
    await screen.findByRole('link',{name:'Ver solicitud'})
    expect(screen.getByRole('button',{name:'Enviadas',exact:true})).toHaveAttribute('aria-pressed','true')
    const last=new URL(fetch.mock.calls.at(-1)[0])
    expect(last.searchParams.get('estado')).toBe('enviadas')
    expect(last.searchParams.get('page')).toBe('2')
  })

  it('una respuesta tardía del filtro anterior no reemplaza enviadas',async()=>{
    let finish
    const sent={...item,descripcion:'Presupuesto ya confirmado',estado:'respondida',presupuesto:saved}
    vi.spyOn(globalThis,'fetch').mockImplementationOnce(()=>new Promise((resolve)=>{finish=resolve}))
      .mockResolvedValueOnce(json({items:[sent],total:1}))
    show('/proveedor')
    await userEvent.click(screen.getByRole('button',{name:'Enviadas',exact:true}))
    await screen.findByText(sent.descripcion)
    await act(async()=>finish(json({items:[item],total:10})))
    expect(screen.queryByText(item.descripcion)).not.toBeInTheDocument()
    expect(screen.getByText(sent.descripcion)).toBeVisible()
  })

  it('un filtro desconocido vuelve a pendientes sin construir retornos externos',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValue(json({items:[],total:0}))
    show('/proveedor?estado=https://evil.example')
    await screen.findByText('No tenés solicitudes pendientes')
    expect(fetch.mock.calls[0][0]).toContain('estado=pendientes')
    expect(screen.getByRole('button',{name:'Pendientes',exact:true})).toHaveAttribute('aria-pressed','true')
  })

  it('ubica el estado con el reclamo y conserva Ver solicitud como enlace sin flecha',async()=>{
    vi.spyOn(globalThis,'fetch').mockResolvedValue(json({items:[item],total:1}))
    show('/proveedor')
    const link=await screen.findByRole('link',{name:'Ver solicitud'})
    const heading=screen.getByRole('heading',{level:3,name:'Reclamo #000019'})
    expect(within(heading.parentElement).getByText('Pendiente')).toBeVisible()
    expect(link).toHaveAttribute('aria-describedby',heading.id)
    expect(link.querySelector('svg')).toBeNull()
    expect(screen.queryByRole('button',{name:'Ver solicitud'})).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation',{name:'Paginación de solicitudes'})).not.toBeInTheDocument()
    const user=userEvent.setup()
    for(let index=0;index<5;index++) await user.tab()
    expect(link).toHaveFocus()
  })

  it.each([1,2,3])('pagina el filtro enviado en página %s sin contador ni consultas repetidas',async(page)=>{
    const sent={...item,estado:'respondida',puede_responder:false,presupuesto:saved}
    const fetch=vi.spyOn(globalThis,'fetch').mockImplementation(()=>Promise.resolve(json({items:[sent],total:21})))
    show(`/proveedor?page=${page}&estado=enviadas`)
    await screen.findByRole('link',{name:'Ver solicitud'})
    const previous=screen.getByRole('button',{name:'Ver anteriores'})
    const next=screen.getByRole('button',{name:'Ver siguientes'})
    expect(previous.disabled).toBe(page===1)
    expect(next.disabled).toBe(page===3)
    expect(screen.queryByText(/Página \d+ de/)).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
    await userEvent.click(page===3 ? previous : next)
    await screen.findByRole('link',{name:'Ver solicitud'})
    expect(fetch).toHaveBeenCalledTimes(2)
    const requested=new URL(fetch.mock.calls.at(-1)[0])
    expect(requested.searchParams.get('page')).toBe(String(page===3 ? 2 : page+1))
    expect(requested.searchParams.get('page_size')).toBe('10')
    expect(requested.searchParams.get('estado')).toBe('enviadas')
  })

  it('recupera una página que desapareció sin navegar a otro índice inválido',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockImplementation((url)=>Promise.resolve(json({
      items:new URL(url).searchParams.get('page')==='1' ? [item] : [],total:2,
    })))
    show('/proveedor?page=99&estado=todas')
    await screen.findByRole('button',{name:'Volver a la primera página'})
    await userEvent.click(screen.getByRole('button',{name:'Ver anteriores'}))
    await screen.findByRole('link',{name:'Ver solicitud'})
    expect(new URL(fetch.mock.calls.at(-1)[0]).searchParams.get('page')).toBe('1')
    expect(new URL(fetch.mock.calls.at(-1)[0]).searchParams.get('estado')).toBe('todas')
    expect(screen.queryByRole('navigation',{name:'Paginación de solicitudes'})).not.toBeInTheDocument()
  })
})
