# MiRubro Digital — Resumen del Sistema

> **Última actualización:** 3 de abril de 2026
> **Versión:** Auditoría completa post-Phase 9 (QR Reseñas Pricing Integration)

---

## 1. ¿Qué es MiRubro?

**MiRubro Digital** es una plataforma SaaS multi-tenant construida para PyMEs, con foco en gastronomía y comercio minorista en Latinoamérica (Argentina).

### Verticales de negocio (4)

| Vertical | Código | Descripción |
|----------|--------|-------------|
| **Gestión Comercial** | `gestion` | POS, inventario, ventas, clientes, facturación, tesorería, reportes |
| **Carta Online (Menú QR)** | `menu_qr` | Menú digital accesible por QR con branding personalizable |
| **Restaurante Inteligente** | `resto` | Operaciones de restaurante: pedidos, cocina, mesas, salón |
| **QR de Reseñas** | `qr_reviews` | Sistema de feedback con filtro inteligente y redirección a Google |

---

## 2. Stack Tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| **Frontend** | Next.js (App Router) + React + TailwindCSS + shadcn/ui + Radix | Next 16.1.6, React 18.3, TS 5.4.5, Tailwind 3.4 |
| **Backend** | Django + DRF + PostgreSQL + Celery + Redis | Django 5.0, DRF 3.15, Celery 5.3 |
| **Charts** | ECharts | 5.6.0 |
| **State Management** | TanStack Query (React Query) | 5.20.0 |
| **Validación** | Zod | 3.23.8 |
| **Animaciones** | Framer Motion | 12.35.2 |
| **Iconos** | Lucide React | 0.563.0 |
| **Pagos** | MercadoPago SDK | 2.2.x |
| **PDF** | ReportLab | 4.1.x |
| **Excel** | openpyxl (backend) + xlsx (frontend) | 3.1.x / 0.20.2 |
| **OCR/Barcode** | pytesseract + pyzbar + pdf2image | Document pipeline |
| **QR** | segno | 1.6.x |
| **Infra** | Docker Compose (dev), Terraform + AWS (prod) | Postgres 16, Redis 7 |
| **Testing** | Django TestCase (backend) + Vitest + Testing Library (frontend) | — |

---

## 3. Arquitectura del Monorepo

```
mirubrodigital/
├── apps/web/                   # Next.js frontend (port 3000)
│   └── src/
│       ├── app/                # App Router: 137 pages
│       ├── components/         # Componentes compartidos (14 categorías)
│       ├── features/           # 13 módulos funcionales
│       ├── hooks/              # Custom hooks
│       ├── lib/                # Auth, API client, utilidades
│       ├── services/           # Capa de servicios API
│       └── types/              # Tipos TypeScript (5 archivos)
├── services/api/               # Django REST API (port 8000)
│   └── src/
│       ├── apps/               # 17 Django apps
│       └── config/             # Settings, URLs, WSGI, Celery
├── infra/
│   ├── docker-compose.yml      # 7 servicios
│   └── terraform/              # AWS: VPC, RDS, ElastiCache, WAF
├── packages/
│   ├── config/                 # ESLint + Prettier compartido
│   └── ui/                     # Futuras primitivas de diseño
└── docs/                       # 50+ documentos de auditoría
```

### Métricas del código

| Métrica | Backend | Frontend |
|---------|---------|----------|
| Archivos de código | 469 `.py` | 584 `.ts/.tsx` |
| Tamaño total | ~3.4 MB | ~3.5 MB |
| Django apps | 17 | — |
| Páginas (routes) | — | 137 `page.tsx` |
| Archivos de test | 53 `test_*.py` | 15 `*.test.*` |
| Migraciones | 136 | — |
| Modelos | 100+ | — |
| Feature modules | — | 13 |

---

## 4. Servicios Docker

| Servicio | Imagen | Puerto | Propósito |
|----------|--------|--------|-----------|
| `postgres` | postgres:16-alpine | 5432 | Base de datos multi-tenant |
| `redis` | redis:7-alpine | 6379 | Cache + cola Celery |
| `api` | Django custom | 8000 | REST API + Swagger |
| `web` | Next.js custom | 3000 | Frontend (SSR + marketing) |
| `celery-worker` | Django custom | — | Tareas async (facturación, email, reportes) |
| `celery-beat` | Django custom | — | Tareas programadas (publicar blogs, suscripciones) |
| `ngrok` | ngrok/ngrok | 4040 | Tunnel para webhooks MP (perfil `tunnel`) |

---

## 5. Django Apps — Inventario Completo (17 apps)

