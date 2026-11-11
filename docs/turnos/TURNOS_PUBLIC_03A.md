# TURNOS PUBLIC 03A

## Estado de cierre

**NOT CLOSED.** La funcionalidad y las validaciones disponibles pasan, pero el navegador integrado no permitió medir un viewport CSS de exactamente 1024 px: con su escala de dispositivo 0.8, las dimensiones configurables más cercanas produjeron 1023 y 1025 px. Ambos anchos pasaron sin overflow y 1025 px ejercita la rama `lg` (desde 1024 px), pero queda pendiente la medición exacta requerida.

No se activó Turnos ni se avanzó a PUBLIC 03B.

## Arquitectura implementada

- La opción Turnos se incorpora al selector de precios y acepta `service=appointments`.
- `PricingVertical` agrega la opción pública `appointments` sin ampliar `BillingVertical`. `isBillingVertical` excluye Turnos de las rutas de suscripción.
- `AppointmentsPricingSection` obtiene productos, planes, tiers y precios mediante el catálogo canónico. La presentación es informativa.
- La grilla de tiers IA usa dos columnas desde `xl`; en la prueba de 1025 px, el diseño anterior desbordaba 3 px en cada tier visible. El ajuste eliminó ese overflow en las mediciones posteriores.

### Por qué `BillingVertical` quedó intacto

Turnos no está habilitado para contratación y no participa del flujo de facturación. Mantenerlo fuera de `BillingVertical` preserva los contratos existentes de checkout y billing; la unión local `PricingVertical` solo habilita la presentación pública.

## Archivos de PUBLIC 03A

- `apps/web/src/app/(marketing)/pricing/page.tsx`: metadatos de la página de precios.
- `apps/web/src/app/(marketing)/pricing/pricing-client.tsx`: selector, query param y separación del flujo de billing.
- `apps/web/src/app/(marketing)/pricing/appointments-pricing-section.tsx`: sección informativa, catálogo y breakpoint responsive.
- `apps/web/src/app/(marketing)/pricing/__tests__/appointments-pricing.test.tsx`: pruebas de integración de precios y ausencia de compra.

Los cambios existentes de PUBLIC 02 en otras áreas del worktree no forman parte de esta lista ni fueron revertidos.

## Planes, tiers y facturación

| Código lógico | Contenido | Mensual | Anual |
|---|---|---:|---:|
| `appointments` | Turnos | $23.000 | $220.800 |
| `appointments_pro` | Turnos Pro | $28.000 | $268.800 |
| `appointments_ai` / `ai_300` | Turnos IA, 300 sesiones/mes | $150.000 | $1.440.000 |
| `appointments_ai` / `ai_1500` | Turnos IA, 1.500 sesiones/mes | $275.000 | $2.640.000 |
| `appointments_ai` / `ai_3000` | Turnos IA, 3.000 sesiones/mes | $385.000 | $3.696.000 |
| `appointments_ai` / `custom` | A medida | A coordinar | A coordinar |

IA se muestra como un solo plan lógico con cuatro tiers anidados. Los importes se leen del catálogo canónico; el ciclo anual sigue la regla anual existente.

El ciclo mensual → anual → mensual se comprobó en runtime: los importes fijos y los tres tiers cambiaron al valor anual y regresaron al valor mensual original.

El tier `custom` nunca muestra `$0` ni “Gratis” y ofrece **Contactar ventas** hacia `/contacto`. Los CTAs de los planes y tiers autogestionados llevan a `/turnos`; no son CTAs de contratación.

## Estado y límites transaccionales

- `appointments.is_active === false`; la página muestra “Contratación online próximamente”.
- No se añadió Turnos a `BillingVertical`.
- No hay links `/subscribe` en la sección; las pruebas también verifican que no haya `router.push` ni llamadas a `fetch`.
- En la interacción Docker desde el selector, entrar a Turnos no generó solicitudes de red ni errores de página. No se observaron quote, billing intent, checkout o Mercado Pago.
- No se añadieron fetches de aplicación ni una nueva directiva/client boundary; la sección se integra en la superficie de precios existente.

## Validaciones

### Locales

Los tests locales, typecheck y build existentes estaban verdes al iniciar este cierre. Las pruebas focalizadas se volvieron a ejecutar en el builder Docker después del ajuste responsive.

### Docker oficial

Se usaron `apps/web/Dockerfile` y los Compose oficiales con el proyecto aislado `turnos-public03a`. Se levantó solamente `web` con `--no-deps`; no se iniciaron API, PostgreSQL, Redis, workers ni migraciones.

- Tests focalizados: **23/23 aprobados** en los dos archivos solicitados.
- Typecheck: exit code 0.
- ESLint focalizado: exit code 0, 0 errores y 2 warnings preexistentes en `pricing-client.tsx` (setState dentro de effect y `any`).
- Prettier focalizado: exit code 0 en la sección y su test.
- Build de producción Docker: exit code 0; compilación, TypeScript y generación de páginas completados.
- Runner Docker: HTTP 200 para `/pricing`, `/pricing?service=appointments` y `/turnos`.

Compose informó variables de entorno locales no configuradas; no impidieron los checks ni el runtime.

### Navegador sobre Docker

- `service=appointments` selecciona Turnos, no Gestión.
- Se muestran exactamente los planes lógicos Turnos, Turnos Pro y Turnos IA, con tiers 300, 1500, 3000 y A medida.
- El selector mostró el contenido correspondiente de Gestión, Carta, Reseñas y Turnos; las otras tres verticales conservaron sus planes.
- El selector no introdujo una navegación transaccional ni solicitudes de aplicación al entrar a Turnos.
- No se registraron errores de página.

### Responsive

Tras el ajuste, `scrollWidth <= clientWidth` para el documento, selector, toggle, cards de planes y tiers IA en todas las dimensiones CSS que el navegador permitió medir:

| Ancho CSS medido | `clientWidth` | `scrollWidth` | Overflow en componentes |
|---:|---:|---:|---|
| 320 | 301 | 301 | No |
| 375 | 356 | 356 | No |
| 768 | 750 | 750 | No |
| 1023 | 1005 | 1005 | No |
| 1025 | 1006 | 1006 | No |
| 1280 | 1261 | 1261 | No |
| 1440 | 1421 | 1421 | No |

El navegador usa `devicePixelRatio = 0.8`; los tamaños enteros configurables saltan de 1023 a 1025 px CSS. El ancho exacto de 1024 px queda sin evidencia directa y es el único gate pendiente para cerrar.

## Regresión y alcance

- Sin cambios en backend, checkout, Mercado Pago, `/t/[slug]` o S8.
- Sin cambios a manifiestos/lockfiles ni dependencias nuevas.
- Sin imágenes nuevas.
- El catálogo canónico existente se consumió sin duplicar precios en el componente.

## Limpieza Docker

- Se detuvo y eliminó el contenedor `web` aislado y la red `turnos-public03a_default`.
- No se iniciaron PostgreSQL ni otros servicios; no se ejecutaron migraciones.
- El volumen `turnos-public03a_postgres_data` quedó intacto; no se montó ni se eliminó.
- Se retiraron los overrides y resultados temporales de validación.

## Deuda técnica

- Turnos permanece intencionalmente inactivo; el flujo de contratación online no forma parte de PUBLIC 03A.
- Resolver la medición exacta de 1024 px en un navegador con escala 1:1 y repetir `scrollWidth <= clientWidth` antes de marcar el slice como cerrado.
- Los dos warnings de ESLint y los avisos de configuración Docker descritos arriba no fueron introducidos ni corregidos en este slice.
