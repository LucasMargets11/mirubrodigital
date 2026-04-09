# HelpModal — Gestión Comercial: Diseño Funcional V2

> **Estado:** Propuesta de diseño V2.1 — no implementado  
> **Fecha:** 2026-04-09  
> **Scope:** Exclusivamente Gestión Comercial (servicio `gestion`)  
> **Exclusiones:** Menú QR, QR de Reseñas, Restaurante Inteligente

---

## 1. Definición refinada de la tab "Configuración inicial"

### 1.1 Objetivo

Dejar el comercio **operativamente listo para funcionar desde el día 1**.  
No es un tour de features. No es una guía de uso diario. No es un recorrido por el sistema.

Es un checklist de **setup estructural**: lo que un comercio necesita tener configurado  
antes de que la operación diaria tenga sentido.

### 1.2 Qué problemas resuelve

| Problema | Cómo lo resuelve |
|----------|-----------------|
| El usuario activa su cuenta y no sabe por dónde empezar | Orden lineal claro: negocio → catálogo → stock → finanzas |
| El usuario carga ventas sin tener productos | El checklist prioriza catálogo antes que operación |
| El usuario emite facturas sin perfil fiscal | El paso fiscal aparece explícitamente y muestra si `is_complete=false` |
| El usuario no sabe qué features tiene según su plan | Los pasos locked muestran qué plan necesitan |
| El usuario no descubre la importación masiva | Es un CTA protagónico dentro del paso de catálogo |

### 1.3 Criterio de inclusión / exclusión

**ENTRA en "Configuración inicial":**

- Todo lo que es **setup de una sola vez** (o muy pocas veces)
- Todo lo que es **prerequisito** para que la operación diaria funcione bien
- Configuración de identidad, catálogo, estructura financiera, equipo

**NO ENTRA en "Configuración inicial":**

- Operaciones recurrentes (registrar ventas, cobrar, etc.)
- Análisis o consulta (reportes, dashboards)
- Funciones avanzadas que presuponen dominio del sistema (exportar, auditoría)
- Optimizaciones opcionales (presupuestos, alertas avanzadas)

### 1.4 Orden ideal de los pasos

La secuencia refleja dependencias reales:

```
1. IDENTIDAD + FISCAL → Datos del negocio y perfil fiscal (un solo paso)
2. IDENTIDAD          → Logo para documentos
3. CATÁLOGO           → Categorías de productos
4. CATÁLOGO           → Productos + importación masiva
5. INVENTARIO         → Stock inicial
6. FINANZAS (PRO)     → Cuentas de dinero (efectivo, banco, billeteras)
7. FINANZAS (PRO)     → Vincular caja con cuenta de efectivo
8. FISCAL (PRO)       → Series de documentos — prerequisito para facturar
9. EQUIPO (PRO)       → Invitar colaboradores y asignar roles
10. ESTRUCTURA (BUS)  → Configurar sucursales
```

**Dependencias:**
- Facturación requiere: perfil fiscal completo + series de documentos
- Stock requiere: al menos 1 producto
- Cuentas de dinero son prerequisito de: caja, gastos, reposiciones
- Sucursales es prerequisito de: reportes consolidados, transferencias

---

## 2. Matriz de pasos para Gestión Comercial

> **V2.1 — Cambio clave:** Los pasos "Datos del negocio" y "Perfil fiscal" se fusionan en un único paso.
> Ambos apuntan a la misma ruta (`/app/gestion/configuracion/negocio`, tab Perfil Fiscal).
> El usuario percibe un solo formulario con datos comerciales y fiscales mezclados — separarlos
> genera confusión ("¿no completé ya esto?"). El check unificado valida ambos en un solo pass.

### 2.1 Bloque: Tu negocio

| # | Paso | Descripción UX | Por qué es setup | Plan | Oblig. | Ruta | CTA | Completion Check | Confiabilidad |
|---|------|---------------|-------------------|------|--------|------|-----|-----------------|---------------|
| 1 | Completar los datos de tu negocio | Nombre, dirección, CUIT, condición ante IVA. Todo en un solo lugar. | Sin datos comerciales ni fiscales no hay contexto operativo ni posibilidad de facturar | ALL | **Obligatorio** | `/app/gestion/configuracion/negocio` (tab Perfil Fiscal) | Completar datos | **API**: `GET /api/v1/businesses/current/billing-profile/` → `is_complete === true AND vat_condition !== ''` | **ALTA** — `is_complete` valida `legal_name` + `tax_id` + `commercial_address`; se agrega `vat_condition` como condición extra |
| 2 | Subir tu logo para facturas y presupuestos | El logo aparece en el encabezado de facturas y presupuestos en PDF. | Identidad visual en documentos comerciales emitidos | ALL | Recomendado | `/app/gestion/configuracion/negocio` (tab Branding) | Subir logo | **API**: `GET /api/v1/businesses/current/branding/` → `logo_horizontal_url !== null OR logo_square_url !== null` | **ALTA** — campo directo, sin ambigüedad |

> **Nota sobre branding:** `BusinessBranding` (logo_horizontal, logo_square, accent_color) se consume
> **únicamente** en la generación de PDFs de facturas (`invoices/pdf.py`) y presupuestos (`sales/quote_pdf.py`).
> No aparece en el sidebar, header, app shell, recibos, emails ni en el menú público QR
> (que tiene su propio modelo `MenuBrandingSettings`). La descripción del paso refleja este alcance real.

> **Recomendación técnica (merge datos+fiscal):** Agregar `vat_condition != ''` al cálculo de `is_complete`
> en el backend, o crear un campo `profile_and_fiscal_ready` que valide los 4 campos
> (`legal_name`, `tax_id`, `commercial_address`, `vat_condition`). Esto evita tener 2 checks para 1 paso.

### 2.3 Bloque: Tu catálogo