### 5.1 accounts — Autenticación y RBAC
- **Modelos (8):** AccountProfile, Membership, EmployeeProfile, RolePermissionOverride, AccessAuditLog, AdminInternalNote, SupportTicket
- **Migraciones:** 27 (última: `0027_clear_must_change_pin`)
- **Funcionalidades:** JWT + cookies httpOnly, PIN para POS, MFA (TOTP), email verification, audit trail (70+ action types), soporte multi-tier, roles de plataforma (superadmin, operations, support_agent, content_admin)
- **Roles RBAC (10):** owner, admin, manager, cashier, staff, viewer, kitchen, salon, analyst, contador

### 5.2 business — Tenant y Entitlements
- **Modelos (7):** Business, ServicePolicy, Entitlements, BusinessBillingProfile, BusinessBranding, CommericalSettings (deprecated)
- **Migraciones:** 20 (última: `0020_add_qr_reviews`)
- **Status flow:** `onboarding → trialing → active → past_due → suspended → canceled`
- **Services:** gestion, restaurante, menu_qr, qr_reviews
- **Multi-branch:** vía `Business.parent` FK (HQ + sucursales)

### 5.3 billing — Suscripciones y Pagos
- **Modelos (6):** Plan, Module, Bundle, Promotion, SubscriptionIntent, PaymentEvent
- **Migraciones:** 11 (última: `0011_add_qr_reviews`)
- **3 sistemas de suscripción coexisten:**
  1. **Legacy:** `business.Subscription` (OneToOne) — plan + add-ons
  2. **Modern:** `billing.Subscription` — bundles + módulos
  3. **Canonical:** `billing.SubscriptionV2` — state machine completa, integración MercadoPago
- **Verticales de módulos:** commercial, restaurant, menu_qr, qr_reviews
- **Checkout:** MercadoPago → SubscriptionIntent → webhook → activación

### 5.4 catalog — Productos y Categorías
- **Modelos (2):** Product, ProductCategory
- **Migraciones:** 2
- **Features:** SKU, costo, precio, barcode, categorías por negocio, soft delete

### 5.5 inventory — Stock y Reposición
- **Modelos (5):** ProductStock, StockMovement, StockReplenishment, InventoryImportJob
- **Migraciones:** 8 (última: `0008_productstock_reserved_quantity`)
- **Movimientos:** IN/OUT/ADJUST/WASTE (con validación de stock negativo)
- **Reposición:** Integración con tesorería (proveedor → stock → transacción → perfil fiscal)
- **Import:** Excel upload → preview → apply (state machine)
- **Valuación:** Costo, precio, margen, ganancia potencial, filtros avanzados

### 5.6 sales — Ventas y Presupuestos
- **Modelos (4):** Sale, SaleItem, Quote, QuoteSequence
- **Migraciones:** 8 (última: `0008_ordersequence`)
- **Pagos:** CASH/TRANSFER/CARD/OTHER
- **POS:** created_by_employee, cancelled_by_employee
- **Quotes:** DRAFT → SENT → ACCEPTED/REJECTED/EXPIRED → CONVERTED + PDF

### 5.7 orders — Pedidos y Cocina (Restaurante)
- **Modelos (3):** Order, OrderItem, OrderDraft
- **Migraciones:** 9
- **Status flow:** DRAFT → OPEN → SENT → PAID → CANCELLED
- **Kitchen:** PENDING → IN_PROGRESS → READY → DONE → CANCELLED (con timestamps granulares)
- **Canales:** dine-in, pickup, delivery
- **Draft → Order:** carrito editable antes de confirmar

### 5.8 customers — CRM
- **Modelos (1):** Customer
- **Migraciones:** 4
- **Tipos:** INDIVIDUAL/COMPANY
- **Documentos:** DNI/CUIT/PASSPORT/OTHER
- **Condición fiscal:** CONSUMER/REGISTERED/MONOTAX/EXEMPT/OTHER
- **Tags JSON, contacto completo, historial de compras**

### 5.9 cash — Caja y Pagos
- **Modelos (5):** CashRegister, CashSession, Payment, CashMovement, (Terminal — Phase 2A)
- **Migraciones:** 8
- **Session:** OPEN → CLOSED → AUDITED
- **Pagos:** CASH/DEBIT/CREDIT/TRANSFER/WALLET/ACCOUNT
- **POS operativo:** PIN login, apertura/cierre por empleado

### 5.10 menu — Carta QR y Engagement
- **Modelos (6):** MenuCategory, MenuItem, PublicMenuConfig, MenuBrandingSettings, MenuEngagementSettings, MercadoPagoConnection, TipTransaction
- **Migraciones:** 9
- **Features:** Categorías, items con imagen y precio, branding (colores, tipografía, logo), slug público, QR dinámico
- **Tips:** MercadoPago (link, QR image, OAuth checkout)
- **Planes:** Básico (sin imágenes), Visual (con imágenes), Marca (dominio custom)

