"""Elección vigente sin depender del esquema nuevo al desplegar el código."""

# Alias ep. Conserva compatibilidad con bases anteriores a HU24 y evita que
# decisiones históricas vuelvan a habilitar acciones al comenzar otro intento.
CURRENT_CHOICE = """NOT EXISTS (
    SELECT 1 FROM public.reclamo_elecciones_proveedor posterior
    WHERE posterior.reclamo_id=ep.reclamo_id
      AND posterior.solicitud_responsable_en=ep.solicitud_responsable_en
      AND (posterior.solicitado_en,posterior.id)>(ep.solicitado_en,ep.id))"""
