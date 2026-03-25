# Auditoría General — Mirubro Digital + Módulo Gastos

> **Fecha:** 2026-03-24
> **Propósito:** Documento de sincronización para retomar contexto completo del proyecto y el módulo de Gastos.

---

## 1. ¿Qué es Mirubro Digital?

**Mirubro Digital** es una plataforma SaaS multi-tenant para PyMEs de Latinoamérica. Opera como monorepo con 3 verticales de servicio:

| Servicio | Descripción | Target |
|----------|-------------|--------|
| **Gestión Comercial** | ERP liviano: productos, inventario, ventas, facturación, tesorería, RRHH | Comercios, almacenes, distribuidoras |
| **Menú QR** | Carta digital accesible por QR, con branding | Restaurantes, bares, cafés |
| **Restaurante Inteligente** | Operación completa: mesas, cocina, pedidos, delivery | Restaurantes full-service |

Cada negocio (Business) elige un servicio y un plan. Los planes determinan qué features se desbloquean.

---

## 2. Stack Técnico

| Capa | Tecnología |
|------|-----------|
| **Frontend** | Next.js 16 (App Router) + React 18 + TypeScript + TailwindCSS + shadcn/ui |
| **State Management** | TanStack Query (React Query) para server state |
| **Backend** | Django 5.0 + Django REST Framework |
| **Base de Datos** | PostgreSQL 16 |
| **Async** | Celery + Redis (workers + beat scheduler) |
| **Auth** | JWT en httpOnly cookies (SimpleJWT) |
| **Infraestructura** | Docker Compose (local), Terraform + AWS (producción) |
| **Monorepo** | npm workspaces: `apps/web`, `services/api`, `packages/*` |

---

## 3. Estructura del Monorepo

```
mirubrodigital/
├── apps/web/                     # Frontend Next.js
│   └── src/
│       ├── app/                  # App Router (páginas)
│       │   ├── (auth)/           # Login, registro
│       │   ├── (marketing)/      # Landing, pricing público
│       │   ├── admin/            # Administración de plataforma
│       │   └── app/gestion/      # ★ Módulo Gestión Comercial
│       │       ├── dashboard/
│       │       ├── productos/
│       │       ├── stock/
│       │       ├── ventas/
│       │       ├── clientes/
│       │       ├── facturas/
│       │       ├── finanzas/     # ★ Tesorería (incluye Gastos)
│       │       ├── reportes/
│       │       └── configuracion/
│       ├── features/             # Hooks + API clients por módulo
│       ├── components/           # Componentes reutilizables
│       └── lib/api/              # Clientes API específicos (tax-backup, etc.)
│
├── services/api/                 # Backend Django
│   └── src/apps/                 # 17 Django apps:
│       ├── accounts/             # Usuarios, RBAC, audit trail
│       ├── billing/              # Suscripciones, bundles, entitlements
│       ├── business/             # Entidad Business, settings, branding
│       ├── catalog/              # Productos, categorías
│       ├── inventory/            # Stock, movimientos, valuación
│       ├── sales/                # Ventas, cotizaciones
│       ├── customers/            # CRM
│       ├── cash/                 # Caja registradora, sesiones
│       ├── invoices/             # Facturación electrónica
│       ├── treasury/             # ★ Tesorería: cuentas, gastos, nómina
│       ├── tax_backup/           # ★ Respaldo Impositivo
│       ├── orders/               # Pedidos (restaurante)
│       ├── menu/                 # Menú QR
│       ├── resto/                # Restaurante (mesas, layout)
│       ├── reports/              # Analytics
│       ├── blog/                 # CMS público
│       └── ...
│
├── packages/                     # Paquetes compartidos (ESLint, Prettier, UI)
├── infra/                        # Docker Compose + Terraform
└── docs/                         # Documentación técnica
```

---

## 4. Sistema de Planes y Entitlements

### 4.1 Planes de Gestión Comercial

| Plan | Precio | Sucursales | Usuarios |
|------|--------|-----------|----------|
| **Start** | $99/mes | 1 | 2 |
| **Pro** | $299/mes | 1-3 | 10 |
| **Business** | $499/mes | 5+ | 20+ |
| **Enterprise** | Custom | ∞ | ∞ |