| # | Paso | Descripción UX | Por qué es setup | Plan | Oblig. | Ruta | CTA | Completion Check | Confiabilidad |
|---|------|---------------|-------------------|------|--------|------|-----|-----------------|---------------|
| 3 | Crear categorías de productos | Organizá tu catálogo por rubros o familias antes de cargar productos. | Sin categorías, los productos quedan sin estructura | ALL | Recomendado | `/app/gestion/productos/categorias` | Crear categoría | **API**: `GET /api/v1/catalog/categories/` → `results.length >= 1` | **ALTA** — count directo |
| 4 | Cargar tu catálogo de productos | Tu catálogo es la base de ventas, stock y facturación. Podés importar un Excel o crear uno por uno. | Sin productos no hay ventas posibles | ALL | **Obligatorio** | `/app/gestion/productos` | Ver detalle §5 | **API**: `GET /api/v1/inventory/summary/` → `total_products >= 1` | **ALTA** — endpoint dedicado con count exacto |

### 2.4 Bloque: Tu inventario

| # | Paso | Descripción UX | Por qué es setup | Plan | Oblig. | Ruta | CTA | Completion Check | Confiabilidad |
|---|------|---------------|-------------------|------|--------|------|-----|-----------------|---------------|
| 5 | Definir el stock inicial | Cargá las cantidades actuales de cada producto para activar alertas y control de inventario. | Sin stock inicial, las alertas y el control de inventario no funcionan | ALL | Recomendado | `/app/gestion/stock` | Cargar stock | **Compuesto** (ver §2.9) | **MEDIA** — ver análisis abajo |

### 2.5 Bloque: Tus finanzas (PRO+)

| # | Paso | Descripción UX | Por qué es setup | Plan | Oblig. | Ruta | CTA | Completion Check | Confiabilidad |
|---|------|---------------|-------------------|------|--------|------|-----|-----------------|---------------|
| 6 | Crear tus cuentas de dinero | Definí dónde entra y sale la plata: efectivo, banco, Mercado Pago. | Sin cuentas, no se puede operar tesorería ni caja | PRO | **Obligatorio** (si PRO) | `/app/gestion/finanzas/cuentas` | Crear cuenta | **API**: `GET /api/v1/treasury/accounts/` → `results.length >= 1` | **ALTA** — count directo |
| 7 | Vincular caja con cuenta de efectivo | Asigná la cuenta de efectivo como destino de los cobros en caja. | Sin este vínculo, los cobros de caja no impactan en finanzas | PRO | Recomendado | `/app/gestion/finanzas/configuracion` | Configurar | **Compuesto**: `accounts.filter(type='cash').length >= 1 AND treasury_settings.default_cash_account !== null` | **MEDIA** — verifica estructura, no uso |

### 2.6 Bloque: Facturación (PRO+)

| # | Paso | Descripción UX | Por qué es setup | Plan | Oblig. | Ruta | CTA | Completion Check | Confiabilidad |
|---|------|---------------|-------------------|------|--------|------|-----|-----------------|---------------|
| 8 | Crear series de documentos | Definí punto de venta, tipo de letra (A/B/C) y numeración para tus comprobantes. | Sin series, no se pueden emitir facturas | PRO | Recomendado | `/app/gestion/configuracion/negocio` (tab Series) | Crear serie | **API**: `GET /api/v1/invoices/document-series/` → `results.length >= 1` con `is_default=true` | **ALTA** — count directo + filtro |

### 2.7 Bloque: Tu equipo (PRO+)

| # | Paso | Descripción UX | Por qué es setup | Plan | Oblig. | Ruta | CTA | Completion Check | Confiabilidad |
|---|------|---------------|-------------------|------|--------|------|-----|-----------------|---------------|
| 9 | Invitar a tu equipo | Agregá empleados y asigná roles para que cada uno acceda solo a lo que necesita. | Necesario si más de una persona opera el sistema | PRO | Opcional | `/app/settings/access` | Invitar | **API**: `GET /api/v1/businesses/current/memberships/` → `count >= 2` (owner + al menos 1 más) | **ALTA** — count directo (excluyendo owner) |

### 2.8 Bloque: Tu estructura (BUSINESS)

| # | Paso | Descripción UX | Por qué es setup | Plan | Oblig. | Ruta | CTA | Completion Check | Confiabilidad |
|---|------|---------------|-------------------|------|--------|------|-----|-----------------|---------------|
| 10 | Crear sucursales | Creá sucursales para manejar reportes consolidados y transferencias entre locales. | Sin sucursales, reportes consolidados y transferencias no tienen sentido | BUSINESS | Recomendado | `/app/owner` | Crear sucursal | **API**: `GET /api/v1/businesses/current/branches/` → `count >= 1` (excluyendo HQ) | **ALTA** — count directo |

### 2.9 Análisis de checks problemáticos

#### Stock inicial — confiabilidad MEDIA

**Problema:** ¿Cómo saber si el usuario "definió stock inicial" versus "hizo un movimiento cualquiera"?

**Señales disponibles:**
- `GET /api/v1/inventory/summary/` → `total_products` vs `out_of_stock`
  - Si `total_products > 0` y `out_of_stock === total_products` → nunca cargó stock
  - Si `out_of_stock < total_products` → al menos algunos productos tienen stock
- `GET /api/v1/inventory/imports/` → si hay al menos 1 job con `status=done` → usó la importación masiva

**Propuesta de check compuesto:**
```
stock_initialized =
  (inventory_summary.total_products > 0 AND inventory_summary.out_of_stock < inventory_summary.total_products)
  OR
  (imports con status=done >= 1)
```

**Confiabilidad:** MEDIA — un usuario podría tener productos con `stock_min=0` y `quantity=0` intencionalmente. No hay forma de distinguir "no cargué stock" de "mi stock es realmente 0". Aceptable para un indicador orientativo.