### 5.11 reviews — QR de Reseñas
- **Modelos (3):** ReviewConfig, Review, ReviewVisit
- **Migraciones:** 5 (última: `0005_reviewvisit`)
- **Filtro inteligente:** ≥4★ → Google, ≤3★ → feedback privado
- **Rating:** 1–5 estrellas + comentario + contacto opcional
- **Status:** NEW → READ → CONTACTED → RESOLVED
- **Source:** QR / MENU / DIRECT
- **Analytics:** ReviewVisit para tracking de visitas, ReviewStatsView para métricas agregadas
- **Público:** Landing page + submit por slug (`/r/[slug]`)
- **Planes (UI):** QR Reseñas ($25.000/mes) y Reseñas Pro ($35.000/mes)

### 5.12 resto — Mesas y Layout (Restaurante)
- **Modelos (3):** Table, TableLayout, TablePlacement
- **Migraciones:** 3
- **Grid:** Canvas con coordenadas (x,y), rotación, z-index
- **Live state:** Snapshot + map state endpoints

### 5.13 treasury — Tesorería y Finanzas
- **Modelos (6):** Account, TransactionCategory, Transaction, FixedExpense, FixedExpensePeriod, Expense
- **Migraciones:** 9 (última: `0009_sprint5_document_pipeline`)
- **Cuentas:** Cash, Bank, MP, Card Float, Other
- **Ledger:** Transaction con dirección IN/OUT/ADJUST, status POSTED/VOIDED
- **Gastos fijos:** Templates recurrentes con frecuencia (WEEKLY/MONTHLY/QUARTERLY/YEARLY)
- **Gastos ad-hoc:** Con auto-source desde reposición de stock
- **Attachment:** Documentos adjuntos a transacciones

### 5.14 invoices — Facturación Electrónica
- **Modelos (3):** DocumentSeries, Invoice (+ InvoiceSeries deprecated)
- **Migraciones:** 5
- **Tipos:** FACTURA, RECIBO, TICKET, NOTA_CREDITO, NOTA_DEBITO, REMITO
- **Letras:** A/B/C/M/X
- **Numeración atómica:** next_number con increment seguro
- **PDF:** Generación con ReportLab

### 5.15 tax_backup — Respaldo Impositivo
- **Modelos (6+):** ExpenseFiscalProfile, FiscalDocument, Alert, DuplicateRecord
- **Migraciones:** 6 (última: `0006_add_document_subtype`)
- **Dual-origin:** Expense + FixedExpensePeriod como fuente
- **Pipeline:** Upload → OCR → parsing → validación → alertas → deduplicación
- **Fiscal status:** SIN_COMPROBANTE → INCOMPLETO → REQUIERE_REVISION → VALIDO_CON_OBSERVACIONES → VALIDO
- **Allocation:** BUSINESS/MIXED/PERSONAL

### 5.16 blog — CMS Editorial
- **Modelos (2):** BlogCategory, BlogPost
- **Migraciones:** 2
- **Workflow:** DRAFT → PUBLISHED / SCHEDULED / ARCHIVED
- **SEO:** meta_title, meta_description, og_*, canonical_url
- **Content blocks:** JSON body (sin WYSIWYG visual aún)
- **Sitemap XML:** Endpoint público

### 5.17 reports — Analytics (read-only)
- **Modelos:** Ninguno (vistas agregadas solamente)
- **Endpoints:** Summary KPIs, sales time-series, product performance, leaderboard, stock alerts, cash closures, payment breakdown

---

## 6. Endpoints API — Mapa Completo

```
/api/v1/health/                        → Health check
/api/docs/                             → Swagger UI (drf-spectacular)
/api/schema/                           → OpenAPI schema

AUTH & ACCESS
/api/v1/auth/                          → login, logout, refresh, me, onboarding
/api/v1/auth/employee-login/           → POS login PIN
/api/v1/auth/employee-change-pin/      → POS cambio de PIN
/api/v1/pos/                           → POS session endpoints
/api/v1/owner/access/                  → Owner access control
/api/v1/support/                       → Tenant support tickets
/api/v1/platform-admin/               → Platform admin (backoffice)

CORE SAAS
/api/v1/                               → Business CRUD, dashboard, settings, entitlements
/api/v1/catalog/                       → Products + categories
/api/v1/customers/                     → CRM
/api/v1/inventory/                     → Stock, movements, import, valuation, replenishment
/api/v1/sales/                         → Sales, quotes, cancel
/api/v1/orders/                        → Restaurant orders, drafts, kitchen board
/api/v1/cash/                          → Cash sessions, payments, movements
/api/v1/invoices/                      → Document series, invoice issuance, PDF
/api/v1/reports/                       → Summary, sales, products, stock, cash, payments

ENGAGEMENT & QR
/api/v1/menu/                          → Menu categories, items, config
/api/v1/public/menu/<slug>/            → Public menu by slug
/api/v1/menu-qr/<business_id>/        → QR code generation
/api/v1/reviews/                       → Review config, list, stats, QR
/api/v1/reviews/public/<slug>/         → Public review landing + submit

RESTAURANT
/api/v1/resto/                         → Table CRUD, layout
/api/v1/restaurant/tables/             → Live snapshot
/api/v1/restaurant/tables/map-state/   → Spatial state
/api/v1/restaurant/reports/            → Restaurant-specific reports

FINANCE & BILLING
/api/v1/billing/                       → Subscriptions, checkout, MercadoPago webhooks
/api/v1/treasury/                      → Accounts, transactions, expenses, payroll
/api/v1/tax-backup/                    → Fiscal profiles, documents, validation

CONTENT
/api/v1/blog/                          → Posts, categories, sitemap, preview
```