### 4.2 Entitlements por Plan

Los entitlements son feature flags que determinan acceso. Cada plan hereda todo lo anterior:

**START (6 entitlements):**
- `gestion.products`, `gestion.inventory_basic`, `gestion.sales_basic`, `gestion.orders`, `gestion.dashboard_basic`, `gestion.settings_basic`

**PRO (18 entitlements = START + 12):**
- +`gestion.customers`, `gestion.cash`, `gestion.quotes`, `gestion.reports`, `gestion.export`, `gestion.treasury`, `gestion.dashboard_finance`, `gestion.inventory_advanced`, `gestion.sales_advanced`, `gestion.rbac_full`, `gestion.audit`, `gestion.invoices`

**BUSINESS (22 entitlements = PRO + 4):**
- +`gestion.multi_branch`, `gestion.transfers`, `gestion.consolidated_reports`, `gestion.tax_backup`

**ENTERPRISE = BUSINESS (mismo set)**

### 4.3 Sistema de Suscripciones (Dual)

Coexisten 2 sistemas durante la transición:

1. **Legacy:** `business.Subscription` con campo `plan` (string: start/pro/business) → resuelve entitlements via `entitlements.py`
2. **Moderno:** `billing.Bundle` + `billing.Module` + `billing.Subscription` → con `PricingService`

Ambos están activos. El sistema usa resolución V2-first: intenta billing moderno, cae a legacy si no existe.

### 4.4 Cómo Funciona el Feature Gating (Frontend)

```
useEntitlements() hook 
  → GET /api/v1/entitlements/
  → Backend resuelve subscription → calcula entitlements del plan + addons
  → Retorna: { entitlements: string[], plan: {...}, addons: [...] }

<EntitlementGate entitlement="gestion.tax_backup" plan="Gestión Business">
  → Si hasEntitlement() es true → muestra children
  → Si es false → muestra UpgradeBlock con botón "Actualizar a {plan}"
</EntitlementGate>
```

### 4.5 Control de Acceso (RBAC + Entitlements)

Un usuario puede realizar una acción si:
1. El **Business** tiene el entitlement (determinado por su plan/suscripción)
2. El **Usuario** tiene el permiso de su rol (owner > admin > manager > cashier > contador > staff > viewer)

Roles disponibles: `owner`, `admin`, `manager`, `cashier`, `contador`, `staff`, `viewer`, `kitchen`, `salon`

---

## 5. Módulo Finanzas → Gastos (Estado Detallado)

### 5.1 Ubicación y Arquitectura

**Frontend:** `apps/web/src/app/app/gestion/finanzas/gastos/`
**Backend:** `services/api/src/apps/treasury/` + `services/api/src/apps/tax_backup/`

La sección Gastos tiene **4 tabs** en el frontend:

| Tab | Componente | Backend App | Entitlement |
|-----|-----------|-------------|-------------|
| **Gastos Fijos** | `FixedExpensesClient` | treasury | `gestion.treasury` (Plan PRO+) |
| **Gastos Puntuales** | `PunctualExpensesClient` | treasury | `gestion.treasury` (Plan PRO+) |
| **Reposiciones de Stock** | `ReplenishmentExpensesClient` | treasury | `gestion.treasury` (Plan PRO+) |
| **Respaldo Impositivo** | `TaxBackupClient` | tax_backup | `gestion.tax_backup` (Plan BUSINESS+) |

El tab selector está en `gastos-client.tsx`. Cada tab es un componente independiente. La URL usa query param `?tab=fijos|puntuales|reposiciones|respaldo`.

---

### 5.2 Tab: Gastos Fijos

**Qué es:** Gastos recurrentes mensuales que se repiten (alquiler, internet, seguros, etc.)

#### Modelos Backend (treasury app)

