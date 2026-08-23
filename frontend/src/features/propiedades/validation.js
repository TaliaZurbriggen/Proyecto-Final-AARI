import { PROVINCIAS_ARGENTINAS } from './provincias.js'

const PROPERTY_TYPES = new Set(['departamento', 'casa', 'local', 'otro'])
const PROVINCES = new Set(PROVINCIAS_ARGENTINAS)
const LETTER_PATTERN = /\p{L}/u
const asText = (value) => String(value ?? '')
const normalizeText = (value) => asText(value).trim().replace(/\s+/g, ' ')

export function validatePropiedad(values) {
  const errors = {}
  const direccion = asText(values.direccion).trim()
  const localidad = asText(values.localidad).trim()
  const barrio = asText(values.barrio).trim()
  const piso = asText(values.piso).trim()
  const numero = asText(values.numero).trim()

  if (direccion.length < 2) {
    errors.direccion = 'Ingresá la dirección de la propiedad.'
  } else if (direccion.length > 200) {
    errors.direccion = 'La dirección no puede superar los 200 caracteres.'
  } else if (!LETTER_PATTERN.test(direccion)) {
    errors.direccion = 'La dirección debe incluir el nombre de la calle o ruta.'
  }

  if (!PROVINCES.has(values.provincia)) {
    errors.provincia = 'Seleccioná la provincia donde se encuentra la propiedad.'
  }

  if (localidad.length < 2) {
    errors.localidad = 'Ingresá la localidad donde se encuentra la propiedad.'
  } else if (localidad.length > 100) {
    errors.localidad = 'La localidad no puede superar los 100 caracteres.'
  } else if (!LETTER_PATTERN.test(localidad)) {
    errors.localidad = 'La localidad debe contener al menos una letra.'
  }

  if (barrio.length === 1) {
    errors.barrio = 'El barrio debe tener al menos 2 caracteres.'
  } else if (barrio.length > 100) {
    errors.barrio = 'El barrio no puede superar los 100 caracteres.'
  } else if (barrio && !LETTER_PATTERN.test(barrio)) {
    errors.barrio = 'El barrio debe contener al menos una letra.'
  }

  if (!PROPERTY_TYPES.has(values.tipo)) {
    errors.tipo = 'Seleccioná el tipo de propiedad.'
  }

  if (!values.propietario_id) {
    errors.propietario_id = 'Seleccioná el propietario del inmueble.'
  }

  if (values.tipo === 'departamento') {
    if (piso && !/^-?\d+$/.test(piso)) {
      errors.piso = 'Ingresá un número entero. Usá 0 para planta baja.'
    }
    if (numero.length > 30) {
      errors.numero = 'El número no puede superar los 30 caracteres.'
    }
  }

  return errors
}

export function normalizePropiedad(values) {
  const isApartment = values.tipo === 'departamento'
  const piso = asText(values.piso).trim()
  return {
    direccion: normalizeText(values.direccion),
    provincia: values.provincia,
    localidad: normalizeText(values.localidad),
    barrio: normalizeText(values.barrio) || null,
    tipo: values.tipo,
    piso: isApartment && piso ? Number(piso) : null,
    numero: isApartment ? normalizeText(values.numero) || null : null,
    propietario_id: values.propietario_id,
  }
}
