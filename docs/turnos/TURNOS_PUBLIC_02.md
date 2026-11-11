# TURNOS PUBLIC 02

Fecha de validación: 2026-10-30.

## Alcance entregado

Integración estática de presencia y navegación de Turnos en las superficies comerciales
existentes. Se conserva la landing de PUBLIC 01, sin modificarla ni habilitar contratación.
No se inicia PUBLIC 03.

| Superficie | Cambio                                                                                                                                                                       |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Home       | Una cuarta entrada en `ProductsSection`, con la misma `ProductCard`, icono `CalendarDays`, descripción, tres bullets y CTA «Conocer Turnos».                                 |
| Navbar     | `/turnos` en el array compartido por desktop y mobile. Espaciado compacto entre `lg` y `xl` para mantener separación respecto del logo. Sin estado ni comportamiento nuevos. |
| Footer     | Enlace «Turnos» en Productos, con destino `/turnos`.                                                                                                                         |
| Sitemap    | `/turnos`, `changeFrequency: monthly`, `priority: 0.7`, igual que las otras landings de producto.                                                                            |
| Servicios  | Una vertical Turnos con agenda, profesionales/clientes, automatizaciones e IA según plan; CTA informativa `/turnos`. Los destinos anteriores se conservan.                   |
| Nosotros   | Una cuarta tarjeta de producto. Icono asociado a cada entrada, eliminando el índice paralelo únicamente de esta lista.                                                       |
| Contacto   | Turnos en el selector y en la lista de temas; icono agregado en la posición correspondiente. Sin cambios en formulario ni envío.                                             |
| Soporte    | Turnos en el selector y en la lista de temas; icono agregado en la posición correspondiente. Sin cambios en formulario ni envío.                                             |
| FAQ        | Corrección de las dos respuestas generales que presentaban la oferta completa. No se agrega una FAQ de producto.                                                             |

Todos los enlaces de producto incorporados apuntan a `/turnos`. No se agrega ningún enlace
a `/pricing?service=appointments`.

### Copy

- Home: «Tres soluciones diseñadas…» pasa a «Soluciones diseñadas…», sin fijar una cantidad.
- Metadata de home y servicios: se incluye Turnos junto a los productos existentes.
- Card: «Organizá tu agenda, profesionales y reservas desde un solo lugar».
- Bullets: agenda/horarios, reservas/clientes y automatizaciones/IA según plan, sin precios,
  límites numéricos, tiers ni entitlements duplicados.
- FAQ: se incluye Turnos y se aclara que su contratación online todavía no está disponible.
- Contacto: «Quiero más información sobre Turnos» y «Obtener más información sobre Turnos».
- Soporte: «Turnos».

`HomeProductShowcase` queda intacto: sus entradas requieren mockups específicos. No se crea
una agenda ilustrativa nueva, una card especializada ni un registro central comercial.

## Responsive y accesibilidad

La grilla de productos usa una columna por debajo de 768 px, dos desde 768 px y cuatro
desde 1280 px. Se reduce el padding de la card existente y el espacio entre cards para
mantener un ancho legible. Nosotros usa los mismos cortes de columnas.

Se validó el runtime Docker con Edge headless y CDP, sin instalar dependencias:

| Viewport CSS | Columnas de productos | Overflow horizontal |
| ------------ | --------------------- | ------------------- |
| 320          | 1                     | No                  |
| 375          | 1                     | No                  |
| 768          | 2                     | No                  |
| 1024         | 2                     | No                  |
| 1280         | 4                     | No                  |
| 1440         | 4                     | No                  |

Las 36 comprobaciones cubren esos seis anchos en `/`, `/turnos`, `/services`, `/nosotros`,
`/contacto` y `/soporte`. Se comprueba `scrollWidth <= clientWidth`, una sola card Turnos,
cuatro cards totales, columnas mediante geometría y separación del navbar desktop.
Se revisaron capturas de la grilla desktop y de la card Turnos a 320 px.

Se conservan enlaces reales, headings y estilos de foco existentes; no hay botones anidados.
No se modifica el focus trap preexistente del menú.

## Tests y validación

Baseline PUBLIC 01: 8 tests aprobados antes de los cambios.

| Validación final                              | Local                                             | Docker          | Exit code |
| --------------------------------------------- | ------------------------------------------------- | --------------- | --------- |
| Tests focalizados, cuatro archivos            | 20/20                                             | 20/20           | 0         |
| Typecheck (`tsc --noEmit`)                    | PASS                                              | PASS            | 0         |
| ESLint de los 16 archivos fuente/test tocados | PASS                                              | PASS            | 0         |
| Prettier de esos archivos                     | PASS                                              | PASS            | 0         |
| Build web                                     | PASS                                              | PASS            | 0         |
| Navegador headless sobre Docker               | 36 checks responsive y cinco recorridos aprobados | Runtime oficial | 0         |

Los cinco recorridos verifican: navegación desktop, apertura/elección/cierre del menú mobile
con restauración del scroll, card de home hacia la landing informativa, selección en Contacto
y selección en Soporte. No se envían formularios ni se inicia checkout.