---

## 7. Frontend — Rutas y Páginas (137 pages)

### Autenticación (5 pages)
- `/entrar` — Login
- `/cambiar-contrasena` — Cambio de contraseña
- `/olvidar-contrasena` — Recuperación
- `/nueva-contrasena` — Reset de contraseña
- `/verificar-email` — Verificación de email

### Marketing (19 pages)
- `/` — Homepage
- `/blog`, `/blog/[slug]`, `/blog/preview/[postId]` — Blog público
- `/carta` — Landing Carta Online
- `/contacto` — Contacto
- `/features` — Features showcase
- `/gestion` — Landing Gestión Comercial
- `/nosotros` — Sobre nosotros
- `/preguntas-frecuentes` — FAQ
- `/pricing` — Comparación de precios
- `/privacidad` — Política de privacidad
- `/resenas` — Landing QR de Reseñas
- `/services` — Servicios
- `/soporte` — Soporte
- `/subscribe`, `/subscribe/return` — Suscripción newsletter
- `/terminos` — Términos y condiciones

### Admin Backoffice (13 pages)
- `/admin` — Dashboard principal
- `/admin/login` — Login admin
- `/admin/mfa-setup` — Configuración MFA
- `/admin/dashboard` — Analytics admin
- `/admin/blog`, `/admin/blog/nuevo`, `/admin/blog/[postId]` — CMS editorial
- `/admin/clientes`, `/admin/clientes/[id]` — Gestión de cuentas
- `/admin/configuracion` — Configuración plataforma
- `/admin/reportes` — Reportes admin
- `/admin/suscripciones`, `/admin/suscripciones/[id]` — Suscripciones
- `/admin/soporte`, `/admin/soporte/nuevo`, `/admin/soporte/[id]` — Tickets de soporte

### App Principal — Gestión Comercial (~40 pages)
- **Dashboard:** `/app/gestion/dashboard` (con prioridades del día)
- **Productos:** `/app/gestion/productos`, `/app/gestion/productos/categorias`
- **Stock:** `/app/gestion/stock`, `stock/compras`, `stock/compras/[id]`, `stock/importar`, `stock/reponer`, `stock/valorizacion`
- **Ventas:** `/app/gestion/ventas`, `ventas/nueva`, `ventas/[id]`, `ventas/pedidos/...`, `ventas/presupuestos/...`
- **Clientes:** `/app/gestion/clientes`, `clientes/[id]`
- **Facturas:** `/app/gestion/facturas`, `facturas/[id]`
- **Finanzas:** `/app/gestion/finanzas` (cuentas, gastos, gastos/respaldo, gastos/tax-backup, movimientos, reportes, sueldos, resumen, configuracion)
- **Reportes:** `/app/gestion/reportes` (ventas, productos, pagos, caja, caja/[id])
- **Configuración:** `/app/gestion/configuracion` (negocio, plan-facturacion)

### App — QR de Reseñas (4 pages)
- `/app/resenas` — Hub del producto (planes, filtro inteligente, dashboard analytics)
- `/app/resenas/configuracion` — Config de reviews (Google Place ID, threshold, mensajes)
- `/app/resenas/feedback` — Lista de feedback recibido
- `/app/resenas/qr` — QR code para compartir + descarga

### App — Restaurante (6+ pages)
- `/app/orders`, `/app/orders/new`, `/app/orders/[id]` — Pedidos
- `/app/tables` — Mesas
- `/app/kitchen` — KDS (Kitchen Display System)
- `/app/resto/operacion/...` — Operación restaurante (reportes de caja)
- `/app/resto/settings/`, `settings/tables` — Configuración mesas

