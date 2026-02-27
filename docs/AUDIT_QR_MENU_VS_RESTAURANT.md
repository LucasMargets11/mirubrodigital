# AUDIT: Menú QR Online vs Restaurante Inteligente

**Fecha:** 2026-02-24  
**Autor:** GitHub Copilot  
**Estado:** Implementado

---

## 1. Resumen Ejecutivo

| Ítem | Estado antes | Estado después |
|------|-------------|---------------|
| `require_service('menu_qr')` bloquea a usuarios de restaurante | ❌ Bug crítico | ✅ Fijo vía jerarquía de servicios |
| Features QR en plan `plus` (restaurante legacy) | ❌ Ausentes | ✅ Añadidas |
| Bundle `restaurante_inteligente` con QR incluido | ❌ No existía | ✅ Creado en seed_billing |
| Demo accounts para QR y Restaurante | ❌ No existían | ✅ `seed_restaurant_qr_demo_accounts` |
| Tests de acceso diferenciado | ❌ No existían | ✅ `test_menu_qr_access.py` |
| `PlansBundles.tsx` para vertical `menu_qr` | ❌ Placeholder | ✅ Muestra bundle real |
| Gating `require_service('restaurante')` en vistas de mesas/órdenes | ❌ Solo RBAC | ✅ Defense-in-depth añadida |

---

## 2. Inventario de Identificadores

### 2.1 Service slugs (campo `Business.default_service` / `Subscription.service`)

| Slug | Descripción |
|------|-------------|
| `gestion` | Gestión Comercial (inventario, ventas, caja) |
| `restaurante` | Restaurante Inteligente (mesas, órdenes, cocina + QR incluido) |
| `menu_qr` | Menú QR Online standalone (solo carta + branding + QR) |

### 2.2 Plan codes (`BusinessPlan` / `Subscription.plan`)

| Plan | Vertical | Descripción |
|------|---------|-------------|
| `start` | commercial | Gestión Comercial básica |
| `pro` | commercial | Gestión Comercial completa |
| `business` | commercial | Gestión Comercial multi-sucursal + facturación |
| `enterprise` | commercial | Igual que business + servicios enterprise |
| `menu_qr` | menu_qr | Plan único de Menú QR Online |
| `starter` | legacy | Gestión legacy (compatibilidad) |
| `plus` | legacy | Restaurante legacy (compatibilidad) |

### 2.3 Billing Bundle codes (`billing.Bundle.code`)

| Code | Vertical | Descripción |
|------|---------|-------------|
| `gestion_start` | commercial | Gestión Start |
| `gestion_pro` | commercial | Gestión Pro |
| `gestion_business` | commercial | Gestión Business |
| `resto_basic` | restaurant | Restaurante básico (legacy) |
| `restaurante_inteligente` | restaurant | Restaurante Inteligente (nuevo, incluye QR) |
| `menu_qr_online` | menu_qr | Menú QR Online standalone |

### 2.4 Feature keys (`features.py` / `FEATURE_KEYS`)

| Feature Key | Descripción | Servicio |
|-------------|-------------|---------|
| `menu_builder` | Editor de carta | QR + Restaurant |
| `menu_branding` | Branding del menú | QR + Restaurant |
| `public_menu` | Menú público online | QR + Restaurant |
| `menu_qr_tools` | Generación QR + link | QR + Restaurant |
| `resto_orders` | Órdenes de restaurante | Restaurant only |
| `resto_kitchen` | Display de cocina | Restaurant only |
| `resto_sales` | Ventas de restaurante | Restaurant only |
| `resto_tables` | Mapa de mesas | Restaurant only |
| `resto_menu` | Carta para restaurante | Restaurant only |
| `resto_reports` | Reportes de restaurante | Restaurant only |

### 2.5 RBAC Permission sets (`rbac.py`)

| Service | Permissions de menú incluidas |
|---------|------------------------------|
| `menu_qr` | `view_menu`, `manage_menu`, `manage_menu_branding`, `view_menu_admin`, `view_public_menu` |
| `restaurante` | Todo lo anterior + `view_tables`, `create_orders`, `view_kitchen_board`, etc. |
| `gestion` | Ninguna de menú |

---

## 3. Rutas Frontend Detectadas

### 3.1 App (autenticado)