#### Vínculo caja-efectivo — confiabilidad MEDIA

**Problema:** El concepto de "configurar caja" en V2 era ambiguo — confundía setup con operación diaria.

**V2.1 redefine el paso** como "vincular caja con cuenta de efectivo", que es el setup real:
1. Existe al menos 1 `Account` de tipo `cash` en Treasury
2. El `TreasurySettings` tiene `default_cash_account` asignado

**Check compuesto:**
```
caja_vinculada =
  (treasury_accounts.filter(type='cash').length >= 1)
  AND
  (treasury_settings.default_cash_account !== null)
```

**Confiabilidad:** MEDIA — verifica la estructura, no el uso. Pero es la señal correcta para "setup".

**Nota:** Haber abierto una sesión de caja NO se incluye como check de setup. Eso es operación diaria.

---

## 3. Separación clara entre tabs

### 3.1 Tabla maestra de clasificación

| Funcionalidad | Tab | Justificación |
|---------------|-----|--------------|
| **Datos del negocio + perfil fiscal** (nombre, dirección, CUIT, IVA) | **Config. inicial** | Un solo paso: se completa una vez, prerequisito de todo |
| **Logo para facturas y presupuestos** | **Config. inicial** | Setup de una sola vez, identidad visual en documentos |
| **Categorías de productos** | **Config. inicial** | Estructura del catálogo, se hace una vez y se ajusta poco |
| **Productos** (creación / importación) | **Config. inicial** | Sin productos no hay operación posible |
| **Stock inicial** | **Config. inicial** | Snapshot del inventario al arrancar, se hace una vez |
| **Cuentas de dinero** (banco, efectivo, MP) | **Config. inicial** (PRO) | Estructura financiera base, se crea una vez |
| **Vínculo caja-efectivo** (asignar cuenta destino) | **Config. inicial** (PRO) | Setup financiero del POS, se define una vez |
| **Series de documentos** | **Config. inicial** (PRO) | Prerequisito de facturación, se define una vez |
| **Equipo e invitaciones** | **Config. inicial** (PRO) | Estructura de equipo, se hace al principio |
| **Sucursales** | **Config. inicial** (BUSINESS) | Estructura organizacional, se define una vez |
| --- | --- | --- |
| **Registrar ventas** | **Cómo usar** | Operación recurrente diaria |
| **Cobrar desde caja** | **Cómo usar** | Operación recurrente diaria |
| **Cargar clientes** | **Cómo usar** | Operación recurrente (aunque el primer alta podría sugerirse) |
| **Emitir facturas** | **Cómo usar** | Operación recurrente (requiere setup previo del perfil fiscal) |
| **Registrar gastos** | **Cómo usar** | Operación recurrente |
| **Movimientos de stock** (entrada, salida, merma) | **Cómo usar** | Operación recurrente |
| **Reposiciones / compras** | **Cómo usar** | Operación recurrente |
| **Consultar reportes** | **Cómo usar** | Operación de consulta |
| --- | --- | --- |
| **Usar categorías para organizar productos** | **Consejos** | Tip de optimización UX |
| **Configurar alertas de stock bajo** | **Consejos** | Optimización de operación — `commercial_settings.warn_on_low_stock_threshold_enabled` |
| **Asociar ventas a clientes** (historial de compras) | **Consejos** | Tip PRO — nudge de upgrade si es START |
| **Exportar reportes CSV** | **Consejos** | Tip PRO |
| **Presupuestos / cotizaciones** | **Consejos** | Tip PRO — operación avanzada |
| **Respaldo impositivo** (tax backup) | **Consejos** | Tip BUSINESS — feature avanzada |
| **Reportes consolidados multi-sucursal** | **Consejos** | Tip BUSINESS |
| **Auditoría de operaciones** | **Consejos** | Tip PRO — feature de control |

### 3.2 Regla general para clasificar

```
¿Se hace UNA VEZ (o muy pocas veces) al inicio?   → Configuración inicial
¿Se hace RECURRENTEMENTE como parte de la operación? → Cómo usar
¿Es una OPTIMIZACIÓN, DISCOVERY o NUDGE de upgrade? → Consejos y optimización
```

---

## 4. Revisión crítica de completion checks

### 4.1 Checks descartados del V1

| Check V1 | Problema | Resolución |
|----------|---------|-----------|
| `phone` truthy = "negocio configurado" | Un teléfono no significa nada. Un negocio puede tener `phone` pero no `legal_name` ni `tax_id` | Reemplazado por `billing_profile.is_complete` que valida `legal_name` + `tax_id` + `commercial_address` |
| Existencia de `CashSession` = "caja configurada" | Abrir una caja es operación diaria, no setup | Reemplazado por: existencia de `Account(type='cash')` + `TreasurySettings.default_cash_account` |
| `sales.count >= 1` = "setup listo" | Una venta no indica setup completo | Eliminado de Configuración inicial. Ventas vive en "Cómo usar" |
| `stock_movements.count >= 1` = "stock configurado" | Un movimiento no significa inventario inicial | Reemplazado por check compuesto: `summary.out_of_stock < summary.total_products` OR `imports(status=done) >= 1` |

### 4.2 Calidad de cada check propuesto (V2.1 — 10 pasos)