### App — Carta Online
- `/app/carta` — Gestión del menú QR
- `/app/menu/branding`, `/app/menu/preview`, `/app/menu/qr` — Branding, preview, QR

### App — Operación / Caja
- `/app/operacion/caja` — Cash home
- `/app/operacion/caja/cierre` — Cierre de caja
- `/app/operacion/caja/movimientos` — Movimientos de caja

### App — Configuración General
- `/app/settings/access`, `/app/settings/access/roles/[role]` — Control de acceso / RBAC
- `/app/settings/branches` — Sucursales
- `/app/settings/online-menu` — Menú online settings

### App — Otros
- `/app/dashboard` — Dashboard principal
- `/app/servicios` — Selector de servicios activos
- `/app/planes` — Planes y suscripción
- `/app/owner` — Controles del owner
- `/app/cuenta/estado` — Estado de cuenta
- `/app/soporte`, `/app/soporte/nuevo`, `/app/soporte/[id]` — Tickets de soporte
- `/app/onboarding/...` — Wizard (servicio, plan, checkout)

### POS — Terminal de Venta (4 pages)
- `/pos/login` — Login por PIN
- `/pos/change-pin` — Cambio de PIN
- `/pos/terminal` — Terminal principal
- `/pos/terminal/new-sale` — Nueva venta

### Rutas Públicas
- `/m/[slug]` — Menú público por QR (+ tip flow: success/failure/pending)
- `/q/[public_id]` — Redirect QR API route
- `/r/[slug]` — Landing pública de reseñas + submit
- `/plantillas/importar-stock.xlsx` — Descarga de template Excel

---

## 8. Feature Modules Frontend (13)

| Módulo | Archivos principales | Propósito |
|--------|---------------------|-----------|
| `billing/` | api, hooks, types, components, data | Suscripciones, checkout, planes |
| `cash/` | api, hooks, components, types, utils | Caja POS, sesiones, pagos |
| `customers/` | api, hooks, components, types | CRM |
| `gestion/` | api, hooks, components, types | Gestión comercial central |
| `inventory-imports/` | api, hooks, types | Import masivo de stock |
| `invoices/` | api, hooks, types | Facturación |
| `menu/` | api, hooks, types | Menú QR |
| `orders/` | api, hooks, types | Pedidos restaurante |
| `pos/` | components, context, hooks, tests | Terminal POS |
| `reports/` | api, hooks, types, utils | Analytics y reportes |
| `reviews/` | api, product, types | QR de Reseñas (product.ts = central source of truth) |
| `resto-reports/` | api, hooks, types | Reportes restaurante |
| `tables/` | api, hooks, types, mock-data | Mesas |

---

## 9. Componentes Compartidos (14 categorías)

| Categoría | Componentes | Uso |
|-----------|------------|-----|
| `admin/` | admin-shell, data-table, filter-bar, pagination, stat-card, status-badge, etc. | Admin backoffice |
| `app/` | app-shell, page-header, engagement-settings, subscription-banner, toast, etc. | App principal |
| `auth/` | auth-form, login-form | Autenticación |
| `gestion/` | entitlement-gate, upgrade-prompt, plan-comparison, addon-purchase-dialog | Billing & gating |
| `invoicing/` | invoice-actions, pdf-download-button | Facturación |
| `layout/` | site-container | Wrapper de layout |
| `legal/` | legal-page-layout | Páginas legales |
| `marketing/` | product-landing (ProductHero, ProductPricing, ProductDemo, etc.), sections | Landing pages |
| `navigation/` | sidebar, topbar, marketing-nav, marketing-footer, module-tabs | Navegación |
| `orders/` | menu-picker, order-checkout-drawer, table-map-embed | Flujo de pedidos |
| `public-menu/` | brand-header, category-section, item-row, menu-layout | Menú público QR |
| `reports/` | charts, insights, metrics, utils | Visualización analytics |
| `ui/` | button, card, modal, drawer, sheet, tabs, badge, alert, switch, etc. | Primitivas UI (shadcn/ui + Radix) |

---

## 10. Modelo de Negocio

### Planes — Gestión Comercial (4 tiers)

| Plan | Precio | Sucursales | Seats | Features principales |
|------|--------|-----------|-------|---------------------|
| **START** | $99/mes | 1 | 1-2 | Productos, inventario básico, ventas, dashboard |
| **PRO** | $299/mes | ≤3 | 5-10 | + Clientes, caja, facturación, tesorería, reportes |
| **BUSINESS** | $499/mes | 5+ | 20+ | + Multi-sucursal, reportes consolidados, respaldo impositivo |
| **ENTERPRISE** | Custom | Ilimitado | Ilimitado | Todo + configuración custom |

### Planes — Carta Online (3 tiers)
- **Básico:** Sin imágenes
- **Visual:** Con imágenes de productos
- **Marca:** Dominio custom + branding completo

