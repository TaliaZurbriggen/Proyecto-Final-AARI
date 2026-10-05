export const MANUAL_OPTIONS = {
  ordinario: { label: 'Ordinario', actor: 'inquilino' },
  extraordinario: { label: 'Extraordinario', actor: 'propietario' },
  expensa: { label: 'Expensa', actor: 'equipo de la inmobiliaria' },
}

export function escalationReason(value) {
  return {
    respuesta_modelo_invalida: 'El agente no pudo obtener una respuesta válida del modelo.',
    riesgo_seguridad: 'El caso presenta un posible riesgo de seguridad.',
    multiples_rubros: 'El reclamo involucra más de un rubro.',
    causa_no_identificable: 'No se pudo identificar la causa del problema.',
    confianza_insuficiente: 'El agente no tuvo suficiente confianza para clasificarlo.',
  }[value] ?? 'La clasificación requiere revisión de la inmobiliaria.'
}

export function validateManualDecision(expense, reason) {
  const errors = {}
  if (!Object.hasOwn(MANUAL_OPTIONS, expense)) errors.tipo_gasto = 'Seleccioná una clasificación.'
  if (reason.trim().length < 10 || reason.trim().length > 1000) {
    errors.fundamento = 'Explicá la decisión usando entre 10 y 1000 caracteres.'
  }
  return errors
}
