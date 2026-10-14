export const candidateOutcome = {
  candidatos_encontrados: 'Candidatos encontrados',
  sin_candidatos: 'No hay proveedores compatibles',
  especialidad_pendiente: 'Falta indicar la especialidad',
  ubicacion_incompleta: 'Falta completar provincia o localidad',
}

export const operatorAlert = {
  no_aplica: 'No requiere aviso al operador.',
  encolado: 'Aviso al operador encolado; no significa que ya se haya entregado.',
  sin_destinatario: 'No se pudo encolar el aviso: no hay personal activo con acceso habilitado.',
}

export function positivePage(value) {
  const page = Number(value || 1)
  return Number.isSafeInteger(page) && page > 0 && page <= 1000000 ? page : 1
}

export function assignmentReturnQuery(params) {
  return new URLSearchParams({
    page: String(positivePage(params.get('page'))),
    search: (params.get('search') || '').slice(0, 200),
  }).toString()
}
