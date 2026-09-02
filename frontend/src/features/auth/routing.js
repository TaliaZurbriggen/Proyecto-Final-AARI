const roleHomePaths = {
  administrador: '/propietarios',
  inquilino: '/inquilino',
  operador: '/operador',
  propietario: '/propietario',
}

export function homePathForRole(role) {
  return roleHomePaths[role] ?? '/login'
}

export function destinationForUser(user) {
  if (!user) return '/login'
  return user.primer_ingreso ? '/cambiar-contrasena' : homePathForRole(user.rol)
}