**FixedExpense** — El gasto fijo como plantilla:
```
- id, business (FK)
- name: string                    # "Alquiler local", "Internet Fibertel"
- category: FK(TransactionCategory, nullable)
- default_amount: Decimal         # Monto por defecto mensual
- due_day: int (1-28)             # Día de vencimiento cada mes
- frequency: string               # "monthly" (por ahora solo mensual)
- is_active: bool
- Constraint: (business, name) único
```

**FixedExpensePeriod** — Instancia mensual del gasto:
```
- id, fixed_expense (FK)
- period: Date (YYYY-MM-01)       # Mes al que corresponde
- amount: Decimal                 # Puede diferir del default (override)
- status: PENDING | PAID | SKIPPED
- due_date: Date                  # Calculada: period.month + due_day
- paid_at: DateTime (nullable)
- paid_account: FK(Account, nullable)
- payment_transaction: FK(Transaction, nullable)
- notes: text (nullable)
- Constraint: (fixed_expense, period) único
```

#### Endpoints

| Método | URL | Descripción |
|--------|-----|-------------|
| GET/POST | `/api/v1/treasury/fixed-expenses/` | CRUD de gastos fijos |
| GET/PATCH/DELETE | `/api/v1/treasury/fixed-expenses/{id}/` | Detalle |
| GET | `/api/v1/treasury/fixed-expenses/{id}/periods/` | Períodos del gasto |
| POST | `/api/v1/treasury/fixed-expenses/{id}/ensure-current/` | Asegurar que exista período actual |
| POST | `/api/v1/treasury/fixed-expenses/{id}/generate-periods/` | Generar N períodos futuros |
| POST | `/api/v1/treasury/fixed-expenses/ensure-all-current/` | Asegurar período actual en todos |
| POST | `/api/v1/treasury/fixed-expense-periods/{id}/pay/` | Pagar un período |
| POST | `/api/v1/treasury/fixed-expense-periods/{id}/skip/` | Saltar un período |

#### Frontend (fixed-expenses-client.tsx)

- **Layout:** Panel izquierdo (lista de gastos fijos) + Panel derecho (detalle del seleccionado)
- **Detalle muestra:** estado del mes actual + historial de 12 meses
- **Acciones:** Crear gasto fijo, Pagar período, Saltar período, Editar monto
- **Modals:** `FixedExpenseFormModal` (crear/editar), `PayPeriodModal` (pagar con selector de cuenta + monto override)

#### Flujo de Pago

```
Usuario selecciona gasto fijo → ve estado del mes actual "Pendiente"
→ Click "Pagar" → Modal con selector de cuenta + monto
→ POST /api/v1/treasury/fixed-expense-periods/{id}/pay/
→ Backend crea Transaction(direction=OUT, reference_type='fixed_expense_period')
→ Actualiza período: status=PAID, paid_at, paid_account, payment_transaction
→ Transaction aparece en el Ledger (Movimientos)
→ Saldo de la cuenta se actualiza
```

---

### 5.3 Tab: Gastos Puntuales

**Qué es:** Gastos únicos, no recurrentes (reparaciones, compras especiales, servicios puntuales)

#### Modelo Backend (treasury app)

**Expense** — Un gasto puntual:
```
- id, business (FK)
- name: string                    # "Reparación aire acondicionado"
- category: FK(TransactionCategory, nullable)
- amount: Decimal
- due_date: Date                  # Fecha de vencimiento
- status: PENDING | PAID | CANCELLED
- paid_at: DateTime (nullable)
- paid_account: FK(Account, nullable)
- payment_transaction: FK(Transaction, nullable)
- attachment: file (nullable)
- notes: text (nullable)
- source_type: string (nullable)  # 'stock_replenishment' si es auto-generado
- source_id: string (nullable)    # ID de la reposición origen
- is_auto_generated: bool         # True si viene de reposición de stock
- template: FK(ExpenseTemplate, nullable, DEPRECATED)
```

#### Endpoints

| Método | URL | Descripción |
|--------|-----|-------------|
| GET | `/api/v1/treasury/expenses/` | Lista (filtrable por status, category, date_from, date_to, source_type) |
| POST | `/api/v1/treasury/expenses/` | Crear gasto puntual |
| GET/PATCH | `/api/v1/treasury/expenses/{id}/` | Detalle |
| POST | `/api/v1/treasury/expenses/{id}/pay/` | Pagar gasto |