| # | Paso | Check | Señal | Confiabilidad | Notas |
|---|------|-------|-------|---------------|-------|
| 1 | Datos del negocio + fiscal | `billing_profile.is_complete AND vat_condition !== ''` | Campo computado + campo directo | **ALTA** | Merge: valida 4 campos en un solo pass |
| 2 | Logo para facturas | `branding.logo_horizontal_url \|\| branding.logo_square_url` | Campos directos nullable | **ALTA** | null = no subió, truthy = subió |
| 3 | Categorías | `categories.length >= 1` | Count de lista | **ALTA** | Claro y sin ambigüedad |
| 4 | Productos | `inventory_summary.total_products >= 1` | Endpoint dedicado | **ALTA** | Count exacto del negocio |
| 5 | Stock inicial | Check compuesto (ver §2.9) | Derivado | **MEDIA** | Indicador orientativo, no certeza absoluta |
| 6 | Cuentas de dinero | `treasury_accounts.length >= 1` | Count de lista | **ALTA** | Sin ambigüedad |
| 7 | Vínculo caja-efectivo | `accounts.filter(type='cash') >= 1` + `settings.default_cash_account` | Compuesto | **MEDIA** | Verifica estructura, no uso |
| 8 | Series de documentos | `document_series.length >= 1 && alguna con is_default=true` | Count + filtro | **ALTA** | Específico y verificable |
| 9 | Equipo | `memberships.count >= 2` | Count de lista | **ALTA** | Owner siempre cuenta como 1 |
| 10 | Sucursales | `branches.count >= 1` (excluyendo HQ) | Count de lista | **ALTA** | Si no hay branches, count = 0 |

### 4.3 Propuesta para checks de confiabilidad MEDIA

Cuando un check no puede determinar el estado con certeza, el frontend debería:

1. Mostrar el check como **completado con caveat**: ícono ✓ pero sin enfatizarlo como "hecho"
2. Permitir **override manual**: el usuario clickea "Marcar como completado" si el check automático no aplica a su caso
3. Guardar el override en **localStorage** o **backend** (`setup_step_overrides: Record<string, boolean>`)

Ejemplo para stock inicial:
```
SI summary.out_of_stock < summary.total_products → ✅ completado
SI summary.out_of_stock === summary.total_products → ○ pendiente
  (pero con link "No necesito stock" para marcar manual)
```

---

## 5. Importación de inventario como paso protagónico

### 5.1 Análisis del contexto

La importación masiva desde Excel es una de las features más valiosas del onboarding.  
Un comercio típico tiene entre 20 y 2000 productos. Cargar uno por uno es inviable.

El sistema ya soporta:
- Import `.xlsx` con hasta 2000 filas
- Headers flexibles (aliases en español/portugués)
- Matching por SKU → update; por nombre → update; sin match → create
- Preview antes de aplicar
- Stock adjust automático si la columna `stock` está presente

### 5.2 Recomendación: paso único con CTA dual

**NO** separar en dos pasos (manual vs importación). **NO** hacer two pasos secuenciales.

**Sí:** Un único paso "Cargar productos" con **dos CTAs** de igual jerarquía:

```
┌─────────────────────────────────────────────────────────┐
│ ○ Cargar tu catálogo de productos                        │
│                                                         │
│   La base de ventas, stock y facturación. Podés         │
│   importar un Excel o crear uno por uno.                │
│                                                         │
│   ┌────────────────────┐  ┌───────────────────────┐     │
│   │ 📥 Importar Excel  │  │ ➕ Crear manualmente  │     │
│   └────────────────────┘  └───────────────────────┘     │
│                                                         │
│   💡 ¿Tenés muchos productos? La importación Excel       │
│      te permite cargar hasta 2000 de una vez.           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Argumentos:**

1. **Un paso, no dos:** El objetivo es "tener productos en el sistema". El método es secundario.
2. **CTA dual:** Respeta que hay dos perfiles de usuario:
   - El que tiene 5 productos → crea manual
   - El que tiene 200+ → importa Excel
3. **Import como CTA primario visual:** El botón de importación va primero (izquierda) y tiene más peso visual, porque es el path de mayor valor. Pero el manual está disponible sin fricción.
4. **Hint contextual:** El texto del hint refuerza el caso de uso de la importación sin forzar al usuario.

**Rutas:**
- CTA "Importar Excel" → `/app/gestion/stock/importar`
- CTA "Crear manualmente" → `/app/gestion/productos` (con modal de creación, o auto-focus en el botón "+ Producto")

### 5.3 Completion check

El mismo para ambos paths:
```
GET /api/v1/inventory/summary/ → total_products >= 1
```

No importa si llegó por import o por creación manual. El paso se completa cuando hay al menos 1 producto.

### 5.4 Relación con categorías

Las categorías son un paso **anterior** y separado. No se fusionan.

Razón: El import de Excel **no crea categorías automáticamente**. El importer solo matchea `name`, `sku`, `barcode`, `price`, `cost`, `stock`, `stock_min`, `note`. No hay columna `category`.

Esto significa que el usuario debería:
1. Primero crear sus categorías
2. Luego cargar productos (manual o import)
3. Luego asignar categorías a los productos importados (si usó import)

El checklist refleja esta secuencia: categorías (paso 4) antes que productos (paso 5).

---

## 6. Cuentas, caja y finanzas iniciales

### 6.1 Arquitectura financiera real del sistema

```
Treasury (PRO+)
├── Account ← La unidad base. Tiene tipo + saldo.
│   ├── type: 'cash'         → Efectivo / caja chica
│   ├── type: 'bank'         → Cuenta bancaria
│   ├── type: 'mercadopago'  → Billetera digital
│   ├── type: 'card_float'   → Flotante de tarjeta
│   └── type: 'other'        → Otros
│
├── TreasurySettings ← Mapea método de pago → cuenta default
│   ├── default_cash_account → Account(type='cash')
│   ├── default_bank_account → Account(type='bank')
│   ├── default_mercadopago_account → Account(type='mercadopago')
│   └── default_card_account → Account(type='card_float')
│
└── Transaction ← Cada movimiento de dinero
    ├── IN / OUT / ADJUST
    └── Linked to: sale, expense, payroll, replenishment, etc.

