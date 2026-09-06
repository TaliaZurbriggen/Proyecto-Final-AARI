export const MAX_CLAIM_PHOTOS = 3
export const MAX_CLAIM_PHOTO_BYTES = 5 * 1024 * 1024
export const CLAIM_PHOTO_TYPES = ['image/jpeg', 'image/png']

export function validateClaim({ descripcion, fotos, urgencia }) {
  const errors = {}
  const cleanDescription = descripcion.trim()
  if (cleanDescription.length < 20 || cleanDescription.length > 1000) {
    errors.descripcion = 'Describí el problema usando entre 20 y 1000 caracteres.'
  }
  if (!['baja', 'media', 'alta'].includes(urgencia)) {
    errors.urgencia = 'Seleccioná el nivel de urgencia.'
  }
  if (fotos.length > MAX_CLAIM_PHOTOS) {
    errors.fotos = 'Podés adjuntar hasta 3 fotos.'
  } else if (fotos.some((photo) => !CLAIM_PHOTO_TYPES.includes(photo.type))) {
    errors.fotos = 'Las fotos deben ser JPG, JPEG o PNG.'
  } else if (fotos.some((photo) => photo.size > MAX_CLAIM_PHOTO_BYTES)) {
    errors.fotos = 'Cada foto debe pesar como máximo 5 MB.'
  }
  return errors
}

export function normalizeClaim(values) {
  return { ...values, descripcion: values.descripcion.trim() }
}

export function claimPropertyLabel(property) {
  const details = [property.direccion]
  if (property.tipo === 'departamento') {
    if (property.piso != null) {
      details.push(property.piso === 0 ? 'PB' : `Piso ${property.piso}`)
    }
    if (property.numero) details.push(`Unidad ${property.numero}`)
  }
  details.push(property.localidad, property.provincia)
  return details.filter(Boolean).join(' · ')
}