### Planes — QR de Reseñas (2 tiers)
- **QR Reseñas ($25.000/mes):** QR, recepción, redirección a Google, feedback interno, gestión de estados
- **Reseñas Pro ($35.000/mes):** Todo anterior + filtro inteligente, analytics avanzadas, métricas de conversión

### Add-ons
- Gestión de Clientes: $20/mes
- Facturación Electrónica: $150/mes
- Sucursal adicional: $50/mes
- Usuario adicional: $5/mes

### Entitlements (24+ feature flags)
Controlados por plan. Verificados vía `PricingService` + `session.features`.
- **Core:** products, inventory_basic, sales_basic, dashboard_basic, settings_basic
- **Pro:** customers, cash, quotes, reports, export, treasury, inventory_advanced, sales_advanced, audit, rbac_full
- **Business:** invoices, multi_branch, transfers, consolidated_reports, tax_backup
- **Enterprise:** todo habilitado

### Rollout Flags (4)
- `NEW_ONBOARDING` — Nuevo flujo de onboarding
- `OWNER_MGMT_V2` — Gestión de acceso v2
- `SUBSCRIPTION_ENFORCEMENT` — Enforcement de suscripción
- `EMAIL_VERIFICATION` — Verificación de email requerida

---

## 11. Autenticación y Seguridad

| Aspecto | Implementación |
|---------|---------------|
| **Auth** | JWT (SimpleJWT) en cookies httpOnly |
| **RBAC** | 10 roles: owner, admin, manager, cashier, staff, viewer, kitchen, salon, analyst, contador |
| **Entitlements** | Feature gating por plan vía Membership + RolePermissionOverride |
| **Audit Trail** | 70+ action types en AccessAuditLog |
| **MFA** | TOTP (pyotp) para admin backoffice |
| **POS Auth** | PIN-based (EmployeeProfile) + JWT session |
| **Email Verification** | Requerida (controlada por rollout flag) |

### Flujo de permisos
```
User tiene permiso X en Recurso Y si:
  1. business.subscription.entitlements incluye el feature
  2. user.role tiene permission_code para ese feature
  3. RBAC middleware valida ambos
```

---

## 12. Infraestructura (AWS — Terraform)

| Recurso | Config |
|---------|--------|
| **VPC** | Red privada con subnets públicas/privadas |
| **RDS** | PostgreSQL 16 (multi-AZ production) |
| **ElastiCache** | Redis 7 (cache + Celery broker) |
| **WAF** | Web Application Firewall |
| **Secrets Manager** | Credenciales seguras |
| **Domains** | Configuración DNS + SSL |

### Variables de entorno clave
- **DB:** POSTGRES_DB/USER/PASSWORD/HOST/PORT
- **Auth:** DJANGO_SECRET_KEY, ACCESS_TOKEN_LIFETIME, COOKIE_DOMAIN/SECURE/SAMESITE
- **MercadoPago:** MP_ACCESS_TOKEN, MP_WEBHOOK_SECRET, MP_CLIENT_ID/SECRET
- **CORS:** CORS_ALLOWED_ORIGINS
- **Email:** EMAIL_BACKEND, EMAIL_HOST, DEFAULT_FROM_EMAIL
- **URLs:** FRONTEND_URL, API_URL_INTERNAL, PUBLIC_MENU_BASE_URL
- **Feature flags:** ROLLOUT_* env vars

---

## 13. Testing

### Backend (53 archivos de test)

| App | Tests | Suites clave |
|-----|-------|-------------|
| treasury | 4 | treasury, payment, expense_document, document_pipeline |
| sales | 3 | sales_api, quote_pdf, pos_sales |
| cash | 3 | pos_cash, cash_services, backfill_phase3 |
| orders | 3 | order_drafts, order_close, order_checkout |
| resto | 2 | table_configuration, reports |
| inventory | 1 | replenishment |
| catalog | 1 | rbac |
| reviews | 1 | reviews (61 tests passing) |
| reports | 1 | reports_api |
| menu | 1 | qr_reviews |
| customers | 1 | tests (single file) |
| tax_backup | 1 | tests (single file, 103 tests) |
| accounts | — | Incluido en framework tests |

### Frontend (15 archivos de test)
- Vitest + React Testing Library
- Coverage principal: POS, navigation, app components

---

## 14. Features Implementadas — Estado Actual

