import { apiRequest } from '../../../services/apiClient.js'

const isCount = (value) => Number.isInteger(value) && value >= 0

export async function getAdminSummary({ signal } = {}) {
  const summary = await apiRequest('/admin/resumen', { signal })
  const baseCounts = ['propietarios', 'propiedades', 'inquilinos', 'proveedores', 'operadores']
  if (!summary || !baseCounts.every((key) => isCount(summary[key]?.total))
      || !['proveedores', 'operadores'].every((key) => isCount(summary[key].activos) && summary[key].activos <= summary[key].total)
      || !isCount(summary.reclamos?.activos) || !isCount(summary.reclamos?.pendientes_clasificacion)
      || summary.reclamos.pendientes_clasificacion > summary.reclamos.activos
      || typeof summary.consultado_en !== 'string' || Number.isNaN(Date.parse(summary.consultado_en))) {
    throw new Error('El resumen recibido está incompleto. Podés volver a intentar.')
  }
  return summary
}