| Ruta | Servicio | Componente / Descripción |
|------|---------|--------------------------|
| `/app/menu` | menu_qr | Editor de carta (usa `MenuClient` de `/app/carta`) |
| `/app/menu/branding` | menu_qr | Branding personalizado |
| `/app/menu/qr` | menu_qr | Generación QR y URL pública |
| `/app/menu/preview` | menu_qr | Preview del menú público |
| `/app/carta` | restaurante | Editor de carta del restaurante (mismo `MenuClient`) |
| `/app/tables` | restaurante | Mapa de mesas |
| `/app/orders` | restaurante | Gestión de órdenes |
| `/app/kitchen` | restaurante | Display de cocina en vivo |
| `/app/servicios` | todos | Servicios habilitados / switcher |

### 3.2 Marketing

| Ruta | Descripción |
|------|-------------|
| `/services` | Página con los 3 servicios (Gestión, Restaurante, Menú QR) |
| `/pricing?service=commerce` | Planes de Gestión Comercial |
| `/pricing?service=restaurant` | Planes de Restaurante |
| `/pricing?service=menu_qr` | Planes de Menú QR Online |

---

## 4. Endpoints Backend

### 4.1 Menú QR (ambos servicios pueden acceder)

| Método | Endpoint | Permission | Servicio |
|--------|---------|------------|---------|
| GET | `/api/v1/menu-qr/<business_id>/` | `view_menu_admin` + `require_service('menu_qr')` | menu_qr **o** restaurante |
| GET/POST/PATCH/DELETE | `/api/v1/menu/categories/` | `view_menu` / `manage_menu` | menu_qr o restaurante |
| GET/POST/PATCH/DELETE | `/api/v1/menu/items/` | `view_menu` / `manage_menu` | menu_qr o restaurante |
| GET | `/api/v1/menu/structure/` | `view_menu` | menu_qr o restaurante |
| POST | `/api/v1/menu/import/` | `import_menu` | menu_qr o restaurante |
| GET | `/m/<slug>/` | público (sin autenticación) | cualquiera |

### 4.2 Restaurante (solo `restaurante`)

| Método | Endpoint | Permission | Servicio |
|--------|---------|------------|---------|
| GET | `/api/v1/restaurant/tables/` | `require_service('restaurante')` | restaurante only |
| GET | `/api/v1/restaurant/tables/map-state/` | `require_service('restaurante')` | restaurante only |
| GET/POST | `/api/v1/orders/` | `create_orders` + `require_service('restaurante')` | restaurante only |
| GET/POST | `/api/v1/tables/` | `view_tables` + `require_service('restaurante')` | restaurante only |
| GET/POST | `/api/v1/kitchen/` | `view_kitchen_board` | restaurante only |

---

## 5. Jerarquía de Servicios (nueva)

```
SERVICE_IMPLIES = {
    'restaurante': {'restaurante', 'menu_qr'},
}
```

- `restaurante` → puede acceder a endpoints marcados con `require_service('menu_qr')` Y `require_service('restaurante')`
- `menu_qr` → solo puede acceder a endpoints marcados con `require_service('menu_qr')`
- `gestion` → puede acceder a endpoints marcados con `require_service('gestion')` únicamente

---

## 6. Matriz de Acceso

| Módulo / Endpoint | `menu_qr_online` | `restaurante_inteligente` |
|-------------------|:---:|:---:|
| Ver/editar carta (categorías, items) | ✅ | ✅ |
| Branding del menú (logo, colores) | ✅ | ✅ |
| Generar QR / URL pública | ✅ | ✅ |
| Menú público (URL sin login) | ✅ | ✅ |
| Importar/exportar carta (Excel) | ✅ | ✅ |
| **Mapa de mesas** | ❌ | ✅ |
| **Órdenes / POS** | ❌ | ✅ |
| **Cocina en vivo (KDS)** | ❌ | ✅ |
| **Caja del restaurante** | ❌ | ✅ |
| **Reportes de restaurante** | ❌ | ✅ |
| **WhatsApp bot** | ❌ | ✅ |
| Configuración general | ✅ | ✅ |
| Gestión de usuarios/roles | ✅ | ✅ |

---

## 7. Cómo se resuelve el acceso hoy (post-fix)