### ✅ Gestión Comercial (100%)
- Productos con categorías, precios, imágenes, barcode
- Inventario: stock, movimientos, valuación, import/export Excel
- Ventas: simples y avanzadas (descuentos, notas, métodos de pago)
- Clientes: CRM con historial de compras, condición fiscal
- Caja: sesiones, pagos multi-método, movimientos, terminales
- Facturación: series unificadas, invoice lifecycle, PDF
- Presupuestos: workflow completo (draft → sent → accepted → converted) + PDF
- Tesorería: cuentas, ledger, gastos (fijos + ad-hoc), sueldos
- Reposición de stock: compras → movimiento → transacción → perfil fiscal
- Reportes: ventas, productos, caja, pagos, stock alerts
- Dashboard: KPIs, prioridades del día
- Valuación de stock: costo, precio, margen, ganancia potencial

### ✅ Carta Online / Menú QR (100%)
- Categorías y items con imágenes
- Branding personalizable (colores, tipografía, logo)
- Slug público `/m/[slug]`
- QR code generation
- Tips via MercadoPago (link, QR image, OAuth)
- 3 planes tiered (Básico, Visual, Marca)

### ✅ Restaurante Inteligente (100%)
- Pedidos: salón/delivery, items, estados de cocina
- Kitchen Display System (KDS): workflow item-level con timestamps
- Order Drafts: carrito editable → pedido
- Mesas: layout grid, placement, live state
- Checkout y pagos
- Integración con menú QR y sistema de caja

### ✅ QR de Reseñas (100%)
- Landing pública por slug (`/r/[slug]`)
- Filtro inteligente: ≥4★ → Google, ≤3★ → feedback privado
- Rating 1–5★ + comentario + contacto opcional
- Estados: NEW → READ → CONTACTED → RESOLVED
- Analytics: visitas, distribución de rating, conversión
- Dashboard con KPIs y tendencias
- QR descargable + link compartible
- 2 planes con pricing component compartido (ProductPricing)
- Configuración: Google Place ID, threshold, mensajes custom

### ✅ Admin / Plataforma (100%)
- Blog CMS: posts, drafts, scheduling, categorías, SEO
- MFA obligatorio para admin
- Audit trail completo
- Gestión de cuentas de clientes
- Tickets de soporte multi-tier
- Gestión de suscripciones
- Reportes de plataforma

### ✅ POS Terminal (100%)
- Login por PIN (EmployeeProfile)
- Terminal de venta
- Integración con caja y sesiones
- Búsqueda de productos con ranking
- Cierre de caja operativo

### ✅ Respaldo Impositivo (100%)
- Perfil fiscal dual-origin (Expense + FixedExpensePeriod)
- Pipeline de documentos: upload → OCR → parsing → validación
- Detección de duplicados
- Alertas automáticas
- Estados fiscales granulares
- 103 tests passing

### ✅ Checkout / Suscripciones (100%)
- Onboarding wizard (servicio → plan → checkout)
- MercadoPago integration
- Webhook processing con audit
- Estado de suscripción con UX (banner, bypass, redirects)

---

## 15. Componente Compartido ProductPricing

Componente genérico de pricing utilizado por las 3 verticales con planes:

```typescript
// @/components/marketing/product-landing/product-pricing.tsx
type PricingCardData = {
    name: string;
    tagline: string;
    price: string;
    period?: string;
    highlights: string[];
    ctaHref: string;
    ctaLabel: string;
    featured?: boolean;
};
```

**Usado por:**
- Gestión Comercial (gestion-pricing-section.tsx)
- Carta Online (carta-pricing-section.tsx)
- QR de Reseñas (resenas-pricing-section.tsx + app/resenas/page.tsx)

**Estilo visual consistente:**
- `rounded-2xl border p-6`, featured = `border-brand-200 bg-brand-50/30 shadow-lg ring-1 ring-brand-100`
- Check icons en `text-brand-500`
- Button CTA con `variant={featured ? 'default' : 'outline'}`

---

## 16. Cuentas Demo

| Plan | Email | Password |
|------|-------|----------|
| START | gc.basic@demo.local | Demo12345! |
| PRO | gc.pro@demo.local | Demo12345! |
| BUSINESS | gc.max@demo.local | Demo12345! |

Comando: `python manage.py seed_gestion_comercial_demo_accounts` (DEBUG only)

---

## 17. Gaps Conocidos / Trabajo Diferido

| Item | Estado | Notas |
|------|--------|-------|
| WYSIWYG Blog Editor | ⏳ Pendiente | Content blocks en JSON, sin editor visual |
| Almacenamiento S3 | ⏳ Pendiente | Imágenes almacenadas localmente |
| Multi-idioma (i18n) | ⏳ Pendiente | Solo español |
| App Móvil | ⏳ Pendiente | Solo web responsive |
| Custom Domains (QR Marca) | ⏳ Pendiente | Plan QR Marca sin dominio custom implementado |
| Consolidación multi-branch | 🔄 Parcial | Modelo listo, reportes consolidados en progreso |
| Legacy model cleanup | ⏳ Pendiente | InvoiceSeries, CommericalSettings, ExpenseTemplate deprecated |
| Advanced analytics | 🔄 Parcial | KPIs básicos listos, drilldowns avanzados pendientes |
| Webhooks externos | ⏳ Pendiente | Solo MercadoPago, sin webhooks genéricos |
| Dual CashSession track | ⏳ Pendiente | `register` + `terminal` coexisten (Phase 2A) |

