const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/
const DNI_PATTERN = /^[0-9]{7,8}$/

export function validatePropietario(values) {
  const errors = {}
  const nombre = values.nombre_completo.trim()
  const dni = values.dni.trim()
  const email = values.email.trim()
  const telefono = values.telefono.trim()

  if (nombre.length < 2) {
    errors.nombre_completo = 'Ingresá el nombre completo del propietario.'
  } else if (nombre.length > 120) {
    errors.nombre_completo = 'El nombre no puede superar los 120 caracteres.'
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

  return errors
}

export function normalizePropietario(values) {
  return {
    nombre_completo: values.nombre_completo.trim(),
    dni: values.dni.trim(),
    email: values.email.trim().toLowerCase(),
    telefono: values.telefono.trim(),
  }
}