#### Frontend (expenses-client.tsx)

- **Layout:** Grid de tarjetas (3 columnas desktop)
- **Sub-tabs:** Pendientes | Pagados
- **Cada tarjeta:** Nombre, categoría (badge), monto, fecha vencimiento, indicador de color por proximidad
- **Acciones:** Crear gasto, Pagar gasto
- **Modals:** `ExpenseFormModal` (nombre, categoría, monto, fecha), `PayExpenseModal` (selector de cuenta)

#### Flujo de Pago

```
Usuario ve tarjeta de gasto pendiente → Click "Registrar Pago"
→ Modal con selector de cuenta
→ POST /api/v1/treasury/expenses/{id}/pay/
→ Backend crea Transaction(direction=OUT, reference_type='expense')
→ Actualiza: status=PAID, paid_at, paid_account, payment_transaction
→ Tarjeta se mueve a sub-tab "Pagados"
→ Transaction en Ledger, saldo de cuenta actualizado
```

---

### 5.4 Tab: Reposiciones de Stock

**Qué es:** Gastos auto-generados por el módulo de inventario cuando se hacen reposiciones de stock.

- **Solo lectura** — no se crean ni pagan desde esta tab
- Son `Expense` con `source_type='stock_replenishment'` e `is_auto_generated=True`
- Badge violeta "Auto-generado"
- Links a: detalle de reposición + ledger de transacciones

---

### 5.5 Tab: Respaldo Impositivo (Tax Backup)

**Qué es:** Sistema de respaldo fiscal para gastos. Permite vincular comprobantes fiscales, gestionar el estado impositivo y preparar la documentación para el contador.

**Entitlement requerido:** `gestion.tax_backup` (solo Plan Business+)

#### Modelos Backend (tax_backup app — 7 modelos)

**ExpenseFiscalProfile** (1:1 con treasury.Expense):
```
- id, expense (OneToOne a treasury.Expense)
- business (FK)
- allocation_type: business | mixed | personal
- tax_status: registrado | respaldado | potencialmente_deducible | a_revisar | no_respaldado_fiscalmente
- amount_net: Decimal (nullable)
- amount_vat: Decimal (nullable)
- is_capital_asset: bool
- review_reason: text (nullable)
- created_by (FK User)
- Índices: (business, tax_status), (business, allocation_type), (business, created_at)
```

**FiscalDocument** (FK a ExpenseFiscalProfile):
```
- fiscal_profile (FK)
- file: upload (tax_backup/docs/{business_id}/{YYYY}/{MM}/{filename})
- document_type: factura | recibo | ticket | nota_credito | nota_debito | otro
- issuer_name, issuer_tax_id, buyer_name, buyer_tax_id
- point_of_sale, invoice_number, issue_date
- subtotal, vat, total, currency
- is_fiscal_document: bool
- parse_status: manual | pending | parsed | failed
```

**ExpensePaymentDetail** (FK a ExpenseFiscalProfile):
```
- fiscal_profile (FK)
- payment_method: cash | transfer | card | mercadopago | check | other
- payment_date, amount, reference, proof_file
```

**TaxStatusLog** (Auditoría de cambios de estado):
```
- fiscal_profile (FK)
- previous_status, new_status, rule_code, note, created_at
```

**RecurringServiceProfile** (1:1 con treasury.FixedExpense):
```
- fixed_expense (OneToOne)
- business (FK)
- provider_name, provider_tax_id
- needs_monthly_invoice: bool
- expected_document_type: string
```

**ServicePeriodAlert** (Alertas de servicios recurrentes):
```
- service_profile (FK), fixed_expense_period (FK)
- alert_type: missing_invoice | incomplete_data
- status: open | resolved | dismissed
- Constraint: unique (service_profile, fixed_expense_period, alert_type)
```

