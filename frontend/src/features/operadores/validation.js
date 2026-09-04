export function normalizeOperador(values) {
  return {
    nombre_completo: values.nombre_completo.trim().replace(/\s+/g, ' '),
    email: values.email.trim().toLowerCase(),
  }
}

export function validateOperador(values) {
  const normalized = normalizeOperador(values)
  const errors = {}
  if (normalized.nombre_completo.length < 2 || normalized.nombre_completo.length > 120) {
    errors.nombre_completo = 'Ingresá un nombre completo de entre 2 y 120 caracteres.'
  } else if (!/^\p{L}+(?:[ '\u2019-]\p{L}+)*$/u.test(normalized.nombre_completo)) {
    errors.nombre_completo = 'Usá solo letras, espacios, apóstrofes o guiones.'
  }
  if (normalized.email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized.email)) {
    errors.email = 'Ingresá un email válido, por ejemplo nombre@dominio.com.'
  }
  return errors
}
