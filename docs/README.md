# Mirubro Monorepo

Base monorepo para un SaaS multi-tenant con Next.js + Django + PostgreSQL listo para correr en local con Docker Compose.

## Requisitos

- Node.js 20+
- npm 10+
- Python 3.12+
- Docker + Docker Compose

## Estructura

```
apps/
  web/        → Next.js (marketing + app)
services/
  api/        → Django + DRF
packages/
  config/     → ESLint/Prettier compartido
  ui/         → Futuras primitivas de diseño
infra/
  docker-compose.yml
```

## Variables de entorno

1. Copiar los ejemplos:
   - `cp apps/web/.env.example apps/web/.env`
   - `cp services/api/.env.example services/api/.env`
2. Ajustar secretos / credenciales según tu entorno.
3. En Docker Compose, asegurate de tener:

- `apps/web/.env`: `NEXT_PUBLIC_API_URL=http://localhost:8000` y `API_INTERNAL_URL=http://mirubro-api:8000`.
- `services/api/.env`: agrega `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,mirubro-api` y deja `COOKIE_DOMAIN=` (vacío), `COOKIE_SECURE=False`, `COOKIE_SAMESITE=Lax` para permitir cookies httpOnly en local. **Nunca uses `COOKIE_DOMAIN=localhost`**, los navegadores descartan ese valor y no guardan las cookies.

## Instalación

```bash
npm install
pip install -r services/api/requirements.txt
```

## Comandos útiles

- `npm run dev` → Levanta todo el stack con Docker Compose (web, api, postgres, redis).
- `npm run dev:web` → Next.js en modo dev local (sin Docker).
- `npm run dev:api` → Django dev server local (usa `.env`).
- `npm run lint` → Ejecuta ESLint de la app web.
- `npm run format` → Aplica Prettier en la app web.

## Servicios expuestos

- Web: http://localhost:3000
- Panel de servicios: http://localhost:3000/app/servicios
- Gestion Comercial:
  - Dashboard: http://localhost:3000/app/gestion/dashboard
  - Productos: http://localhost:3000/app/gestion/productos
  - Stock: http://localhost:3000/app/gestion/stock
  - Valorización de stock: http://localhost:3000/app/gestion/stock/valorizacion
  - Ventas: http://localhost:3000/app/gestion/ventas
  - Registrar venta: http://localhost:3000/app/gestion/ventas/nueva
- Healthcheck API: http://localhost:8000/api/v1/health
- Documentación API: http://localhost:8000/api/docs
- Auth API:
  - `POST http://localhost:8000/api/v1/auth/login/`
  - `POST http://localhost:8000/api/v1/auth/logout/`
  - `POST http://localhost:8000/api/v1/auth/refresh/`
  - `GET  http://localhost:8000/api/v1/auth/me/`
- Service Hub API: `GET http://localhost:8000/api/v1/services/`

### Catálogo (Productos)

- `GET/POST   /api/v1/catalog/products/`
- `GET/PATCH  /api/v1/catalog/products/{id}/` (DELETE hace soft delete vía `is_active = false`).

### Inventario

- `GET        /api/v1/inventory/stock/` (filtros `search` y `status=low|out|ok`).
- `GET/POST   /api/v1/inventory/movements/` (+ filtro `product_id`).
- `GET        /api/v1/inventory/movements/{id}/`
- `GET        /api/v1/inventory/summary/`
- `GET        /api/v1/inventory/valuation/` calcula la valuación del stock y proyección de ganancia potencial. Filtros: `q`, `status`, `active`, `only_in_stock`, `sort`. Requiere `view_stock`. Los campos de costo/ganancia solo se devuelven si el rol posee `manage_products`.
  > Notas: los movimientos `IN` suman, `OUT/WASTE` restan y `ADJUST` setea la cantidad absoluta indicada en `quantity`. Si una operación deja el stock negativo devuelve 400.

#### Valorización de stock / Proyección de ganancia

- Ruta UI: `/app/gestion/stock/valorizacion` (dentro de Gestión Comercial, pestaña Stock).
- Muestra tarjetas de "Valor a precio", "Valor a costo" y "Ganancia potencial", más una tabla filtrable con Qty, costo unitario, precio unitario, valorización por producto y margen.
- Filtros disponibles: búsqueda por nombre/SKU, estado (`ok|low|out`), solo con stock, activos/inactivos y ordenamientos (`top` ganancia, `top` valor, cantidad, nombre).
- Requiere que el plan tenga las features `products` + `inventory` habilitadas y que el rol tenga `view_stock`. Los costos/ganancias sólo aparecen si el usuario tiene `manage_products`.
- Ideal para preparar órdenes de compra y pricing rápido sin tener que exportar a Excel.

### Ventas

- `GET /api/v1/sales/` listado paginado con filtros `status`, `payment_method`, `date_from/date_to` y `search` (número, cliente o notas).
- `POST /api/v1/sales/` crea una venta con items `{ product_id, quantity, unit_price }`, calcula subtotal/descuento/total y descuenta stock (crea movimientos `OUT`).
- `GET /api/v1/sales/{id}/` devuelve el detalle completo incluyendo items.
- `POST /api/v1/sales/{id}/cancel/` (opcional) revierte stock con movimientos `IN` si tenés `cancel_sales`.

Los roles `cashier`, `staff`, `manager` y `owner` pueden crear ventas (`create_sales`). `view_sales` controla el acceso a la pantalla y API.

### Restaurante Inteligente · Órdenes