**DuplicateFlag** (Detección de duplicados):
```
- fiscal_profile (FK), matched_profile (FK)
- match_type: provider_invoice_date_amount | exact_amount_date
- status: pending | confirmed_duplicate | dismissed
- Constraint: par normalizado (id menor primero) + no auto-referencia
```

#### Motor de Reglas (rules.py)

Cuando se sube un documento o pago, se ejecuta `evaluate_tax_status(profile)` con 6 reglas:

1. **RULE_PERSONAL**: Si `allocation_type == personal` → `no_respaldado_fiscalmente`
2. **RULE_NO_FISCAL_DOC**: Sin documentos fiscales → `no_respaldado_fiscalmente`
3. **RULE_BACKED**: Tiene factura válida → `respaldado`
4. **RULE_MIXED**: Asignación mixta → `potencialmente_deducible`
5. **RULE_CAPITAL_ASSET**: Es bien de uso → `potencialmente_deducible`
6. **RULE_AMOUNT_MISMATCH**: Monto documento ≠ monto gasto → `a_revisar`

#### Checklist de Cierre Mensual (checklist.py)

6 verificaciones para cierre fiscal mensual:
1. `all_profiles_backed` — Todos los perfiles con respaldo
2. `no_missing_documents` — Sin documentos faltantes
3. `all_payments_covered` — Todos los pagos cubiertos
4. `services_without_invoice` — Sin alertas abiertas en servicios
5. `no_pending_reviews` — Sin perfiles "a_revisar" pendientes
6. `no_open_duplicates` — Sin duplicados sin resolver

Score: X/6 (listo para cierre cuando 6/6)

#### Endpoints

| Método | URL | Descripción |
|--------|-----|-------------|
| GET/POST | `/api/v1/tax-backup/profiles/` | CRUD perfiles fiscales |
| GET/PATCH/DELETE | `/api/v1/tax-backup/profiles/{id}/` | Detalle perfil |
| GET/POST | `/api/v1/tax-backup/profiles/{id}/documents/` | Documentos del perfil |
| DELETE | `/api/v1/tax-backup/profiles/{id}/documents/{docId}/` | Eliminar documento |
| GET/POST | `/api/v1/tax-backup/profiles/{id}/payments/` | Pagos del perfil |
| GET | `/api/v1/tax-backup/profiles/{id}/status-log/` | Timeline de estados |
| POST | `/api/v1/tax-backup/profiles/{id}/re-evaluate/` | Re-evaluar reglas |
| GET | `/api/v1/tax-backup/profiles/summary/` | Dashboard de totales |
| GET | `/api/v1/tax-backup/profiles/export-csv/` | Exportar CSV |
| GET | `/api/v1/tax-backup/profiles/export-zip/` | Exportar ZIP con docs |
| GET | `/api/v1/tax-backup/profiles/monthly-report/` | Reporte mensual |
| GET | `/api/v1/tax-backup/profiles/checklist/` | Checklist de cierre |
| GET/POST | `/api/v1/tax-backup/services/` | Perfiles de servicios recurrentes |
| GET/PATCH | `/api/v1/tax-backup/alerts/` | Alertas de servicios |
| GET/PATCH | `/api/v1/tax-backup/duplicates/` | Flags de duplicados |

#### Frontend (12 componentes en `tax-backup/`)

| Componente | Función |
|-----------|---------|
| `tax-backup-client.tsx` | Orquestador: 4 sub-tabs (Perfiles, Servicios, Exportes, Checklist) |
| `tax-backup-dashboard.tsx` | 6 cards con counters por tax_status |
| `tax-backup-table.tsx` | Tabla paginada con filtros (status, allocation, search) |
| `tax-backup-detail.tsx` | Panel lateral: docs, pagos, timeline, duplicados |
| `create-profile-modal.tsx` | Modal: selector de gasto + allocation type + notas |
| `document-upload.tsx` | Form drag&drop: tipo doc, emisor, CUIT, nro factura, fecha, monto |
| `payment-form.tsx` | Form inline: método, fecha, monto, referencia, comprobante |
| `status-timeline.tsx` | Timeline vertical de cambios de estado |
| `tax-backup-services.tsx` | Lista de perfiles de servicios recurrentes + alertas |
| `tax-backup-exports.tsx` | Selector de período + botones CSV/ZIP |
| `tax-backup-checklist.tsx` | Checklist con 6 items + score |
| `constants.ts` | Colores por status, opciones de tipo documento, disclaimer legal |