Cash (PRO+)
├── Terminal ← Dispositivo/estación de cobro
│   └── CashSession ← Sesión de caja (open → close)
│       ├── opening_cash_amount
│       ├── CashMovement (manual IN/OUT)
│       └── Payment (from sales)
```

### 6.2 Clasificación para el onboarding

| Elemento | Tab | Justificación | Plan |
|----------|-----|---------------|------|
| **Crear cuentas de dinero** (efectivo, banco, MP) | **Config. inicial** | Estructura base. Sin cuentas, Treasury no funciona. Se hace una sola vez. | PRO |
| **Mapear cuentas a métodos de pago** (TreasurySettings) | **Config. inicial** (incluido en paso "Crear cuentas") | Consecuencia directa de crear cuentas. El frontend debería sugerirlo inline. | PRO |
| **Configurar caja** (abrir primera sesión) | **Config. inicial** | Setup de infraestructura POS. Pero el verdadero setup es tener la cuenta de efectivo + el mapping. | PRO |
| **Registrar gastos** | **Cómo usar** | Operación recurrente | PRO |
| **Gastos fijos** (alquiler, servicios) | **Cómo usar** | Configuración recurrente mensual | PRO |
| **Reposiciones / compras** | **Cómo usar** | Operación recurrente ligada a stock | PRO |
| **Reconciliación de cuentas** | **Consejos** | Optimización avanzada, no es setup | PRO |
| **Respaldo impositivo** (tax backup) | **Consejos** | Feature avanzada BUSINESS | BUSINESS |
| **Presupuestos de gasto** (Budget) | **Consejos** | Optimización, no setup | PRO |

### 6.3 Propuesta UX para el paso financiero

El paso 6 ("Crear tus cuentas de dinero") debería presentarse como un **mini-setup guiado**, no como "entrá a finanzas y creá algo":

```
┌─────────────────────────────────────────────────────────┐
│ ○ Crear tus cuentas de dinero                  PRO    │
│                                                         │
│   Definí dónde entra y sale la plata de tu negocio.     │
│   Necesario para usar caja, gastos y finanzas.          │
│                                                         │
│   Cuentas comunes:                                      │
│   • 💵 Efectivo — para cobros en caja                   │
│   • 🏦 Banco — para transferencias y débitos            │
│   • 💜 Mercado Pago — para cobros digitales             │
│                                                         │
│   [Crear cuenta →]                                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**No es necesario** crear una UI de onboarding nueva para esto. El CTA lleva a la página de cuentas existente (`/app/gestion/finanzas/cuentas`) que ya tiene el modal de creación.

### 6.4 Separación cuentas vs vínculo caja-efectivo

**Cuentas de dinero** y **vínculo caja-efectivo** son pasos **separados** en el checklist:

1. **Paso 6: Cuentas de dinero** — Crear al menos 1 Account (preferiblemente una de tipo `cash`)
2. **Paso 7: Vincular caja con cuenta de efectivo** — Verificar que `TreasurySettings.default_cash_account` está asignado

**Razón:** Un usuario PRO que no usa caja física (solo vende online) necesita cuentas de dinero pero no necesariamente el vínculo de caja. Son conceptos distintos.

El paso de vínculo caja-efectivo se marca como **Recomendado**, no Obligatorio.

---

## 7. Experiencia START vs PRO vs BUSINESS

### 7.1 Principio: no mostrar una pared de pasos bloqueados

Un usuario START que ve 10 pasos, de los cuales 5 están bloqueados, percibe:
- "Este sistema no es para mí"
- "Estoy pagando por algo incompleto"
- "Necesito pagar más para que funcione"

**Eso es inaceptable.**

### 7.2 Estrategia de visualización por plan

#### Plan START (5 pasos visibles + 1 nudge)

| Visible | Paso |
|---------|----- |
| ✅ | Completar los datos de tu negocio |
| ✅ | Subir tu logo para facturas y presupuestos |
| ✅ | Crear categorías de productos |
| ✅ | Cargar tu catálogo de productos (manual + import) |
| ✅ | Definir el stock inicial |
| ─ | **Nudge único** al final (no como paso bloqueado) |

Para START, los 5 pasos base se muestran completos, sin nada bloqueado.  
Al final del checklist, un **único bloque de upgrade** no intrusivo:

```
┌─────────────────────────────────────────────────────────┐
│  ✨ ¿Necesitás más?                                     │
│                                                         │
│  Con el plan PRO podés:                                 │
│  • Configurar caja y cobrar desde el POS                │
│  • Gestionar cuentas de dinero y finanzas               │
│  • Emitir facturas electrónicas                         │
│  • Controlar accesos de tu equipo                       │
│                                                         │
│  [Ver planes →]                                         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Reglas para START:**
- NO mostrar pasos PRO/BUSINESS como ítems bloqueados del checklist
- NO mostrar badges PRO/BUSINESS en pasos individuales
- SÍ mostrar un bloque de upgrade compacto al final
- El checklist START debe sentirse **completo** con sus 6 pasos

#### Plan PRO (9 pasos visibles + 1 nudge)

| Visible | Paso |
|---------|----- |
| ✅ | Todos los de START (5) |
| ✅ | Crear tus cuentas de dinero |
| ✅ | Vincular caja con cuenta de efectivo |
| ✅ | Crear series de documentos |
| ✅ | Invitar a tu equipo |
| ─ | **Nudge BUSINESS** al final (sucursales, respaldo impositivo) |

#### Plan BUSINESS (10 pasos, sin nudge)

| Visible | Paso |
|---------|----- |
| ✅ | Todos los de PRO (9) |
| ✅ | Crear sucursales |

El checklist BUSINESS se muestra completo. No hay nudge porque ya es el plan más alto accesible (Enterprise es custom/contacto).

### 7.3 Implementación técnica del filtrado

```typescript
function getVisibleSteps(
  allSteps: SetupStep[],
  currentPlan: 'starter' | 'pro' | 'business' | 'enterprise',
): SetupStep[] {
  const planTier = { starter: 0, pro: 1, business: 2, enterprise: 3 };
  const current = planTier[currentPlan] ?? 0;

  return allSteps.filter(step => {
    const required = planTier[step.minPlan] ?? 0;
    return required <= current; // Solo mostrar si el plan alcanza
  });
}

