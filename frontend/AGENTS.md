# Guía del frontend de AARI

Estas instrucciones complementan el `AGENTS.md` de la raíz y aplican a todo `frontend/`.

## Antes de diseñar o implementar

1. Usar la skill del repositorio `.agents/skills/aari-frontend/SKILL.md`.
2. Leer su referencia `references/visual-language.md`.
3. Revisar `src/styles/tokens.css` y los componentes compartidos existentes.
4. Incluir en la propuesta qué piezas se reutilizan y qué comportamiento tendrá la pantalla en móvil.

## Reglas de implementación

- Usar React y CSS Modules para los componentes.
- Consumir colores, espacios, radios, sombras y tipografía desde `src/styles/tokens.css`.
- No escribir colores hexadecimales en componentes o páginas.
- Reutilizar `src/components/ui` y `src/components/layout` antes de crear otro componente equivalente.
- Mantener una única navegación principal superior.
- Usar `lucide-react` para iconografía funcional.
- Incluir estados de foco, deshabilitado, carga, vacío y error cuando correspondan.
- Mantener etiquetas visibles en formularios y nombres accesibles en botones de solo icono.
- No incorporar modo oscuro hasta que exista una decisión de producto aprobada.

## Validación mínima

Desde `frontend/` ejecutar:

```bash
npm run lint
npm run build
```

Cuando haya un navegador disponible, revisar al menos un ancho de escritorio y uno móvil, además de la navegación con teclado.