### Backend (capas en orden)
1. **`HasBusinessMembership`**: ¿el usuario pertenece a algún negocio?
2. **`require_service(slug)`**: ¿el negocio tiene ese servicio (o uno que lo implica)?
3. **`HasPermission`**: ¿el rol del usuario tiene el permiso RBAC para esta acción?
4. **`HasEntitlement`** (solo Gestión Comercial): ¿el plan del negocio incluye este módulo?

### Frontend
1. `active_service` determina qué config de sidebar se usa (`restaurante` → nav restaurante, `menu_qr` → nav menú QR)
2. Cada ítem de nav tiene `featureKey` y/o `permissionKey` que se validan contra el contexto del negocio
3. Marketing: `PlansBundles` carga bundles por vertical y muestra precio/módulos

---

## 8. Bugs identificados y estado

| # | Bug | Impacto | Estado |
|---|-----|---------|--------|
| 1 | `require_service('menu_qr')` bloquea a usuarios de restaurante | **Crítico** — restaurante no puede generar QR | ✅ Fijo |
| 2 | Plan `plus` no incluye features QR | **Alto** — `enabled_services` no activa `menu_qr` para restaurante | ✅ Fijo |
| 3 | No hay bundle `restaurante_inteligente` con QR incluido | **Medio** — pricing page no refleja QR en restaurante | ✅ Fijo |
| 4 | `PlansBundles` muestra placeholder para `menu_qr` cuando no hay bundles | **Medio** — requiere `seed_billing` ejecutado | ✅ Fijo |
| 5 | Vistas de restaurante sin `require_service('restaurante')` | **Bajo** — RBAC ya bloquea, defense-in-depth faltante | ✅ Fijo |
| 6 | No hay cuentas demo de restaurante ni menu_qr standalone | **Medio** — no hay forma de probar sin crear manual | ✅ Fijo |

---

## 9. Instalar / Correr seeds

```bash
# 1. Seed billing (módulos y bundles para todos los servicios)
docker compose exec api python manage.py seed_billing

# 2. Seed cuentas demo de Gestión Comercial
docker compose exec api python manage.py seed_gestion_comercial_demo_accounts

# 3. Seed cuentas demo de Restaurante y Menú QR
docker compose exec api python manage.py seed_restaurant_qr_demo_accounts
```

### Credenciales demo resultantes

| Email | Password | Servicio | Bundle |
|-------|---------|---------|--------|
| `gc.basic@demo.local` | `Demo12345!` | Gestión Start | gestion_start |
| `gc.pro@demo.local` | `Demo12345!` | Gestión Pro | gestion_pro |
| `gc.max@demo.local` | `Demo12345!` | Gestión Business | gestion_business |
| `restaurant.demo@demo.local` | `Demo12345!` | Restaurante Inteligente | restaurante_inteligente |
| `qr.demo@demo.local` | `Demo12345!` | Menú QR Online | menu_qr_online |

---

## 10. Checklist de QA Manual

### QR Demo (`qr.demo@demo.local`)
- [ ] Entrar a app → sidebar muestra "Menú QR" solamente
- [ ] Puede crear categorías y productos en carta
- [ ] Puede subir logo y cambiar branding
- [ ] Puede generar QR y URL pública → abre desde incógnito sin login
- [ ] Intentar acceder `/app/tables` → redirigido/bloqueado
- [ ] Intentar acceder `/app/orders` → redirigido/bloqueado
- [ ] API `/api/v1/restaurant/tables/` → 403

### Restaurant Demo (`restaurant.demo@demo.local`)
- [ ] Entrar a app → sidebar muestra "Restaurante Inteligente" con mesas, órdenes, cocina, carta
- [ ] Puede acceder a mapa de mesas
- [ ] Puede crear y gestionar órdenes
- [ ] Puede acceder a cocina en vivo
- [ ] Puede editar carta desde `/app/carta`
- [ ] API `/api/v1/menu-qr/<id>/` → 200 (genera QR correctamente)
- [ ] Menú público funciona desde URL generada

### Marketing
- [ ] `/services` → muestra Gestión Comercial, Restaurantes, Menú QR Online
- [ ] `/pricing?service=menu_qr` → muestra bundle "Menú QR Online" con precio y módulos
- [ ] `/pricing?service=restaurant` → muestra bundle "Restaurante Inteligente" con precio y módulos
- [ ] CTA "Ver planes" conduce al pricing correcto para cada servicio
