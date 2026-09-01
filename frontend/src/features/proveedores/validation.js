import { PROVINCIAS_ARGENTINAS } from '../propiedades/provincias.js'

const PROVINCES = new Set(PROVINCIAS_ARGENTINAS)
const LETTER_PATTERN = /\p{L}/u
const PHONE_PATTERN = /^\+?[0-9\s().-]+$/
const asText = (value) => String(value ?? '')
const normalizeText = (value) => asText(value).trim().replace(/\s+/g, ' ')

export function splitNames(value) {
  const seen = new Set()
  return asText(value)
    .split(',')
    .map(normalizeText)
    .filter((item) => {
      const key = item.toLocaleLowerCase('es')
      if (!item || seen.has(key)) return false
      seen.add(key)
      return true
    })
}

export function normalizeWhatsapp(value) {
  const text = asText(value).trim()
  const digits = text.replace(/\D/g, '')
  return text.startsWith('+') ? `+${digits}` : text
}

function validateLocationName(value, label) {
  const normalized = normalizeText(value)
  if (normalized.length < 2) return `Ingresá ${label}.`
  if (normalized.length > 100) return `${label} no puede superar los 100 caracteres.`
  if (!LETTER_PATTERN.test(normalized)) return `${label} debe contener al menos una letra.`
  return undefined
}

export function validateProveedor(values) {
  const errors = {}
  const name = normalizeText(values.nombre_razon_social)
  const registration = normalizeText(values.matricula)
  const phone = asText(values.telefono).trim()
  const digits = phone.replace(/\D/g, '')
  const customSpecialties = splitNames(values.especialidades_personalizadas)

  if (name.length < 2) {
    errors.nombre_razon_social = 'Ingresá el nombre o la razón social.'
  } else if (name.length > 150) {
    errors.nombre_razon_social = 'El nombre no puede superar los 150 caracteres.'
  } else if (!LETTER_PATTERN.test(name)) {
    errors.nombre_razon_social = 'El nombre debe contener al menos una letra.'
  }

  if (registration.length > 80) {
    errors.matricula = 'La matrícula no puede superar los 80 caracteres.'
  }

  if (!phone.startsWith('+')) {
    errors.telefono = 'Incluí el código de país, por ejemplo +54.'
  } else if (!PHONE_PATTERN.test(phone) || digits.length < 8 || digits.length > 15) {
    errors.telefono = 'Ingresá un teléfono internacional válido de 8 a 15 números.'
  }

  if (!values.especialidad_ids.length && !customSpecialties.length) {
    errors.especialidades = 'Seleccioná o agregá al menos una especialidad.'
  }
  if (customSpecialties.some((item) => item.length < 2 || item.length > 80 || !LETTER_PATTERN.test(item))) {
    errors.especialidades_personalizadas = 'Cada especialidad debe tener entre 2 y 80 caracteres e incluir letras.'
  }

  if (Boolean(values.hora_inicio) !== Boolean(values.hora_fin)) {
    errors.horario = 'Completá juntas la hora de inicio y la hora de fin.'
  } else if (values.hora_inicio && values.hora_fin && values.hora_fin <= values.hora_inicio) {
    errors.horario = 'La hora de fin debe ser posterior a la de inicio.'
  }

  if (!values.coberturas.length) {
    errors.coberturas = 'Agregá al menos una zona de cobertura.'
  }
  const locations = new Set()
  values.coberturas.forEach((coverage, index) => {
    if (!PROVINCES.has(coverage.provincia)) {
      errors[`cobertura-${index}-provincia`] = 'Seleccioná una provincia.'
    }
    const localityError = validateLocationName(coverage.localidad, 'la localidad')
    if (localityError) errors[`cobertura-${index}-localidad`] = localityError
    const key = `${coverage.provincia.toLocaleLowerCase('es')}|${normalizeText(coverage.localidad).toLocaleLowerCase('es')}`
    if (coverage.provincia && coverage.localidad && locations.has(key)) {
      errors[`cobertura-${index}-localidad`] = 'Esta provincia y localidad ya están cargadas.'
    }
    locations.add(key)
    const neighborhoods = splitNames(coverage.barrios)
    if (!coverage.cubre_toda_localidad && !neighborhoods.length) {
      errors[`cobertura-${index}-barrios`] = 'Ingresá al menos un barrio o marcá toda la localidad.'
    } else if (neighborhoods.some((item) => item.length < 2 || item.length > 100 || !LETTER_PATTERN.test(item))) {
      errors[`cobertura-${index}-barrios`] = 'Cada barrio debe tener entre 2 y 100 caracteres e incluir letras.'
    }
  })
  return errors
}

export function normalizeProveedor(values) {
  return {
    nombre_razon_social: normalizeText(values.nombre_razon_social),
    matricula: normalizeText(values.matricula).toUpperCase() || null,
    telefono: normalizeWhatsapp(values.telefono),
    activo: Boolean(values.activo),
    hora_inicio: values.hora_inicio || null,
    hora_fin: values.hora_fin || null,
    especialidad_ids: [...new Set(values.especialidad_ids)],
    especialidades_personalizadas: splitNames(
      values.especialidades_personalizadas,
    ).map((item) => item.toLocaleLowerCase('es')),
    coberturas: values.coberturas.map((coverage) => ({
      provincia: coverage.provincia,
      localidad: normalizeText(coverage.localidad),
      cubre_toda_localidad: coverage.cubre_toda_localidad,
      barrios: coverage.cubre_toda_localidad ? [] : splitNames(coverage.barrios),
    })),
  }
}
