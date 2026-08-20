---
name: aari-frontend
description: Diseña, implementa y revisa interfaces del frontend React de AARI respetando su sistema visual, componentes compartidos, accesibilidad y comportamiento responsive. Usar al crear o modificar pantallas, layouts, componentes, estilos CSS, formularios, estados de carga o vacío, navegación y revisiones visuales dentro de frontend/.
---

# AARI Frontend

Aplicar una experiencia coherente, limpia y humana en todas las pantallas de AARI. Reutilizar la base existente antes de crear variantes nuevas y mantener las decisiones visuales centralizadas.

## Preparar el trabajo

1. Leer `AGENTS.md` y `frontend/AGENTS.md` antes de proponer cambios.
2. Leer [references/visual-language.md](references/visual-language.md).
3. Revisar `frontend/src/styles/tokens.css`, los componentes existentes y la pantalla afectada.
4. Presentar la propuesta exigida por el repositorio y esperar aprobación antes de editar.

## Implementar

1. Componer la pantalla con los elementos de `frontend/src/components/ui` y `frontend/src/components/layout`.
2. Usar variables de `tokens.css`; no introducir colores, sombras, radios o espaciados arbitrarios en componentes.
3. Encapsular estilos de componentes con CSS Modules y reservar `globals.css` para reglas globales reales.
4. Mantener una única navegación principal superior. Evitar barras laterales o duplicaciones de navegación salvo una decisión de producto aprobada.
5. Incluir los estados pertinentes: normal, hover, focus, disabled, loading, vacío y error.
6. Diseñar primero para escritorio sin perder el comportamiento entre 768 px y pantallas móviles.
7. Usar iconos de `lucide-react`; no usar emojis como iconografía funcional.

## Validar

1. Ejecutar `npm run lint` y `npm run build` desde `frontend/`.
2. Revisar visualmente la pantalla en escritorio y móvil cuando haya navegador disponible.
3. Verificar navegación por teclado, foco visible, etiquetas accesibles, contraste y áreas táctiles.
4. Revisar el diff y comprobar que los nuevos estilos consuman los tokens compartidos.

## Gestionar excepciones

Detener la implementación si una necesidad exige apartarse de la paleta, la navegación, la tipografía o los patrones definidos. Explicar la necesidad y las alternativas, y esperar la decisión de la persona responsable del proyecto.

## Recursos

- Consultar [references/visual-language.md](references/visual-language.md) para criterios visuales, responsive y de accesibilidad.
- Usar [assets/aari-dashboard-reference.png](assets/aari-dashboard-reference.png) como referencia de dirección, no como una maqueta que deba copiarse literalmente.
