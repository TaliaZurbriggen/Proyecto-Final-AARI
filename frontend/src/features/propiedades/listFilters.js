import { PROVINCIAS_ARGENTINAS } from './provincias.js'

export const LOCATION_FILTER_FIELDS = [
  { name: 'provincia', label: 'Provincia', allLabel: 'Todas', options: PROVINCIAS_ARGENTINAS.map((value) => ({ value, label: value })) },
  { name: 'localidad', label: 'Localidad', placeholder: 'Nombre completo de la localidad' },
]

export const PROPERTY_FILTER_FIELDS = [
  { name: 'tipo', label: 'Tipo de inmueble', options: [
    { value: 'departamento', label: 'Departamento' }, { value: 'casa', label: 'Casa' },
    { value: 'local', label: 'Local' }, { value: 'otro', label: 'Otro' },
  ] },
  ...LOCATION_FILTER_FIELDS,
  { name: 'barrio', label: 'Barrio', placeholder: 'Nombre completo del barrio' },
  { name: 'propietario', label: 'Propietario', placeholder: 'Nombre, DNI o email', maxLength: 120 },
  { name: 'tiene_inquilino_activo', label: 'Ocupación', allLabel: 'Todas', options: [
    { value: 'true', label: 'Con inquilino activo' }, { value: 'false', label: 'Sin inquilino activo' },
  ] },
]
