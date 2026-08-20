# Lenguaje visual de AARI

## Intención

AARI debe sentirse confiable, cálido y simple para usuarios no técnicos. La interfaz prioriza jerarquía clara, aire, lenguaje directo y acciones fáciles de reconocer. La referencia visual aprobada está en `../assets/aari-dashboard-reference.png`.

Los valores ejecutables y vigentes viven en `frontend/src/styles/tokens.css`. Este documento explica cómo usarlos; no debe duplicar números que puedan quedar desactualizados.

## Identidad

- Usar Inter Variable como tipografía principal en toda la aplicación.
- Reservar el azul petróleo para títulos, navegación y contenido de alta jerarquía.
- Usar el verde como acción primaria y confirmación positiva.
- Usar coral para urgencias, errores y acciones destructivas.
- Usar amarillo únicamente para advertencias y estados que requieren atención.
- Mantener fondo general marfil muy claro y superficies blancas.
- Trabajar en modo claro. Un modo oscuro requerirá una decisión y una especificación propias.

## Composición

- Mantener una única cabecera superior con marca, navegación, búsqueda y perfil.
- Usar `PageContainer` para limitar el ancho de lectura y conservar márgenes fluidos.
- Introducir cada pantalla con `PageHeading`: título, explicación breve y, si corresponde, una acción principal.
- Construir la jerarquía con espacio, tipografía y divisores suaves antes de agregar contenedores.
- Usar tarjetas solo cuando agrupen contenido que realmente funcione como una unidad. Evitar una tarjeta para cada texto o control.
- Alinear las acciones principales a la intención de lectura y dejar las acciones secundarias visualmente más tranquilas.

## Geometría y profundidad

- Preferir bordes redondeados medios y consistentes; evitar tanto los rectángulos rígidos como las cápsulas indiscriminadas.
- Usar bordes claros para separar superficies.
- Reservar sombras para elementos elevados o interactivos. No apilar sombras decorativas.
- Respetar la escala de espaciado de 8 px definida por los tokens.

## Componentes y estados

- Reutilizar `Button`, `IconButton`, `SearchInput`, `StatusBadge`, `FormField`, `EmptyState` y `LoadingState` antes de crear alternativas.
- Una acción primaria por región visual. Las demás deben usar variantes secundaria o fantasma.
- Los badges comunican estado, no funcionan como botones.
- Los formularios siempre muestran etiqueta; el placeholder no reemplaza a la etiqueta.
- Mostrar errores junto al campo que los origina y explicar cómo resolverlos.
- Cargas, vacíos y errores deben conservar el contexto de la pantalla; no dejar áreas en blanco sin explicación.

## Responsive

- Escritorio: conservar navegación completa y contenido con ancho máximo.
- Tablet: permitir que cabecera y acciones se reorganicen sin superponerse.
- Móvil: apilar encabezados y acciones, mantener al menos 44 px en controles táctiles y evitar scroll horizontal de contenido.
- Las tablas extensas deben transformarse o permitir desplazamiento dentro de su propia región; nunca ensanchar toda la página.

## Accesibilidad

- Mantener foco visible con teclado.
- Asociar etiquetas y mensajes de error mediante atributos accesibles.
- No depender exclusivamente del color: sumar texto, icono o forma para comunicar estado.
- Usar botones para acciones y enlaces para navegación.
- Respetar `prefers-reduced-motion` y evitar animaciones no esenciales.
- Los iconos sin texto necesitan un nombre accesible; los decorativos deben ocultarse a lectores de pantalla.

## Evitar

- Tipografías serif o mezclas tipográficas sin aprobación.
- Colores hexadecimales directos fuera de `tokens.css`.
- Navegación lateral duplicada con la cabecera.
- Gradientes decorativos, glassmorphism o efectos que compitan con el contenido.
- Emojis usados como iconos de interfaz.
- Bloques excesivamente rectangulares, densos o con apariencia de plantilla genérica.
- Cambiar la identidad para una pantalla aislada sin actualizar primero el sistema compartido.
