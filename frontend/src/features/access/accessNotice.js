export function accessNotice(access, { entityLabel, isEditing }) {
  const action = isEditing ? 'se actualizó' : 'se registró'
  if (access?.estado === 'fallido') {
    return `El ${entityLabel} ${action}, pero el correo no pudo enviarse. Reintentá el envío desde el detalle.`
  }
  if (access?.estado === 'pendiente') {
    return `El ${entityLabel} ${action}. Las credenciales quedaron pendientes de envío.`
  }
  if (access?.estado === 'enviado') {
    return `El ${entityLabel} ${action} y las credenciales se enviaron correctamente.`
  }
  return `El ${entityLabel} ${action} correctamente.`
}