#### Tests

103/103 PASS:
- `tests.py` (25): reglas, modelos, integración
- `test_exports.py` (36): CSV, ZIP, parsing de períodos
- `test_checklist.py` (24): 6 reglas de checklist
- `test_permissions.py` (18): roles, acceso por permisos

---

## 6. Relación entre los Modelos de Gastos

```
treasury.FixedExpense ─────── 1:N ──→ treasury.FixedExpensePeriod
       │                                        │
       │ 1:1                                    │ 1:1
       ▼                                        ▼
tax_backup.RecurringServiceProfile    tax_backup.ServicePeriodAlert
                                                
treasury.Expense ─────── 1:1 ──→ tax_backup.ExpenseFiscalProfile
       │                                   │
       │                              ┌────┴──────┐──────────────────┐
       │                              │            │                  │
       ▼                              ▼            ▼                  ▼
treasury.Transaction         FiscalDocument  PaymentDetail    TaxStatusLog
(reference_type='expense')                                         │
                                                                   ▼
                                                           DuplicateFlag
```

**Puntos clave de vinculación:**
- `ExpenseFiscalProfile.expense` es OneToOne con `treasury.Expense` → Un gasto puntual tiene máximo un perfil fiscal
- `RecurringServiceProfile.fixed_expense` es OneToOne con `treasury.FixedExpense` → Un gasto fijo tiene máximo un perfil de servicio recurrente
- Cuando se paga un Expense o FixedExpensePeriod, se crea un `Transaction` en el ledger
- El Tax Backup NO crea sus propias transacciones — solo documenta/clasifica gastos existentes

---

## 7. Inconsistencias Detectadas y Corregidas (2026-03-24)

### 7.1 ❌ Endpoint entitlements — URL incorrecta (CORREGIDO)

**Problema:** El frontend llamaba a `/api/v1/business/entitlements/` pero la ruta real de Django era `/api/v1/entitlements/` (la app business se monta en `api/v1/` sin prefijo `business/`).

**Resultado:** 404 en todas las llamadas → `useEntitlements()` siempre retornaba vacío → `EntitlementGate` bloqueaba todo como si no tuviera plan.

**Fix:** `apps/web/src/features/gestion/api.ts` — Cambiado de `/api/v1/business/entitlements/` a `/api/v1/entitlements/`

### 7.2 ❌ EntitlementGate — Plan incorrecto en label (CORREGIDO)

**Problema:** En `gastos-client.tsx`, el `EntitlementGate` mostraba `plan="Gestión Pro"` para Respaldo Impositivo, pero el entitlement `gestion.tax_backup` requiere plan **Business**, no Pro.

**Resultado:** Un usuario con plan Pro veía "Actualizar a Gestión Pro" (su propio plan) — confuso e incorrecto.

**Fix:** Cambiado a `plan="Gestión Business"`.

### 7.3 ❌ Entitlements — tax_backup faltante en enterprise y plus (CORREGIDO)

**Problema:** En `entitlements.py`, los planes `enterprise` y `plus` (legacy) no incluían `gestion.tax_backup`, a pesar de que enterprise debería tener todo lo de business, y plus se mapea a business.

**Fix:** Agregado `gestion.tax_backup` a ambos planes.

### 7.4 ⚠️ Nota: Respaldo Impositivo solo cubre Gastos Puntuales

El `ExpenseFiscalProfile` tiene un OneToOne con `treasury.Expense` (gastos puntuales), no con `FixedExpensePeriod`. Esto significa que actualmente **no se puede crear un perfil fiscal directamente para un período de gasto fijo**.

Los gastos fijos se cubren parcialmente a través de `RecurringServiceProfile` (perfil de servicio recurrente que monitorea facturas mensuales del proveedor), pero no tienen el mismo nivel de detalle que un `ExpenseFiscalProfile`.