---

## 18. Documentación Existente

El directorio `docs/` contiene 50+ archivos de auditoría e implementación organizados por módulo:

### Core
- `README.md` — Setup local y cuentas demo
- `ROLES_ACCESS_MODULE.md` — Sistema de roles
- `AUDIT_ROLES_ACCESS_COMPLETE.md` — Auditoría RBAC (72/100)
- `IMPL_SPEC_ACCESS_REMEDIATION.md` — Spec de remediación de acceso
- `IMPL_PLAN_ACCESS_REMEDIATION.md` — Plan de implementación (4 PRs)

### Gestión Comercial
- `FEATURES_GESTION_COMERCIAL.md` — Features completas
- `GESTION_COMERCIAL_PLANS.md` — Planes START/PRO/BUSINESS
- `GESTION_COMERCIAL_ENTITLEMENTS.md` — 24+ feature flags
- `BUSINESS_SETTINGS_AUDIT.md` — Sistema de configuración
- `CATEGORIES_IMPLEMENTATION.md` — Categorías de productos
- `SORTING_IMPLEMENTATION.md` — Ordenamiento en listas
- `PRODUCTOS_CATEGORIAS_TABS_IMPLEMENTATION.md` — UI de productos

### Finanzas
- `FINANCE_GASTOS_AUDIT.md` — Módulo de tesorería
- `GASTOS_MODULE_AUDIT.md` — Módulo de gastos
- `SPRINT1_PAYMENT_DESIGN.md` — Diseño de pagos sprint 1
- `SPRINT3_GASTOS_PIPELINE_AUDIT.md` — Pipeline de gastos
- `AUDITORIA_MIRUBRO_GASTOS_SYNC.md` — Sync de gastos

### Stock & Compras
- `STOCK_REPLENISHMENT_MVP.md` — Reposición de stock
- `STOCK_IMPORT_TEMPLATE_GUIDE.md` — Guía de import
- `PURCHASES_REPLENISHMENT_AUDIT.md` — Auditoría compras

### Impositivo
- `TAX_BACKUP_HANDOFF.md` — Handoff respaldo impositivo
- `PHASE4_FRONTEND_DESIGN_TAX_BACKUP.md` — Diseño frontend

### Menú QR
- `QR_MENU_PLANS_IMPLEMENTATION.md` — Planes del menú QR
- `MENU_QR_TIPS_AND_REVIEWS.md` — Tips y reseñas
- `AUDIT_QR_MENU_VS_RESTAURANT.md` — Auditoría QR vs Restaurante

### QR Reseñas
- `AUDIT_QR_RESENAS_STANDALONE.md` — Auditoría reseñas standalone
- `QR_RESENAS_FASE1_IMPLEMENTATION_PLAN.md` — Plan de implementación fase 1

### Admin & Blog
- `PHASE5_BLOG_CMS_DELIVERY.md` — Entrega blog CMS
- `ADMIN_LOGIN_HARDENING.md` — Hardening del login admin
- `security/admin-login-hardening-aws.md` — Hardening AWS

### POS & Caja
- `POS_CASH_IMPLEMENTATION_SUMMARY.md` — Resumen implementación POS
- `POS_CASH_FRONTEND_HANDOFF.md` — Handoff frontend POS

### Billing
- `PRICING_GESTION_COMERCIAL_IMPLEMENTATION.md` — Pricing GC
- `PLAN_SYSTEM_FIXES.md` — Fixes del sistema de planes
- `STAGING_BILLING_VALIDATION.md` — Validación billing staging
- `FIX_ENABLED_SERVICES_DEMO_ACCOUNTS.md` — Fix demos
- `DEMO_ACCOUNTS_GESTION_COMERCIAL.md` — Cuentas demo GC

### Infra & Layout
- `MERCADOPAGO_DEV_DOCKER.md` — MercadoPago en Docker
- `LAYOUT_SIDEBAR_REFACTOR.md` — Refactor sidebar
- `HEADER_FIX_SUMMARY.md` — Fix header

### Auditorías Generales
- `AUDITORIA_TECNICA_COMPLETA.md` — Auditoría técnica completa
- `AUDITORIA_MATRIZ_EVIDENCIA.md` — Matriz de evidencia
- `PRIORIDADES_DIA_AUDIT.md` — Prioridades del día