function shouldShowUpgradeNudge(currentPlan: string): boolean {
  return currentPlan === 'starter' || currentPlan === 'pro';
}

function getUpgradeNudgeTarget(currentPlan: string): string {
  return currentPlan === 'starter' ? 'PRO' : 'BUSINESS';
}
```

**Clave:** Los pasos de planes superiores **no se renderizan como ítems del checklist**.  
Se reemplazan por un **bloque de upgrade estático** al final.

---

## 8. Propuesta V2.1 — Configuración inicial para Gestión Comercial

### 8.1 Estructura final de la tab

```
┌────────────────────────────────────────────────────────────┐
│  Configuración inicial — Gestión Comercial          [✕]   │
│                                                            │
│  Progreso: 2/5 completados                                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░░░                 │
│                                                            │
│  ── Tu negocio ─────────────────────────────────────────   │
│                                                            │
│  ✅ Completar los datos de tu negocio                       │
│     Nombre, dirección, CUIT y condición ante IVA.          │
│                                                            │
│  ○  Subir tu logo para facturas y presupuestos             │
│     El logo aparece en el encabezado de tus documentos     │
│     comerciales en PDF.                    [Subir logo →]  │
│                                                            │
│  ── Tu catálogo ────────────────────────────────────────   │
│                                                            │
│  ○  Crear categorías de productos         [Crear →]        │
│     Organizá tu catálogo por rubros o familias.            │
│                                                            │
│  ○  Cargar tu catálogo de productos                        │
│     La base de ventas, stock y facturación. Podés          │
│     importar un Excel o crear uno por uno.                 │
│                                                            │
│     [📥 Importar Excel]    [➕ Crear manualmente]          │
│                                                            │
│  ── Tu inventario ──────────────────────────────────────   │
│                                                            │
│  ○  Definir el stock inicial               [Cargar →]      │
│     Cargá las cantidades actuales para activar alertas     │
│     y control de inventario.                               │
│                                                            │
│  ── ¿Necesitás más? ───────────────────────────────────   │
│                                                            │
│  Con el plan PRO podés gestionar finanzas, emitir          │
│  facturas y controlar accesos de tu equipo.                │
│  [Ver planes →]                                            │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

(Vista START — 5 pasos + nudge al final)