**Decisión pendiente:** ¿Se necesita poder crear perfiles fiscales para períodos de gastos fijos individuales? Esto requeriría:
- Crear una FK alternativa en `ExpenseFiscalProfile` a `FixedExpensePeriod`
- O generar `Expense` "shadow" para cada período pagado de gasto fijo (vía signal)

---

## 8. Cuentas de Demo Disponibles

### Gestión Comercial (3 cuentas con planes escalonados)

| Email | Password | Plan | Módulos |
|-------|----------|------|---------|
| `gc.basic@demo.local` | `Demo12345!` | Start ($99/mes) | 6 |
| `gc.pro@demo.local` | `Demo12345!` | Pro ($299/mes) | 16 |
| `gc.max@demo.local` | `Demo12345!` | Business ($499/mes) | 20 |

**Comando:** `docker compose exec api python manage.py seed_gestion_comercial_demo_accounts`

### Negocios con Roles (seed_demo)

**Manzana (Gestión Comercial, PRO):**
- `manzana.owner@mirubro.local` / `mirubro123` (owner)
- `manzana.manager@mirubro.local` / `mirubro123` (manager)
- `manzana.cashier@mirubro.local` / `mirubro123` (cashier)

**La Pizza (Restaurante, PLUS):**
- `lapizza.owner@mirubro.local` / `mirubro123` (owner)

---

## 9. Endpoints Clave (Resumen Rápido)

| Módulo | Base URL | Autenticación |
|--------|----------|---------------|
| Auth | `/api/v1/auth/` | Público (login, register) |
| Business | `/api/v1/` (sin prefijo) | JWT + Business membership |
| Entitlements | `/api/v1/entitlements/` | JWT + Business membership |
| Treasury | `/api/v1/treasury/` | JWT + entitlement `gestion.treasury` |
| Tax Backup | `/api/v1/tax-backup/` | JWT + entitlement `gestion.tax_backup` |
| Billing | `/api/v1/billing/` | JWT + Business membership |
| Catalog | `/api/v1/catalog/` | JWT + Business membership |
| Inventory | `/api/v1/inventory/` | JWT + Business membership |
| Sales | `/api/v1/sales/` | JWT + Business membership |
| Invoices | `/api/v1/invoices/` | JWT + Business membership |

**Swagger:** `http://localhost:8000/api/docs`
**Frontend:** `http://localhost:3000/entrar`
**Admin:** `http://localhost:8000/admin`

---

## 10. Para Retomar Desarrollo

### Docker Compose (levanta todo)
```bash
cd infra
docker compose up --build
```

### Migraciones
```bash
docker compose exec api python manage.py migrate
```

### Seeds
```bash
docker compose exec api python manage.py seed_billing          # Planes y bundles
docker compose exec api python manage.py seed_demo             # Negocios con roles
docker compose exec api python manage.py seed_gestion_comercial_demo_accounts  # Cuentas por plan
```

### Tests Tax Backup
```bash
docker compose exec api python manage.py test apps.tax_backup --verbosity=2
```

---

## 11. Decisiones de Diseño Vigentes

1. **Gastos Fijos vs Puntuales son modelos separados**: `FixedExpense` + `FixedExpensePeriod` para recurrentes, `Expense` para únicos. No se fusionan.
2. **Transaction es el ledger unificado**: Todo pago (gasto, nómina, venta, transferencia) genera un `Transaction` con `reference_type` para trazabilidad.
3. **Tax Backup es app separada**: No está dentro de treasury. Tiene su propio Django app con modelos, views, tests. Se vincula via FK a modelos de treasury.
4. **EntitlementGate es frontend-only**: No hay middleware que bloquee APIs por entitlement (los ViewSets verifican permisos, no entitlements directamente — excepto Tax Backup que sí valida `gestion.tax_backup`).
5. **Señales auto-evalúan**: Al subir un `FiscalDocument` o `ExpensePaymentDetail`, un signal ejecuta las reglas automáticamente y loguea cambios de estado.
