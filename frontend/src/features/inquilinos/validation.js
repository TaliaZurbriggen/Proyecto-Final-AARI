const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/
const DNI_PATTERN = /^[0-9]{7,8}$/
const PERSON_NAME_PATTERN = /^\p{L}+(?:[ '\u2019-]\p{L}+)*$/u
const PERSON_NAME_ERROR =
  'Ingresá un nombre válido usando solo letras, espacios, apóstrofes o guiones.'
const asText = (value) => String(value ?? '')
const normalizeText = (value) => asText(value).trim().replace(/\s+/g, ' ')

export function validateInquilino(values, { propertyRequired = true } = {}) {
  const errors = {}
  const nombre = normalizeText(values.nombre_completo)
  const dni = asText(values.dni).trim()
  const email = asText(values.email).trim()
  const telefono = asText(values.telefono).trim()

  if (nombre.length < 2) {
    errors.nombre_completo = 'Ingresá el nombre completo del inquilino.'
  } else if (nombre.length > 120) {
    errors.nombre_completo = 'El nombre no puede superar los 120 caracteres.'
  } else if (!PERSON_NAME_PATTERN.test(nombre)) {
    errors.nombre_completo = PERSON_NAME_ERROR
  }

  if (!DNI_PATTERN.test(dni)) {
    errors.dni = 'Ingresá un DNI de 7 u 8 números, sin puntos ni espacios.'
  }

  if (!EMAIL_PATTERN.test(email)) {
    errors.email = 'Ingresá un email válido, por ejemplo nombre@dominio.com.'
  }

  if (telefono.length < 6) {
    errors.telefono = 'Ingresá un teléfono de contacto válido.'
  } else if (telefono.length > 30) {
    errors.telefono = 'El teléfono no puede superar los 30 caracteres.'
  }

  if (propertyRequired && !values.propiedad_id) {
    errors.propiedad_id = 'Seleccioná una propiedad disponible.'
  }

  return errors
}

export function normalizeInquilino(values) {
  return {
    nombre_completo: normalizeText(values.nombre_completo),
    dni: asText(values.dni).trim(),
    email: asText(values.email).trim().toLowerCase(),
    telefono: normalizeText(values.telefono),
    propiedad_id: values.propiedad_id || null,
  }
}