Los tests nuevos cubren contenido renderizado, unicidad de card, navegación compartida,
footer, sitemap, servicios, iconos de Nosotros incluso al reordenar las entradas, selectores
y generación de mensajes existente, FAQ, producto inactivo y ausencia de fetches/client
components/imports pesados en los archivos estáticos tocados. Se reutilizan además los
ocho tests existentes de la landing PUBLIC 01.

ESLint conserva dos warnings preexistentes: import no usado de `SiteContainer` en
`ContactTopics` y `any` en `FooterLink`. No hay errores de lint. No se corrigen por estar
fuera de alcance.

### Docker

- Docker funcional, Node local disponible.
- Dockerfile oficial `apps/web/Dockerfile`, sin modificaciones.
- Compose oficial + override de desarrollo + overrides temporales de aislamiento.
- Proyecto exclusivo `turnos-public02`; únicamente servicio `web`, con `--no-deps`.
- Runner oficial para HTTP en `127.0.0.1:3102`; stage builder oficial para ejecutar tests,
  typecheck, ESLint, Prettier y build dentro de Docker.
- Sin API, PostgreSQL, Redis, workers ni migraciones.
- HTTP final: 200 en `/`, `/turnos`, `/services`, `/nosotros`, `/contacto`, `/soporte`,
  `/preguntas-frecuentes` y `/sitemap.xml`.
- No se modifican Dockerfile, Compose, manifests, lockfiles ni configuración del proyecto.
- Al terminar se detuvieron y eliminaron el contenedor y la red exclusivos de esta
  validación, y se cerró el navegador headless aislado.

La instalación del Dockerfile existente resuelve los rangos del manifiesto sin lockfile
propio de web: local usó Next 16.1.6 y Docker resolvió Next 16.4.3. Ambos builds aprobaron.
No se actualizan dependencias en este slice.

## Archivos de esta entrega

Modificados:

1. [ProductsSection](../../apps/web/src/components/marketing/sections/products.tsx).
2. [Navbar marketing](../../apps/web/src/components/navigation/marketing-nav.tsx).
3. [Footer marketing](../../apps/web/src/components/navigation/marketing-footer.tsx).
4. [Home](<../../apps/web/src/app/(marketing)/page.tsx>).
5. [Sitemap](../../apps/web/src/app/sitemap.ts).
6. [Servicios](<../../apps/web/src/app/(marketing)/services/page.tsx>).
7. [Datos de Nosotros](<../../apps/web/src/app/(marketing)/nosotros/_data.ts>).
8. [Productos de Nosotros](<../../apps/web/src/app/(marketing)/nosotros/_components/AboutProductsSection.tsx>).
9. [Opciones de Contacto](<../../apps/web/src/app/(marketing)/contacto/_constants.ts>).
10. [Temas de Contacto](<../../apps/web/src/app/(marketing)/contacto/_components/ContactTopics.tsx>).
11. [Opciones de Soporte](<../../apps/web/src/app/(marketing)/soporte/_constants.ts>).
12. [Temas de Soporte](<../../apps/web/src/app/(marketing)/soporte/_components/SupportTopics.tsx>).
13. [FAQ](<../../apps/web/src/app/(marketing)/preguntas-frecuentes/_data.ts>).

Agregados:

1. [Tests de superficies públicas](../../apps/web/src/components/marketing/__tests__/turnos-public-surfaces.test.tsx).
2. [Tests de navbar](../../apps/web/src/components/navigation/__tests__/marketing-turnos.test.tsx).
3. [Tests de Contacto/Soporte](<../../apps/web/src/app/(marketing)/contacto/__tests__/turnos-options.test.tsx>).
4. Este reporte.

El directorio de la landing PUBLIC 01 ya estaba sin seguimiento al iniciar la tarea.
Se preserva sin cambios; no se atribuye su creación a esta entrega.

## Invariantes y deuda técnica

- `appointments.is_active` sigue siendo `false`, comprobado por tests.
- `/pricing`, `PricingClient`, `BillingVertical`, checkout y Mercado Pago: sin cambios.
- Backend, `/t/[slug]` y S8: sin cambios.
- Contratación online de Turnos: deshabilitada.
- Nuevos Client Components: **0**.
- Nuevos fetches de aplicación: **0**.
- Nuevas dependencias, imágenes de aplicación, dynamic imports y estado React: **0**.
- Sin React Query, Framer Motion, carrusel, scroll horizontal ni JS de layout nuevos.
- Los cambios de formato corresponden a Prettier sobre los archivos tocados.

Deuda técnica registrada: el copy comercial de productos permanece distribuido entre
home, navegación, servicios, Nosotros y opciones de formularios, como ocurría antes.
Un eventual registro central de productos requiere otro slice; no se duplica pricing
ni se intenta ese refactor aquí. Contacto y Soporte conservan sus arrays paralelos de
iconos, sincronizados para Turnos y cubiertos por renderizado en los tests.

Resultado: **TURNOS PUBLIC 02 — CLOSED**.