- `GET /api/v1/orders/` lista las órdenes filtrando por estado (`pending`, `preparing`, `ready`, `delivered`, `charged`, `canceled`).
- `POST /api/v1/orders/` crea una nueva orden del salón o delivery con los items cargados manualmente o referenciando productos del catálogo.
- `GET /api/v1/orders/{id}/` devuelve el detalle completo con items.
- `POST /api/v1/orders/{id}/status/` actualiza el estado operativo (pendiente → en preparación → lista → entregada) siempre que tengas `change_order_status`.
- `POST /api/v1/orders/{id}/close/` genera una venta vinculada a la orden, descuenta stock de los productos utilizados y marca la orden como `charged`. Requiere permisos `close_orders` y respeta la configuración comercial (cliente obligatorio, caja abierta, stock negativo, etc.).

## Autenticación JWT (cookies httpOnly)

1. Crear un usuario en Django (o agregar más via admin):

```bash
cd services/api
python manage.py createsuperuser
```

2. Levantar el stack con `npm run dev` para exponer Next (3000) + API (8000).
3. Entrar a `http://localhost:3000/entrar` y loguearte con email/contraseña creados.
4. El backend genera tokens JWT (SimpleJWT) y los envía en cookies httpOnly (`access_token`, `refresh_token`).
5. Las rutas de `/app` validan sesión en el server y revisan el estado del plan:

- Sin sesión → redirect a `/entrar`.
- Plan no activo → redirect a `/app/planes` y se ocultan features (ej. Órdenes) según `features` del plan.

> Tip: usa `http://localhost:8000/admin/apps/business/subscription/` para cambiar `status` y probar el flujo de suspensión.

### Cómo probar que las cookies JWT funcionan

1. **Ver Set-Cookie al iniciar sesión**

```bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{"email":"tu@correo.com","password":"********"}' \
  http://localhost:8000/api/v1/auth/login/
```

Deberías ver dos cabeceras `Set-Cookie: access_token=...` y `Set-Cookie: refresh_token=...` con `HttpOnly; SameSite=Lax`.

2. **Reutilizar las cookies para /auth/me**

```bash
curl -b "access_token=...; refresh_token=..." http://localhost:8000/api/v1/auth/me/
```

3. **Desde el navegador** abre DevTools → Storage → Cookies → `http://localhost` y verifica que ambos tokens estén guardados tras loguearte en `http://localhost:3000/entrar`.

## Datos demo automatizados

Podés cargar dos negocios de ejemplo con todos los roles en cualquier entorno (local o Docker) ejecutando:

```bash
docker compose -f infra/docker-compose.yml exec api python manage.py seed_demo
```

Opciones útiles:

- `--password <pwd>`: define la contraseña común para todos los usuarios (por defecto `mirubro123`).
- `--reset`: elimina ambos negocios y usuarios demo antes de recrearlos.

El comando es idempotente, imprime un resumen al finalizar y siempre apunta a `http://localhost:3000/entrar` para probar el login. Para el negocio **Manzana** además genera 10 productos activos con stock inicial y dos ventas demo para que `/app/gestion/ventas` tenga datos reales.

### Negocio 1 · Manzana (Gestión Comercial · plan PRO)

| Rol     | Email                         | Password     |
| ------- | ----------------------------- | ------------ |
| owner   | manzana.owner@mirubro.local   | `mirubro123` |
| manager | manzana.manager@mirubro.local | `mirubro123` |
| cashier | manzana.cashier@mirubro.local | `mirubro123` |
| staff   | manzana.staff@mirubro.local   | `mirubro123` |
| viewer  | manzana.viewer@mirubro.local  | `mirubro123` |

> Tip rápida: Ingresá con `manzana.owner@mirubro.local` para ver costos y márgenes en `/app/gestion/stock/valorizacion`. Con `manzana.staff@mirubro.local` sólo vas a ver el valor a precio (los campos de costo/ganancia se ocultan), ideal para probar los guard rails de permisos.

### Negocio 2 · La Pizza (Restaurantes · plan PLUS)

| Rol     | Email                         | Password     |
| ------- | ----------------------------- | ------------ |
| owner   | lapizza.owner@mirubro.local   | `mirubro123` |
| manager | lapizza.manager@mirubro.local | `mirubro123` |
| cashier | lapizza.cashier@mirubro.local | `mirubro123` |
| kitchen | lapizza.kitchen@mirubro.local | `mirubro123` |
| salon   | lapizza.salon@mirubro.local   | `mirubro123` |
| viewer  | lapizza.viewer@mirubro.local  | `mirubro123` |

## Flujo para levantar todo

1. Instalar dependencias (ver sección anterior).
2. Copiar `.env` desde los ejemplos.
3. Ejecutar `npm run dev` en la raíz del repo.
4. Verificar que:
   - `http://localhost:3000` carga marketing/app.

- `http://localhost:3000/entrar` permite iniciar sesión con el usuario creado.
- `http://localhost:8000/api/v1/health` responde `{ "status": "ok" }`.
- `http://localhost:8000/api/docs` muestra el Swagger generado por drf-spectacular.
- `http://localhost:3000/app/servicios` lista los servicios habilitados según el plan.

## Guía de prueba manual (Gestion Comercial)

1. Iniciar sesión en `http://localhost:3000/entrar`.
2. Ingresar a `/app/servicios` y confirmar que "Gestion Comercial" figura como habilitado.
3. Entrar a `/app/gestion/dashboard` para ver el resumen del servicio.
4. Crear al menos un producto nuevo desde `/app/gestion/productos`.
5. Registrar un movimiento (entrada y salida) desde `/app/gestion/stock`.
6. Verificar que el stock actualizado se refleje en la tabla y en los movimientos recientes.
7. Con un rol con `create_sales` (ej. `manzana.cashier`), entrar a `/app/gestion/ventas/nueva`, agregar dos productos y confirmar la venta. Chequear que la venta figura en `/app/gestion/ventas` y que el stock del producto se haya descontado.