```
┌────────────────────────────────────────────────────────────┐
│  Configuración inicial — Gestión Comercial          [✕]   │
│                                                            │
│  Progreso: 4/9 completados                                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░                 │
│                                                            │
│  ── Tu negocio ─────────────────────────────────────────   │
│  ✅ Completar los datos de tu negocio                       │
│  ✅ Subir tu logo para facturas y presupuestos              │
│                                                            │
│  ── Tu catálogo ────────────────────────────────────────   │
│  ✅ Crear categorías de productos                           │
│  ✅ Cargar tu catálogo de productos                         │
│                                                            │
│  ── Tu inventario ──────────────────────────────────────   │
│  ○  Definir el stock inicial               [Cargar →]      │
│                                                            │
│  ── Tus finanzas ───────────────────────────────────────   │
│  ○  Crear tus cuentas de dinero            [Crear →]       │
│  ○  Vincular caja con cuenta de efectivo   [Configurar →]  │
│                                                            │
│  ── Facturación ────────────────────────────────────────   │
│  ○  Crear series de documentos             [Crear →]       │
│                                                            │
│  ── Tu equipo ──────────────────────────────────────────   │
│  ○  Invitar a tu equipo                    [Invitar →]     │
│                                                            │
│  ── ¿Necesitás más? ───────────────────────────────────   │
│  Con BUSINESS podés crear sucursales, consolidar           │
│  reportes y generar respaldos impositivos.                 │
│  [Ver planes →]                                            │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

(Vista PRO — 9 pasos + nudge BUSINESS)

### 8.2 Bloques / secciones internas

| Bloque | Pasos incluidos | Aplica a |
|--------|----------------|----------|
| **Tu negocio** | Datos + fiscal (paso 1) · Logo para documentos (paso 2) | ALL |
| **Tu catálogo** | Categorías (paso 3) · Productos con CTA dual (paso 4) | ALL |
| **Tu inventario** | Stock inicial (paso 5) | ALL |
| **Tus finanzas** | Cuentas de dinero (paso 6) · Vínculo caja-efectivo (paso 7) | PRO+ |
| **Facturación** | Series de documentos (paso 8) | PRO+ |
| **Tu equipo** | Invitar equipo (paso 9) | PRO+ |
| **Tu estructura** | Crear sucursales (paso 10) | BUSINESS |
| **¿Necesitás más?** | Bloque estático de upgrade | START / PRO |

Los bloques que no aplican al plan del usuario **no se renderizan** (ni como sección vacía ni como bloque bloqueado).

### 8.3 Orden final de pasos (V2.1)

| Orden | ID | Paso | minPlan | Obligatoriedad | Ruta |
|-------|-----|------|---------|----------------|------|
| 1 | `gestion.business_and_fiscal` | Completar los datos de tu negocio | starter | Obligatorio | `/app/gestion/configuracion/negocio` |
| 2 | `gestion.branding` | Subir tu logo para facturas y presupuestos | starter | Recomendado | `/app/gestion/configuracion/negocio` |
| 3 | `gestion.categories` | Crear categorías de productos | starter | Recomendado | `/app/gestion/productos/categorias` |
| 4 | `gestion.products` | Cargar tu catálogo de productos | starter | Obligatorio | `/app/gestion/productos` · `/app/gestion/stock/importar` |
| 5 | `gestion.initial_stock` | Definir el stock inicial | starter | Recomendado | `/app/gestion/stock` |
| 6 | `gestion.treasury_accounts` | Crear tus cuentas de dinero | pro | Obligatorio (si PRO) | `/app/gestion/finanzas/cuentas` |
| 7 | `gestion.cash_link` | Vincular caja con cuenta de efectivo | pro | Recomendado | `/app/gestion/finanzas/configuracion` |
| 8 | `gestion.document_series` | Crear series de documentos | pro | Recomendado | `/app/gestion/configuracion/negocio` |
| 9 | `gestion.team` | Invitar a tu equipo | pro | Opcional | `/app/settings/access` |
| 10 | `gestion.branches` | Crear sucursales | business | Recomendado | `/app/owner` |

### 8.4 Diferenciación por plan — resumen

| Plan | Pasos visibles | Bloques visibles | Nudge |
|------|---------------|-----------------|-------|
| START | 1–5 | Tu negocio · Tu catálogo · Tu inventario | → PRO |
| PRO | 1–9 | Todos menos "Tu estructura" | → BUSINESS |
| BUSINESS | 1–10 | Todos | Ninguno |
| ENTERPRISE | 1–10 | Todos | Ninguno |

### 8.5 Recomendaciones UX

1. **Progreso por bloque, no solo global.** Cada sección debería tener su indicador compacto (e.g., "2/3" al lado del título del bloque). Esto da sensación de avance incluso si el checklist total es largo.

2. **Colapsar bloques completados.** Si "Tu negocio" está 3/3, colapsar automáticamente y mostrar inline "✅ Completado". Esto reduce scroll y enfoca la atención en lo pendiente.

3. **No bloquear la navegación.** El checklist es orientativo, no un wizard secuencial. El usuario puede completar pasos en cualquier orden. Las dependencias lógicas (e.g., "necesitás productos para cargar stock") se muestran como hints, no como bloqueos.

4. **CTA contextual por paso.** Cada paso tiene un CTA que navega a la sección correcta de la app Y cierra el modal. Al volver al modal, el status se recomputa.

5. **Estado "en progreso" implícito.** No se usa un estado explícito "en_progreso". Un paso está `pending` (no completado) o `completed` (check pasó). El usuario no necesita marcarlo manualmente como "en progreso".

6. **El paso de productos es visualmente más grande.** Es el step más importante y tiene CTA dual. Merece más espacio visual que los demás.

7. **Texto de ayuda corto pero útil.** Cada paso tiene 1 línea de descripción. No incluir tutoriales. No incluir "por qué". Solo "qué tenés que hacer".

### 8.6 Observaciones técnicas para implementación

1. **Endpoint consolidado (recomendado para V1):**
   En lugar de hacer 5-10 llamadas individuales, crear `GET /api/v1/help/setup-status/` que retorne el estado de todos los checks en una sola respuesta:

   ```json
   {
     "gestion.business_and_fiscal": { "completed": true },
     "gestion.branding": { "completed": true },
     "gestion.categories": { "completed": true, "count": 5 },
     "gestion.products": { "completed": true, "count": 47 },
     "gestion.initial_stock": { "completed": false, "detail": { "total": 47, "with_stock": 12 } },
     "gestion.treasury_accounts": { "completed": false, "count": 0 },
     "gestion.cash_link": { "completed": false, "detail": { "has_cash_account": false, "has_default_mapping": false } },
     "gestion.document_series": { "completed": false, "count": 0 },
     "gestion.team": { "completed": false, "members": 1 },
     "gestion.branches": { "completed": false, "count": 0 }
   }
   ```

   **Ventaja:** Una sola request, cache unificado, lógica de check centralizada en backend (single source of truth).

   **Nota:** Incluir solo los pasos que aplican al plan del usuario. El backend conoce el plan y puede filtrar.

2. **Setup guide dismiss — campo backend:**
   Mantener la propuesta V1: `setup_guide_dismissed_at` en el modelo Business. Una migración AddField, trivial.

3. **Invalidación de cache:**
   Cada vez que el usuario completa una acción relevante (crea producto, sube logo, etc.), invalidar el cache de React Query para `setupStatusKey`. Esto puede hacerse con `queryClient.invalidateQueries({ queryKey: ['setup-status'] })` en el `onSuccess` de las mutations relevantes.

4. **Feature flag para el modal:**
   Agregar un feature flag `help_modal_enabled` (default `true`) que permita desactivar el modal globalmente si hay problemas. Esto es independiente del feature gating por plan.

5. **Paso comercial+fiscal — single step, single check:**
   V2 tenía pasos 1 (datos del negocio) y 3 (perfil fiscal) separados pese a apuntar a la misma ruta.
   V2.1 los fusiona en paso 1 con check unificado: `is_complete AND vat_condition !== ''`.
   **Recomendación:** Agregar `vat_condition` al cálculo de `is_complete` en backend.

6. **Import Excel — link a plantilla:**
   El CTA "Importar Excel" debería incluir en su tooltip o sub-texto un link para descargar la plantilla template (si existe como archivo descargable). Actualmente la documentación está en `docs/STOCK_IMPORT_TEMPLATE_GUIDE.md` pero no hay un `.xlsx` template descargable para el usuario. **Esto es un gap identificado.**

---

## 9. Contenido propuesto para las otras tabs (solo Gestión Comercial)

### 9.1 Tab "Cómo usar" — Operaciones recurrentes

| # | Título | Descripción | Ruta | Plan |
|---|--------|-------------|------|------|
| 1 | Registrar una venta | Cargá ventas desde el panel con productos, cantidad y método de pago. | `/app/gestion/ventas` | ALL |
| 2 | Cobrar desde la caja | Abrí una sesión de caja, cobrá ventas y cerrá el turno con arqueo. | `/app/operacion/caja` | PRO |
| 3 | Cargar un cliente | Creá clientes para asociar ventas y llevar historial de compras. | `/app/gestion/clientes` | PRO |
| 4 | Emitir una factura | Generá facturas vinculadas a ventas con tu perfil fiscal configurado. | `/app/gestion/facturas` | PRO |
| 5 | Registrar un gasto | Cargá gastos puntuales o fijos y vinculalos a cuentas de dinero. | `/app/gestion/finanzas/gastos` | PRO |
| 6 | Hacer un movimiento de stock | Registrá entradas, salidas, ajustes o mermas en tu inventario. | `/app/gestion/stock` | ALL |
| 7 | Registrar una compra / reposición | Cargá compras a proveedores que ajusten stock y generen gasto automático. | `/app/gestion/stock` | PRO |
| 8 | Consultar reportes | Revisá métricas de ventas, stock y finanzas desde el panel de reportes. | `/app/gestion/reportes` | PRO |

### 9.2 Tab "Consejos y optimización"

| # | Tip | Plan mínimo | CTA |
|---|-----|-------------|-----|
| 1 | Usá categorías para filtrar rápido en la lista de productos y en reportes | ALL | — |
| 2 | Configurá alertas de stock bajo para no quedarte sin mercadería | ALL | Ir a config → `commercial_settings.warn_on_low_stock_threshold_enabled` |
| 3 | Definí un stock mínimo por producto para que las alertas sean precisas | ALL | — |
| 4 | Asociá ventas a clientes para tener historial y poder fidelizar | PRO | Ver planes → |
| 5 | Exportá reportes en CSV para compartir con tu contador | PRO | Ver planes → |
| 6 | Usá presupuestos para enviar cotizaciones antes de cerrar la venta | PRO | Ver planes → |
| 7 | Configurá gastos fijos (alquiler, servicios) para automatizar seguimiento mensual | PRO | — |
| 8 | Reconciliá tus cuentas periódicamente para detectar diferencias | PRO | — |
| 9 | Abrí sucursales para gestionar múltiples locales desde un panel | BUSINESS | Ver planes → |
| 10 | Activá respaldo impositivo para digitalizar facturas recibidas con OCR | BUSINESS | Ver planes → |
| 11 | Consultá reportes consolidados para ver el rendimiento de todas tus sucursales | BUSINESS | Ver planes → |

---

## 10. Resumen de cambios V1 → V2

| Aspecto | V1 | V2 |
|---------|----|----|
| Pasos START | 4 (+ 5 bloqueados visible) | **6 pasos limpios + nudge compacto** |
| "Registrar primera venta" | En Config. inicial | **Movido a "Cómo usar"** |
| "Exportar datos" | En Config. inicial | **Movido a "Consejos"** |
| Paso de productos | CTA simple "Crear producto" | **CTA dual: Importar Excel + Crear manual** |
| Check "negocio configurado" | `phone` truthy | **`billing_profile.is_complete`** |
| Check "caja configurada" | `CashSession.count >= 1` | **`Account(type=cash)` + `TreasurySettings.default_cash_account`** |
| Check "stock inicial" | `stock_movements.count >= 1` | **Check compuesto: summary.out_of_stock < total OR import done** |
| Pasos PRO bloqueados en START | Mostrados con badge + lock | **Ocultos. Nudge único al final** |
| Perfil fiscal | Incluido en "datos del negocio" | **Paso separado** (CUIT + IVA ≠ nombre + dirección) |
| Cuentas/caja/finanzas | Un solo paso genérico | **2 pasos separados: cuentas de dinero + configurar caja** |
| Series de documentos | No incluido | **Paso explícito** (prerequisito real de facturación) |
| Secciones internas del checklist | Lista plana | **Bloques con títulos: Tu negocio / Tu catálogo / etc.** |
| Endpoint de checks | N llamadas individuales | **Recomendación: endpoint consolidado /help/setup-status/** |

---

## 11. Resumen de cambios V2 → V2.1

| Aspecto | V2 | V2.1 |
|---------|----|----|
| **Datos + fiscal** | 2 pasos separados (1 y 3) con misma ruta | **1 solo paso**: "Completar los datos de tu negocio" — check: `is_complete AND vat_condition` |
| **Branding: descripción** | "Logo horizontal, cuadrado y color corporativo" | **"Subir tu logo para facturas y presupuestos"** — refleja que branding solo se usa en PDFs |
| **Branding: alcance documentado** | No especificado | **Nota explícita:** BusinessBranding se consume **solo** en `invoices/pdf.py` y `sales/quote_pdf.py`. No en sidebar, header, app, emails, menú QR |
| **"Configurar caja" → renombrado** | "Configurar caja" (confundía setup con operación diaria) | **"Vincular caja con cuenta de efectivo"** — acción de setup clara |
| **ID del paso caja** | `gestion.cash_setup` | **`gestion.cash_link`** — refleja la acción real |
| **Ruta del paso caja** | `/app/operacion/caja` (zona de operación) | **`/app/gestion/finanzas/configuracion`** (zona de setup) |
| **Check del paso caja** | Confiabilidad BAJA (buscaba CashSession) | Confiabilidad **MEDIA** (verifica Account cash + TreasurySettings mapping) |
| **Total de pasos** | 11 (6 START + 4 PRO + 1 BUS) | **10** (5 START + 4 PRO + 1 BUS) |
| **ID paso 1** | `gestion.business_profile` + `gestion.fiscal_profile` | **`gestion.business_and_fiscal`** — un solo ID |
| **Copy UX: todos los títulos** | Descriptivos/técnicos ("Cargar productos", "Crear cuentas de dinero") | **Orientados al usuario** ("Cargar tu catálogo de productos", "Crear tus cuentas de dinero") |
| **Copy UX: descripciones** | Genéricas | **Específicas al impacto**: qué pasa si no lo hacés, qué desbloquea |
| **Wireframes** | START 6 pasos, PRO 10 pasos | **START 5 pasos, PRO 9 pasos** — consistentes con merge |
