# Fase 4 — Diseño Frontend: Respaldo Impositivo

> Módulo: Respaldo Impositivo · Plan: Business · Entitlement: `gestion.tax_backup`
> Stack: Next.js App Router · TanStack Query v5 · Tailwind + shadcn/ui · lucide-react

---

## 1. Resumen Ejecutivo

Se diseña la experiencia frontend del módulo **Respaldo Impositivo** como una nueva sub-pestaña dentro de Gastos ("Respaldo") en el módulo Finanzas ya existente, gateada por entitlement `gestion.tax_backup` (plan Business). El módulo permite al usuario:

1. **Listar** sus gastos con perfil fiscal, ver semáforo de estado, filtrar y buscar.
2. **Crear** un perfil fiscal para un gasto existente (asociar documentos, método de pago, tipo de asignación).
3. **Ver detalle** con comprobantes adjuntos, pagos, historial de estado y posibles duplicados.
4. **Gestionar servicios recurrentes** y sus alertas de comprobantes faltantes.
5. **Visualizar métricas** en un mini-dashboard interactivo con donut chart y contadores.

La interfaz reutiliza 100% los patrones existentes: tabs URL-based, cards con badges, modals para formularios, EmptyState, EntitlementGate, Currency, y el sistema de colores slate/emerald/rose/amber del design system.

---

## 2. Decisiones Asumidas

| # | Decisión | Justificación |
|---|----------|---------------|
| D1 | Nueva sub-tab `?tab=respaldo` dentro de `gastos-client.tsx` | Sigue el patrón actual de 3 tabs (fijos/puntuales/reposiciones) → ahora 4. Evita crear una nueva ruta top-level en FinanceTabs. |
| D2 | EntitlementGate envuelve solo el contenido de la tab respaldo, no las demás | Si no tiene plan Business, ve las otras tabs normalmente y en "Respaldo" ve UpgradeBlock. |
| D3 | Los formularios usan `useState` + `<form onSubmit>` — sin react-hook-form ni zod | Consistente con TODOS los formularios existentes en el módulo Finanzas. |
| D4 | Colores semáforo: emerald=respaldado, amber=a_revisar+potencialmente_deducible, rose=no_respaldado, slate=registrado | Mapeo natural al design system. Se evita confusión con violet (reservado para reposiciones). |
| D5 | Nunca se dice "deducible confirmado" ni "confirmamos la deducibilidad" en UI | Restricción legal explícita. Se usa "Potencialmente deducible" o "Con respaldo fiscal". |
| D6 | Upload de archivos con drag & drop simple + click, máx 10 MB, PDF/JPG/PNG/WEBP | Alineado con la validación del backend. Se usa `<input type="file">` nativo con preview. |
| D7 | Tabla para listing (no cards) ya que los perfiles fiscales tienen múltiples campos | Gastos puntuales usan cards, pero el perfil fiscal tiene: nombre, monto, status, asignación, docs, fecha. Tabla es más eficiente. |
| D8 | El detalle de perfil fiscal usa layout 2-panel en desktop (tabla izq + detail der). En mobile (<1024px) el detail se renderiza stacked debajo de la tabla, inline, sin navegación adicional. Al seleccionar un perfil se hace scroll automático al detail con `scrollIntoView()`. | Sigue el patrón de fixed-expenses-client.tsx. Se descarta drawer (dependencia Radix Sheet no existente) y full-screen route (rompe el contexto de tabs). Stacked inline es el patrón más simple y coherente con el responsive actual del grid `lg:grid-cols-3` que ya colapsa a 1 columna. |
| D9 | Query keys: `['tax-backup', ...]` como namespace separado de `['treasury', ...]` | Es un módulo independiente con su propio API namespace (`/api/v1/tax-backup/`). |
| D10 | API client en `lib/api/tax-backup.ts` separado de `treasury.ts` | Separación de concerns. Treasury ya es grande (400+ líneas). |

---

## 3. Diseño Propuesto

### 3.1 Mapa de Pantallas

```
/app/gestion/finanzas/gastos?tab=respaldo
├── [EntitlementGate gestion.tax_backup]
│   ├── TaxBackupDashboard (mini resumen: donut + contadores)
│   ├── TaxBackupToolbar (filtros + búsqueda + botón "Nuevo Perfil")
│   ├── TaxBackupTable (tabla de perfiles fiscales)
│   │   └── TaxStatusBadge (semáforo inline)
│   ├── TaxBackupDetail (panel derecho / drawer)
│   │   ├── ProfileHeader (nombre, monto, status badge, allocation badge)
│   │   ├── DocumentsList + UploadDocument
│   │   ├── PaymentsList + AddPayment
│   │   ├── StatusTimeline (historial de cambios)
│   │   ├── DuplicateAlerts (si aplica)
│   │   └── ActionBar (re-evaluar, editar asignación)
│   └── [Modal] CreateProfileForm
│       ├── Expense selector (gastos sin perfil fiscal)
│       ├── AllocationType radio
│       ├── Mixed % slider (si allocation=mixed)
│       └── Notas
│
├── TaxBackupServicesView (sub-tab o section)
│   ├── ServicesList (servicios recurrentes)
│   └── AlertsList (alertas de comprobantes faltantes)
│
└── [fallback: UpgradeBlock si no tiene entitlement]
```

### 3.2 Flujos de Usuario

#### Flujo 1: Primera vez (onboarding)
```
Tab "Respaldo" → EntitlementGate verifica →
  ✓ Tiene plan Business →
    EmptyState "Aún no tenés perfiles fiscales"
    CTA: "Crear primer perfil"
  ✗ No tiene plan →
    UpgradeBlock "Respaldo Impositivo requiere plan Business"
```

#### Flujo 2: Crear perfil fiscal para un gasto
```
Click "Nuevo Perfil" →
  Modal CreateProfileForm:
    1. Select "Gasto" (dropdown de gastos SIN perfil fiscal)
    2. Radio "Asignación": Negocio | Mixto | Personal
       → Si Mixto: slider % negocio (10-90)
    3. Textarea "Notas" (opcional)
    4. Submit → POST /api/v1/tax-backup/profiles/
       → Backend auto-evalúa reglas → status="registrado"
       → Invalidate ['tax-backup', 'profiles']
       → Close modal → Seleccionar perfil creado en tabla
```

#### Flujo 3: Adjuntar comprobante
```
En detail panel → Sección "Comprobantes" →
  Click "Adjuntar" o drag & drop →
    File input: max 10MB, PDF/JPG/PNG/WEBP
    Campos inline:
      - Tipo de comprobante (select: Factura, Recibo, Ticket, N/C, N/D, Otro)
      - CUIT emisor (text, optional)
      - Nombre emisor (text, optional)
      - Nro comprobante (text, optional)
      - Fecha emisión (date, optional)
      - Total (number, optional)
      - ¿Es comprobante fiscal? (checkbox, default=true)
    Submit → POST /api/v1/tax-backup/profiles/{id}/documents/
      → Backend re-evalúa → puede cambiar a "respaldado"
      → Invalidate queries → Status badge se actualiza
```

#### Flujo 4: Registrar forma de pago
```
En detail panel → Sección "Pagos" →
  Click "Agregar forma de pago" →
    Inline form:
      - Método (select: Efectivo, Transferencia, Tarjeta, MercadoPago, Cheque, Otro)
      - Referencia (text, optional)
      - Comprobante de pago (file upload, optional)
    Submit → POST /api/v1/tax-backup/profiles/{id}/payments/
      → Backend re-evalúa
      → Invalidate queries
```

#### Flujo 5: Re-evaluar manualmente
```
En detail panel → ActionBar →
  Click "Re-evaluar" →
    POST /api/v1/tax-backup/profiles/{id}/re-evaluate/
    → Response: { tax_status, duplicates_found }
    → Invalidate ['tax-backup', 'profiles', id]
    → Toast: "Estado actualizado: {display}" o "Sin cambios"
```

#### Flujo 6: Resolver alerta de duplicado
```
Banner amarillo en detail panel (si hay DuplicateFlags pendientes) →
  "Posible duplicado con {expense_name}" →
    Botones: "Es duplicado" / "No es duplicado"
    → PATCH /api/v1/tax-backup/duplicates/{id}/
      { status: 'confirmed_duplicate' | 'dismissed' }
    → Invalidate queries
```

#### Flujo 7: Servicio recurrente — alta y alertas
```
Sub-sección "Servicios Recurrentes" →
  "Asociar gasto fijo como servicio" →
    Select FixedExpense sin service_profile →
    Campos: nombre servicio, CUIT proveedor, tipo doc esperado
    Submit → POST /api/v1/tax-backup/services/
  
Alertas:
  Badge contador en tab "Servicios" →
    Lista de alertas (comprobante faltante / datos incompletos)
    → PATCH para resolver o descartar
```

### 3.3 Estructura de Componentes

```
apps/web/src/app/app/gestion/finanzas/gastos/
├── gastos-client.tsx                 ← MODIFICAR: agregar tab "respaldo"
├── tax-backup/
│   ├── tax-backup-client.tsx         ← Componente raíz con layout 2-panel
│   ├── tax-backup-dashboard.tsx      ← Mini dashboard (donut + contadores)
│   ├── tax-backup-table.tsx          ← Tabla filtrable de perfiles
│   ├── tax-backup-detail.tsx         ← Panel derecho con toda la info
│   ├── tax-backup-services.tsx       ← Servicios recurrentes + alertas
│   ├── create-profile-modal.tsx      ← Modal de creación
│   ├── document-upload.tsx           ← Upload + form inline de comprobante
│   ├── payment-form.tsx              ← Form inline de pago
│   └── status-timeline.tsx           ← Historial visual de cambios de estado

apps/web/src/lib/api/
├── tax-backup.ts                     ← API client con tipos e interfaces

(componentes compartidos ya existentes — se reutilizan sin modificar)
├── components/ui/button.tsx
├── components/ui/modal.tsx
├── components/ui/badge.tsx
├── components/gestion/entitlement-gate.tsx
├── components/gestion/upgrade-prompt.tsx
├── finanzas/components/empty-state.tsx
├── finanzas/components/currency.tsx
```

### 3.4 Formularios y Campos

#### CreateProfileForm (Modal)

| Campo | Tipo HTML | Requerido | Fuente de datos |
|-------|-----------|-----------|-----------------|
| Gasto asociado | `<select>` | Sí | GET /api/v1/treasury/expenses/?status=pending&status=paid (filtrado: sin `fiscal_profile`) |
| Tipo de asignación | `<fieldset>` radio buttons | Sí | AllocationType: business, mixed, personal |
| % uso negocio | `<input type="range">` + `<input type="number">` | Solo si mixed | 10-90, step 5, default 50 |
| Notas | `<textarea>` | No | Texto libre, max 500 chars |

#### DocumentUploadForm (Inline en detail panel)

| Campo | Tipo HTML | Requerido | Validación |
|-------|-----------|-----------|------------|
| Archivo | `<input type="file">` con drag zone | Sí | max 10MB, accept=".pdf,.jpg,.jpeg,.png,.webp" |
| Tipo de comprobante | `<select>` | Sí | DocumentType choices |
| Es comprobante fiscal | `<input type="checkbox">` | No | default=true |
| CUIT emisor | `<input type="text">` | No | Pattern: XX-XXXXXXXX-X |
| Nombre emisor | `<input type="text">` | No | — |
| Nro comprobante | `<input type="text">` | No | — |
| Fecha emisión | `<input type="date">` | No | ≤ hoy |
| Total | `<input type="number" step="0.01">` | No | ≥ 0 |

#### PaymentForm (Inline en detail panel)

| Campo | Tipo HTML | Requerido | Fuente |
|-------|-----------|-----------|--------|
| Método de pago | `<select>` | Sí | PaymentMethod choices |
| Referencia | `<input type="text">` | No | Nro transferencia, etc. |
| Comprobante de pago | `<input type="file">` | No | max 10MB, mismos formatos |

### 3.5 Tabla / Listado de Perfiles

**Columnas:**

| Columna | Contenido | Ancho | Orden |
|---------|-----------|-------|-------|
| Gasto | expense_name (link al detail) | flex-1 | — |
| Monto | expense_amount con `<Currency>` | 120px | — |
| Estado Fiscal | `<TaxStatusBadge status={tax_status} />` | 160px | — |
| Asignación | allocation_type badge | 100px | — |
| Docs | doc_count (con icono FileText) | 60px | — |
| Fecha | created_at formateada | 100px | default desc |

**Filtros (toolbar):**

| Filtro | Componente | Query param |
|--------|------------|-------------|
| Estado fiscal | `<select>` multi-option | `?tax_status=respaldado` |
| Asignación | `<select>` | `?allocation_type=business` |
| Búsqueda | `<input type="search">` | `?search=internet` (debounce 300ms) |

### 3.6 Vista de Detalle (Panel Derecho)

Layout vertical con secciones colapsables:

```
┌─────────────────────────────────────────┐
│ ← Volver    [Re-evaluar]  [Editar]      │
├─────────────────────────────────────────┤
│ Internet Fibertel             $15.200   │
│ ● Respaldado     🏢 Negocio            │
│ Vence: 15/01/2025                       │
├─────────────────────────────────────────┤
│ 📎 Comprobantes (2)           [Adjuntar]│
│ ┌─────────────────────────────────────┐ │
│ │ 📄 Factura A 0001-00045234         │ │
│ │    Fibertel SA · $15.200 · 10/01   │ │
│ │    ✓ Comprobante fiscal    [🗑️]    │ │
│ ├─────────────────────────────────────┤ │
│ │ 📄 Ticket pos #445                 │ │
│ │    Sin nombre · $15.200 · 10/01    │ │
│ │    ✗ No fiscal             [🗑️]    │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ 💳 Pagos (1)            [Agregar pago]  │
│ ┌─────────────────────────────────────┐ │
│ │ Transferencia · Ref: TRF-4456      │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ ⏱️ Historial                            │
│  ● 10/01 14:30 — registrado→respaldado │
│    Regla: BACKED · "All clear"         │
│  ○ 10/01 14:25 — (creado)→registrado   │
│    Regla: FALLBACK                     │
├─────────────────────────────────────────┤
│ ⚠️ Posibles duplicados                  │
│  "Internet Enero" ↔ "Fibertel Ene"     │
│  Match: Proveedor+Factura+Fecha+Monto  │
│  [Es duplicado] [No es duplicado]       │
└─────────────────────────────────────────┘
```

### 3.7 Vista de Servicios Recurrentes

Se accede desde una sub-tab "Servicios" dentro de la tab Respaldo (pill tabs internos):

```
[Perfiles] [Servicios]           ← pill tabs dentro de tab respaldo

┌─────────────────────────────────────────┐
│ Servicios Recurrentes    [+ Asociar]    │
├─────────────────────────────────────────┤
│ 📡 Internet Fibertel                    │
│    CUIT: 30-12345678-9 · Factura A     │
│    Gasto fijo: Internet ($15.200/mes)  │
│                                         │
│ 📡 Hosting AWS                          │
│    CUIT: — · Otro                      │
│    Gasto fijo: Hosting ($8.500/mes)    │
├─────────────────────────────────────────┤
│ ⚠️ Alertas (2)                          │
│ ┌─────────────────────────────────────┐ │
│ │ 🔴 Comprobante faltante            │ │
│ │    Internet - Enero 2025            │ │
│ │    [Resolver] [Descartar]           │ │
│ ├─────────────────────────────────────┤ │
│ │ 🟡 Datos incompletos               │ │
│ │    Hosting - Diciembre 2024         │ │
│ │    [Resolver] [Descartar]           │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### 3.8 Widgets de Dashboard (Mini)

En la parte superior de la tab Respaldo, un resumen compacto:

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│    12    │ │     7    │ │     2    │ │     1    │ │     1    │ │     1    │
│  Total   │ │Respaldado│ │Pot.Deduc.│ │A Revisar │ │No Resp.  │ │Registrado│
│  ⬜ slate│ │ 🟢 emrld│ │ 🟡 amber │ │ 🟠 ambDk │ │ 🔴 rose  │ │ ⬜ slate │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

**Decisión D11**: `potencialmente_deducible` se muestra como card separada (no agrupada con `a_revisar`). Justificación: son estados con semántica distinta — uno indica documentación parcialmente válida, el otro indica que se requiere acción manual. Agruparlos escondería la proporción real de cada estado y dificultaría la priorización. Se diferencian visualmente con amber-100/amber-700 (pot. deducible) vs amber-50/amber-600 (a revisar). El grid pasa a `md:grid-cols-3 lg:grid-cols-6`.

Opcionalmente, un donut chart con los porcentajes (implementable en una fase posterior con recharts si se desea).

Datos: `GET /api/v1/tax-backup/profiles/summary/` → `{ total, by_status }`.

### 3.8b Paginación del Listado

**Decisión D12**: Paginación clásica con botones Anterior/Siguiente, 50 registros por página (alineado con `TaxBackupPagination.default_limit = 50` del backend).

**Justificación**:
- **vs "Cargar más"**: Cargar más acumula DOM y dificulta volver a un registro anterior. No aporta valor en una tabla con panel de detalle lateral.
- **vs Infinite scroll**: Infinite scroll complica la interacción con el panel derecho (scroll contiende con el scroll del detail). Además requiere intersection observer — complejidad innecesaria para MVP.
- **Paginación clásica** es el patrón más simple de implementar con `LimitOffsetPagination` (ya configurada). El usuario puede saltar entre páginas. La tabla muestra `"Mostrando 1-50 de {count}"` + botones.

```tsx
{/* Footer de tabla */}
<div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 text-sm text-slate-500">
    <span>Mostrando {offset + 1}-{Math.min(offset + limit, count)} de {count}</span>
    <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={!hasPrev} onClick={goToPrev}>Anterior</Button>
        <Button variant="outline" size="sm" disabled={!hasNext} onClick={goToNext}>Siguiente</Button>
    </div>
</div>
```

Query keys incorporan offset: `['tax-backup', 'profiles', { ...filters, offset }]`.

### 3.9 Gating por Plan

```
                    ┌─────────────────┐
                    │  gastos-client   │
                    │ 4 tabs: fijos,   │
                    │ puntuales,       │
                    │ reposiciones,    │
                    │ respaldo         │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
    tab !== respaldo               tab === respaldo
              │                             │
    Componente normal              EntitlementGate
                                   entitlement="gestion.tax_backup"
                                   feature="Respaldo Impositivo"
                                   plan="Business"
                                            │
                                   ┌────────┴────────┐
                                   │                 │
                              hasEntitlement    !hasEntitlement
                                   │                 │
                           TaxBackupClient      UpgradeBlock
```

**Implementación concreta:**

```tsx
// En gastos-client.tsx — tab respaldo
{activeTab === 'respaldo' ? (
  <EntitlementGate
    entitlement="gestion.tax_backup"
    feature="Respaldo Impositivo"
    plan="Business"
    description="Gestioná el respaldo fiscal de todos tus gastos."
  >
    <TaxBackupClient canManage={canManage} />
  </EntitlementGate>
) : ...}
```

**Permisos (server side — ya resuelto):**
- `page.tsx` ya verifica `permissions.view_finance` y pasa `canManage` al cliente.
- El backend verifica `view_finance` para GET, `manage_finance` para POST/PATCH/DELETE.
- No se necesita cambio en `page.tsx`.

### 3.10 Estados UX

#### Loading
```tsx
<div className="flex justify-center p-12">
  <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
</div>
```
Se usa en: carga inicial de perfiles, carga de detail, carga de summary.

#### Empty State — Sin perfiles
```tsx
<EmptyState
  title="Aún no tenés perfiles fiscales"
  description="Creá un perfil para tus gastos y empezá a organizar tu respaldo impositivo."
  actionLabel={canManage ? "Crear primer perfil" : undefined}
  onAction={() => setIsCreateOpen(true)}
/>
```

#### Empty State — Sin documentos en un perfil
```tsx
<div className="text-center py-6 text-sm text-slate-500">
  <FileText className="h-8 w-8 mx-auto mb-2 text-slate-300" />
  <p>Sin comprobantes adjuntos</p>
  {canManage && (
    <button onClick={...} className="text-indigo-600 hover:underline mt-1 text-sm">
      Adjuntar comprobante
    </button>
  )}
</div>
```

#### Error State
```tsx
<div className="text-center py-8">
  <AlertCircle className="h-8 w-8 mx-auto mb-2 text-rose-400" />
  <p className="text-sm text-slate-600">Error al cargar los datos</p>
  <button onClick={() => refetch()} className="text-sm text-indigo-600 hover:underline mt-2">
    Reintentar
  </button>
</div>
```

#### Optimistic Updates
- Al resolver duplicado → desaparece de la lista con fade-out.
- Al subir documento → aparece en la lista inmediatamente con skeleton placeholder.

#### Mutation Loading
- Botones de submit muestran `<Loader2 className="h-4 w-4 animate-spin mr-2" />` y `disabled`.
- Mismo patrón que `ExpenseFormModal` existente.

### 3.11 Microcopy

| Contexto | Texto |
|----------|-------|
| Tab label | "Respaldo" |
| Tab label (con contador) | "Respaldo (12)" o badge numérico |
| Dashboard título | "Resumen de Respaldo Fiscal" |
| Empty state título | "Aún no tenés perfiles fiscales" |
| Empty state descripción | "Creá un perfil para tus gastos y empezá a organizar tu respaldo impositivo." |
| Botón crear | "Nuevo Perfil Fiscal" |
| Modal crear título | "Crear Perfil Fiscal" |
| Select gasto placeholder | "Seleccioná un gasto..." |
| Radio Negocio | "Negocio — Uso 100% comercial" |
| Radio Mixto | "Mixto — Uso compartido personal/comercial" |
| Radio Personal | "Personal — No vinculado al negocio" |
| Slider label | "Porcentaje de uso comercial" |
| Status: registrado | "Registrado" — slate |
| Status: respaldado | "Con respaldo fiscal" — emerald |
| Status: potencialmente_deducible | "Potencialmente deducible" — amber |
| Status: a_revisar | "Requiere revisión" — amber (dark) |
| Status: no_respaldado | "Sin respaldo fiscal" — rose |
| Asignación: business | "🏢 Negocio" |
| Asignación: mixed | "🔀 Mixto (70%)" |
| Asignación: personal | "👤 Personal" |
| Documentos header | "Comprobantes" |
| Botón adjuntar | "Adjuntar comprobante" |
| Pagos header | "Formas de pago" |
| Botón pago | "Agregar forma de pago" |
| Historial header | "Historial de estado" |
| Duplicados header | "Posibles duplicados" |
| Botón re-evaluar | "Re-evaluar" |
| Re-evaluar success toast | "Estado actualizado: {display}" |
| Re-evaluar no-change toast | "El estado no cambió" |
| Duplicado confirmar | "Es duplicado" |
| Duplicado descartar | "No es duplicado" |
| File too large | "El archivo no puede superar 10 MB" |
| File wrong type | "Solo se aceptan archivos PDF, JPG, PNG o WEBP" |
| Services tab | "Servicios" |
| Alert: missing_invoice | "Comprobante faltante" |
| Alert: incomplete_data | "Datos incompletos" |
| Alert resolver | "Resolver" |
| Alert descartar | "Descartar" |
| Upgrade block | "Respaldo Impositivo requiere plan Business" |
| Upgrade description | "Gestioná el respaldo fiscal de todos tus gastos, adjuntá comprobantes y llevá un control automático del estado impositivo." |

**Disclaimer legal** (siempre visible en el dashboard mini):
> "Este módulo organiza tu documentación fiscal con fines de orden interno. No reemplaza el asesoramiento de un contador público."

---

## 4. Riesgos UX / Técnicos

| # | Riesgo | Impacto | Mitigación |
|---|--------|---------|------------|
| R1 | Gastos sin perfil fiscal no tienen indicador visual en otras tabs | Usuario no sabe qué gastos faltan respaldar | Futuro: `ConditionalFeature` badge "sin respaldo" en cards de gastos puntuales. Fase posterior. |
| R2 | Upload de archivos grandes puede ser lento en conexiones móviles | UX frustrante | Progress bar en upload + accept attribute para validar antes de enviar. |
| R3 | Re-evaluación manual podría confundir si el estado no cambia | "¿No funcionó?" | Toast explícito "El estado no cambió — la evaluación actual es correcta." |
| R4 | 4 tabs en mobile podría ser estrecho | Overflow | Usar `overflow-x-auto` con scroll horizontal como ya existe en FinanceTabs. |
| R5 | El select de gastos en CreateProfile podría ser muy largo | UX pobre | Agregar búsqueda/filtro inline en el select. O usar combobox pattern. |
| R6 | Duplicados con falsos positivos | Ruido | UI clara: "Posible duplicado" (nunca "Es duplicado"). Fácil dismiss. |
| R7 | La sub-tab "Servicios" dentro de respaldo agrega un nivel más de navegación | Profundidad excesiva | Mantener como pill tabs simples, sin URL extra. En futuro se puede promover a tab propia. |
| R8 | `potencialmente_deducible` y `a_revisar` ambos amber puede confundir | Falta distinción | Se diferencian por tono (amber-500 vs amber-700) y texto. Suficiente para MVP. |

---

## 5. Checklist de Implementación Frontend

### Archivos a crear

- [ ] `apps/web/src/lib/api/tax-backup.ts` — API client + tipos TypeScript
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/tax-backup-client.tsx` — Componente raíz
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/tax-backup-dashboard.tsx` — Mini dashboard
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/tax-backup-table.tsx` — Tabla de perfiles
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/tax-backup-detail.tsx` — Panel de detalle
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/tax-backup-services.tsx` — Servicios + alertas
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/create-profile-modal.tsx` — Modal creación
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/document-upload.tsx` — Upload de comprobantes
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/payment-form.tsx` — Form de pago
- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/status-timeline.tsx` — Historial de estado

### Archivos a modificar

- [ ] `apps/web/src/app/app/gestion/finanzas/gastos/gastos-client.tsx` — Agregar tab "Respaldo" + import
- [ ] `apps/web/src/features/gestion/hooks.ts` — (opcional) Agregar hooks de tax-backup si se centralizan ahí

### Orden de implementación sugerido

1. **`lib/api/tax-backup.ts`** — Tipos + funciones API (sin dependencias frontend)
2. **`gastos-client.tsx`** — Agregar 4ta tab con EntitlementGate
3. **`tax-backup-client.tsx`** — Shell con layout 2-panel + empty state
4. **`create-profile-modal.tsx`** — Modal de creación
5. **`tax-backup-table.tsx`** — Tabla de listado con filters
6. **`tax-backup-dashboard.tsx`** — Contadores de summary
7. **`tax-backup-detail.tsx`** — Panel de detalle completo
8. **`document-upload.tsx`** — Upload de comprobantes
9. **`payment-form.tsx`** — Form de pago
10. **`status-timeline.tsx`** — Timeline de historial
11. **`tax-backup-services.tsx`** — Servicios recurrentes + alertas

---

## 6. Ejemplos de Componentes, Props y Pseudocódigo

### 6.1 API Client — `lib/api/tax-backup.ts`

```ts
import { apiGet, apiPost, apiPatch, apiDelete } from './client';

// ── Types ────────────────────────────────────────────────────────────────

export type TaxStatus = 'registrado' | 'respaldado' | 'potencialmente_deducible' | 'a_revisar' | 'no_respaldado_fiscalmente';
export type AllocationType = 'business' | 'mixed' | 'personal';
export type DocumentType = 'factura' | 'recibo' | 'ticket' | 'nota_credito' | 'nota_debito' | 'otro';
export type PaymentMethod = 'cash' | 'transfer' | 'card' | 'mercadopago' | 'check' | 'other';
export type AlertStatus = 'open' | 'resolved' | 'dismissed';
export type DuplicateStatus = 'pending' | 'confirmed_duplicate' | 'dismissed';

export interface FiscalProfile {
  id: number;
  expense: number;
  expense_name: string;
  expense_amount: string;
  expense_status: string;
  expense_due_date: string;
  tax_status: TaxStatus;
  tax_status_display: string;
  allocation_type: AllocationType;
  allocation_type_display: string;
  business_use_percentage: number;
  review_reason: string | null;
  notes: string;
  doc_count: number;
  created_at: string;
  updated_at: string;
}

export interface FiscalProfileDetail extends FiscalProfile {
  documents: FiscalDocument[];
  payment_details: PaymentDetail[];
  status_logs: StatusLog[];
}

export interface FiscalDocument {
  id: number;
  document_type: DocumentType;
  issuer_name: string;
  issuer_tax_id: string;
  invoice_number: string;
  issue_date: string | null;
  total: string | null;
  is_fiscal_document: boolean;
  file: string;
  created_at: string;
}

export interface PaymentDetail {
  id: number;
  payment_method: PaymentMethod;
  reference: string;
  proof_file: string | null;
  created_at: string;
}

export interface StatusLog {
  id: number;
  previous_status: TaxStatus;
  new_status: TaxStatus;
  rule_code: string;
  note: string;
  created_at: string;
}

export interface RecurringService {
  id: number;
  fixed_expense: number;
  service_name: string;
  provider_tax_id: string;
  expected_document_type: DocumentType;
  is_active: boolean;
  created_at: string;
}

export interface ServiceAlert {
  id: number;
  service_profile: number;
  alert_type: 'missing_invoice' | 'incomplete_data';
  status: AlertStatus;
  message: string;
  resolved_at: string | null;
  created_at: string;
}

export interface DuplicateFlag {
  id: number;
  profile_a: number;
  profile_b: number;
  match_type: string;
  status: DuplicateStatus;
  resolved_by: number | null;
  resolved_at: string | null;
}

export interface TaxBackupSummary {
  total: number;
  by_status: Record<TaxStatus, number>;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Query key factory ────────────────────────────────────────────────────

export const taxBackupKeys = {
  all: ['tax-backup'] as const,
  profiles: (filters?: Record<string, string>) => ['tax-backup', 'profiles', filters] as const,
  profile: (id: number) => ['tax-backup', 'profiles', id] as const,
  summary: () => ['tax-backup', 'summary'] as const,
  services: () => ['tax-backup', 'services'] as const,
  alerts: (filters?: Record<string, string>) => ['tax-backup', 'alerts', filters] as const,
  duplicates: () => ['tax-backup', 'duplicates'] as const,
};

// ── API Functions ────────────────────────────────────────────────────────

const BASE = '/api/v1/tax-backup';

export function listProfiles(params: { tax_status?: string; allocation_type?: string; search?: string; limit?: number; offset?: number } = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') qs.append(k, String(v)); });
  return apiGet<PaginatedResponse<FiscalProfile>>(`${BASE}/profiles/?${qs}`);
}

export function getProfile(id: number) {
  return apiGet<FiscalProfileDetail>(`${BASE}/profiles/${id}/`);
}

export function createProfile(data: { expense: number; allocation_type: AllocationType; business_use_percentage?: number; notes?: string }) {
  return apiPost<FiscalProfileDetail>(`${BASE}/profiles/`, data);
}

export function updateProfile(id: number, data: Partial<{ allocation_type: AllocationType; business_use_percentage: number; notes: string }>) {
  return apiPatch<FiscalProfileDetail>(`${BASE}/profiles/${id}/`, data);
}

export function getProfileSummary() {
  return apiGet<TaxBackupSummary>(`${BASE}/profiles/summary/`);
}

export function reEvaluateProfile(id: number) {
  return apiPost<{ tax_status: string; tax_status_display: string; duplicates_found: number }>(`${BASE}/profiles/${id}/re-evaluate/`, {});
}

// Documents
export function listDocuments(profileId: number) {
  return apiGet<FiscalDocument[]>(`${BASE}/profiles/${profileId}/documents/`);
}

export function uploadDocument(profileId: number, formData: FormData) {
  return apiPost<FiscalDocument>(`${BASE}/profiles/${profileId}/documents/`, formData);
}

export function deleteDocument(profileId: number, docId: number) {
  return apiDelete(`${BASE}/profiles/${profileId}/documents/${docId}/`);
}

// Payments
export function listPayments(profileId: number) {
  return apiGet<PaymentDetail[]>(`${BASE}/profiles/${profileId}/payments/`);
}

export function addPayment(profileId: number, data: FormData | { payment_method: PaymentMethod; reference?: string }) {
  return apiPost<PaymentDetail>(`${BASE}/profiles/${profileId}/payments/`, data);
}

// Status log
export function getStatusLog(profileId: number) {
  return apiGet<StatusLog[]>(`${BASE}/profiles/${profileId}/status-log/`);
}

// Services
export function listServices() {
  return apiGet<PaginatedResponse<RecurringService>>(`${BASE}/services/`);
}

export function createService(data: { fixed_expense: number; service_name: string; provider_tax_id?: string; expected_document_type?: DocumentType }) {
  return apiPost<RecurringService>(`${BASE}/services/`, data);
}

export function updateService(id: number, data: Partial<RecurringService>) {
  return apiPatch<RecurringService>(`${BASE}/services/${id}/`, data);
}

// Alerts
export function listAlerts(params: { status?: string } = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v) qs.append(k, v); });
  return apiGet<PaginatedResponse<ServiceAlert>>(`${BASE}/alerts/?${qs}`);
}

export function resolveAlert(id: number, status: 'resolved' | 'dismissed') {
  return apiPatch<ServiceAlert>(`${BASE}/alerts/${id}/`, { status });
}

// Duplicates
export function listDuplicates() {
  return apiGet<PaginatedResponse<DuplicateFlag>>(`${BASE}/duplicates/`);
}

export function resolveDuplicate(id: number, status: 'confirmed_duplicate' | 'dismissed') {
  return apiPatch<DuplicateFlag>(`${BASE}/duplicates/${id}/`, { status });
}
```

### 6.2 gastos-client.tsx — Modificación (diff conceptual)

```tsx
// ANTES: type GastosTab = 'fijos' | 'puntuales' | 'reposiciones';
// DESPUÉS:
type GastosTab = 'fijos' | 'puntuales' | 'reposiciones' | 'respaldo';

// Importar:
import { EntitlementGate } from '@/components/gestion/entitlement-gate';
import { TaxBackupClient } from './tax-backup/tax-backup-client';

// Agregar botón en el flex gap-1 p-1:
<button
    onClick={() => setTab('respaldo')}
    className={cn(
        'px-5 py-2 text-sm font-medium rounded-lg transition-all',
        activeTab === 'respaldo'
            ? 'bg-white text-emerald-700 shadow-sm'
            : 'text-slate-500 hover:text-slate-900'
    )}
>
    Respaldo
</button>

// Agregar case en el render:
{activeTab === 'respaldo' ? (
    <EntitlementGate
        entitlement="gestion.tax_backup"
        feature="Respaldo Impositivo"
        plan="Business"
        description="Gestioná el respaldo fiscal de todos tus gastos."
    >
        <TaxBackupClient canManage={canManage} />
    </EntitlementGate>
) : activeTab === 'fijos' ? (
    // ... existing
```

### 6.3 TaxBackupClient — Componente Raíz

```tsx
"use client";

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Loader2, Plus, Shield } from 'lucide-react';
import { cn } from '@/lib/utils';

import { listProfiles, getProfileSummary, taxBackupKeys, FiscalProfile } from '@/lib/api/tax-backup';
import { Button } from '@/components/ui/button';
import { EmptyState } from '../../components/empty-state';
import { TaxBackupDashboard } from './tax-backup-dashboard';
import { TaxBackupTable } from './tax-backup-table';
import { TaxBackupDetail } from './tax-backup-detail';
import { TaxBackupServices } from './tax-backup-services';
import { CreateProfileModal } from './create-profile-modal';

type SubTab = 'perfiles' | 'servicios';

interface Props { canManage: boolean }

export function TaxBackupClient({ canManage }: Props) {
    const [subTab, setSubTab] = useState<SubTab>('perfiles');
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [filters, setFilters] = useState<Record<string, string>>({});

    const { data: profilesData, isLoading } = useQuery({
        queryKey: taxBackupKeys.profiles(filters),
        queryFn: () => listProfiles(filters),
    });

    const { data: summary } = useQuery({
        queryKey: taxBackupKeys.summary(),
        queryFn: getProfileSummary,
    });

    if (isLoading) {
        return (
            <div className="flex justify-center p-12">
                <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            </div>
        );
    }

    const profiles = profilesData?.results ?? [];
    const selectedProfile = profiles.find(p => p.id === selectedId) ?? null;

    return (
        <div className="space-y-6">
            {/* Disclaimer */}
            <p className="text-xs text-slate-400 flex items-center gap-1">
                <Shield className="h-3 w-3" />
                Este módulo organiza tu documentación fiscal con fines de orden interno. No reemplaza el asesoramiento de un contador público.
            </p>

            {/* Sub-tabs: Perfiles / Servicios */}
            <div className="flex items-center justify-between">
                <div className="flex gap-1 p-1 bg-slate-100 rounded-lg w-fit">
                    <button
                        onClick={() => setSubTab('perfiles')}
                        className={cn(
                            'px-4 py-2 text-sm font-medium rounded-md transition-all',
                            subTab === 'perfiles' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'
                        )}
                    >
                        Perfiles Fiscales
                    </button>
                    <button
                        onClick={() => setSubTab('servicios')}
                        className={cn(
                            'px-4 py-2 text-sm font-medium rounded-md transition-all',
                            subTab === 'servicios' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'
                        )}
                    >
                        Servicios
                    </button>
                </div>

                {subTab === 'perfiles' && canManage && (
                    <Button onClick={() => setIsCreateOpen(true)} className="rounded-full">
                        <Plus className="mr-2 h-4 w-4" />
                        Nuevo Perfil Fiscal
                    </Button>
                )}
            </div>

            {subTab === 'perfiles' ? (
                profiles.length === 0 && !Object.keys(filters).length ? (
                    <EmptyState
                        title="Aún no tenés perfiles fiscales"
                        description="Creá un perfil para tus gastos y empezá a organizar tu respaldo impositivo."
                        actionLabel={canManage ? 'Crear primer perfil' : undefined}
                        onAction={() => setIsCreateOpen(true)}
                    />
                ) : (
                    <>
                        {summary && <TaxBackupDashboard summary={summary} />}

                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            {/* Left: Table */}
                            <div className="lg:col-span-2">
                                <TaxBackupTable
                                    profiles={profiles}
                                    selectedId={selectedId}
                                    onSelect={setSelectedId}
                                    filters={filters}
                                    onFiltersChange={setFilters}
                                />
                            </div>
                            {/* Right: Detail */}
                            <div className="lg:col-span-1">
                                {selectedProfile ? (
                                    <TaxBackupDetail
                                        profileId={selectedProfile.id}
                                        canManage={canManage}
                                    />
                                ) : (
                                    <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-sm text-slate-500">
                                        Seleccioná un perfil para ver el detalle
                                    </div>
                                )}
                            </div>
                        </div>
                    </>
                )
            ) : (
                <TaxBackupServices canManage={canManage} />
            )}

            {isCreateOpen && (
                <CreateProfileModal
                    isOpen={isCreateOpen}
                    onClose={() => setIsCreateOpen(false)}
                    onCreated={(profile) => {
                        setIsCreateOpen(false);
                        setSelectedId(profile.id);
                    }}
                />
            )}
        </div>
    );
}
```

### 6.4 TaxStatusBadge — Componente auxiliar

```tsx
import { cn } from '@/lib/utils';
import type { TaxStatus } from '@/lib/api/tax-backup';

const STATUS_CONFIG: Record<TaxStatus, { label: string; bg: string; text: string }> = {
    registrado:                 { label: 'Registrado',              bg: 'bg-slate-100',  text: 'text-slate-700'  },
    respaldado:                 { label: 'Con respaldo fiscal',     bg: 'bg-emerald-100',text: 'text-emerald-700'},
    potencialmente_deducible:   { label: 'Potencialmente deducible',bg: 'bg-amber-100',  text: 'text-amber-700'  },
    a_revisar:                  { label: 'Requiere revisión',       bg: 'bg-amber-50',   text: 'text-amber-600'  },
    no_respaldado_fiscalmente:  { label: 'Sin respaldo fiscal',     bg: 'bg-rose-100',   text: 'text-rose-700'   },
};

export function TaxStatusBadge({ status }: { status: TaxStatus }) {
    const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.registrado;
    return (
        <span className={cn('text-xs px-2 py-1 rounded-full font-medium', config.bg, config.text)}>
            {config.label}
        </span>
    );
}
```

### 6.5 TaxBackupDashboard — Mini dashboard

```tsx
import { TaxBackupSummary } from '@/lib/api/tax-backup';
import { cn } from '@/lib/utils';

const STAT_CARDS = [
    { key: 'total',                       label: 'Total',               color: 'bg-slate-900 text-white',       textColor: 'text-slate-300' },
    { key: 'respaldado',                  label: 'Con respaldo',        color: 'bg-emerald-50 border-emerald-200', textColor: 'text-emerald-600' },
    { key: 'potencialmente_deducible',    label: 'Pot. deducible',      color: 'bg-amber-50 border-amber-200',    textColor: 'text-amber-700'   },
    { key: 'a_revisar',                   label: 'A revisar',           color: 'bg-amber-50 border-amber-300',    textColor: 'text-amber-600'   },
    { key: 'no_respaldado_fiscalmente',   label: 'Sin respaldo',        color: 'bg-rose-50 border-rose-200',      textColor: 'text-rose-600'    },
    { key: 'registrado',                  label: 'Registrado',          color: 'bg-slate-50 border-slate-200',    textColor: 'text-slate-600'   },
] as const;

export function TaxBackupDashboard({ summary }: { summary: TaxBackupSummary }) {
    return (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {STAT_CARDS.map((card) => {
                const count = card.key === 'total'
                    ? summary.total
                    : (summary.by_status[card.key as keyof typeof summary.by_status] ?? 0);
                return (
                    <div key={card.key} className={cn('rounded-2xl border p-4 text-center', card.color)}>
                        <div className="text-2xl font-bold font-mono">{count}</div>
                        <div className={cn('text-xs font-medium mt-1', card.textColor)}>{card.label}</div>
                    </div>
                );
            })}
        </div>
    );
}
```

### 6.6 TaxBackupTable — Pseudocódigo

```tsx
export function TaxBackupTable({ profiles, selectedId, onSelect, filters, onFiltersChange }: {
    profiles: FiscalProfile[];
    selectedId: number | null;
    onSelect: (id: number) => void;
    filters: Record<string, string>;
    onFiltersChange: (f: Record<string, string>) => void;
}) {
    const [search, setSearch] = useState(filters.search ?? '');

    // Debounce search
    useEffect(() => {
        const t = setTimeout(() => onFiltersChange({ ...filters, search }), 300);
        return () => clearTimeout(t);
    }, [search]);

    return (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm">
            {/* Toolbar: search + filter selects */}
            <div className="p-4 border-b border-slate-100 flex flex-wrap gap-3">
                <input type="search" placeholder="Buscar gasto..." value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="flex-1 min-w-[200px] rounded-md border-slate-300 p-2 text-sm border" />
                <select value={filters.tax_status ?? ''} onChange={e => onFiltersChange({ ...filters, tax_status: e.target.value })}
                    className="rounded-md border-slate-300 p-2 text-sm border">
                    <option value="">Todos los estados</option>
                    <option value="registrado">Registrado</option>
                    <option value="respaldado">Con respaldo</option>
                    <option value="a_revisar">A revisar</option>
                    <option value="no_respaldado_fiscalmente">Sin respaldo</option>
                    <option value="potencialmente_deducible">Pot. deducible</option>
                </select>
                <select value={filters.allocation_type ?? ''} onChange={e => onFiltersChange({ ...filters, allocation_type: e.target.value })}
                    className="rounded-md border-slate-300 p-2 text-sm border">
                    <option value="">Toda asignación</option>
                    <option value="business">Negocio</option>
                    <option value="mixed">Mixto</option>
                    <option value="personal">Personal</option>
                </select>
            </div>

            {/* Table */}
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-slate-100 text-left text-xs text-slate-500 uppercase tracking-wider">
                        <th className="px-4 py-3">Gasto</th>
                        <th className="px-4 py-3 text-right">Monto</th>
                        <th className="px-4 py-3">Estado</th>
                        <th className="px-4 py-3">Asignación</th>
                        <th className="px-4 py-3 text-center">Docs</th>
                    </tr>
                </thead>
                <tbody>
                    {profiles.map(p => (
                        <tr key={p.id}
                            onClick={() => onSelect(p.id)}
                            className={cn(
                                'border-b border-slate-50 cursor-pointer transition-colors',
                                selectedId === p.id ? 'bg-slate-50' : 'hover:bg-slate-50/50'
                            )}>
                            <td className="px-4 py-3 font-medium text-slate-900">{p.expense_name}</td>
                            <td className="px-4 py-3 text-right font-mono"><Currency amount={p.expense_amount} /></td>
                            <td className="px-4 py-3"><TaxStatusBadge status={p.tax_status} /></td>
                            <td className="px-4 py-3 text-slate-600">{p.allocation_type_display}</td>
                            <td className="px-4 py-3 text-center text-slate-500">{p.doc_count}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
```

### 6.7 CreateProfileModal — Pseudocódigo

```tsx
export function CreateProfileModal({ isOpen, onClose, onCreated }: {
    isOpen: boolean;
    onClose: () => void;
    onCreated: (profile: FiscalProfileDetail) => void;
}) {
    const queryClient = useQueryClient();
    const [expense, setExpense] = useState('');
    const [allocationType, setAllocationType] = useState<AllocationType>('business');
    const [businessPct, setBusinessPct] = useState(50);
    const [notes, setNotes] = useState('');

    // Fetch expenses that don't have a fiscal profile yet
    const { data: expenses } = useQuery({
        queryKey: ['treasury', 'expenses', 'without-profile'],
        queryFn: () => listExpenses({ limit: 200 }),
        // NOTE: backend should ideally provide a filter like ?has_fiscal_profile=false
        // Fallback: filter client-side by cross-referencing with profiles
    });

    const createMutation = useMutation({
        mutationFn: createProfile,
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: taxBackupKeys.all });
            onCreated(data);
        },
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createMutation.mutate({
            expense: Number(expense),
            allocation_type: allocationType,
            business_use_percentage: allocationType === 'mixed' ? businessPct : allocationType === 'business' ? 100 : 0,
            notes,
        });
    };

    return (
        <Modal open={isOpen} onClose={onClose} title="Crear Perfil Fiscal">
            <form onSubmit={handleSubmit} className="space-y-4">
                {/* Expense selector */}
                <div>
                    <label className="block text-sm font-medium text-slate-700">Gasto asociado</label>
                    <select required value={expense} onChange={e => setExpense(e.target.value)}
                        className="mt-1 block w-full rounded-md border p-2 text-sm border-slate-300">
                        <option value="">Seleccioná un gasto...</option>
                        {/* expenses filtered to those without fiscal_profile */}
                    </select>
                </div>

                {/* Allocation type radios */}
                <fieldset>
                    <legend className="text-sm font-medium text-slate-700 mb-2">Tipo de asignación</legend>
                    {(['business', 'mixed', 'personal'] as const).map(type => (
                        <label key={type} className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 mb-2 cursor-pointer hover:bg-slate-50">
                            <input type="radio" name="allocation" value={type} checked={allocationType === type}
                                onChange={() => setAllocationType(type)}
                                className="mt-0.5" />
                            <div>
                                <span className="font-medium text-slate-900">
                                    {type === 'business' ? 'Negocio' : type === 'mixed' ? 'Mixto' : 'Personal'}
                                </span>
                                <p className="text-xs text-slate-500">
                                    {type === 'business' ? 'Uso 100% comercial'
                                        : type === 'mixed' ? 'Uso compartido personal/comercial'
                                        : 'No vinculado al negocio'}
                                </p>
                            </div>
                        </label>
                    ))}
                </fieldset>

                {/* Mixed % slider */}
                {allocationType === 'mixed' && (
                    <div>
                        <label className="block text-sm font-medium text-slate-700">
                            Porcentaje de uso comercial: <span className="font-mono">{businessPct}%</span>
                        </label>
                        <input type="range" min={10} max={90} step={5} value={businessPct}
                            onChange={e => setBusinessPct(Number(e.target.value))}
                            className="mt-2 w-full" />
                        <div className="flex justify-between text-xs text-slate-400 mt-1">
                            <span>10% negocio</span>
                            <span>90% negocio</span>
                        </div>
                    </div>
                )}

                {/* Notes */}
                <div>
                    <label className="block text-sm font-medium text-slate-700">Notas (opcional)</label>
                    <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} maxLength={500}
                        className="mt-1 block w-full rounded-md border p-2 text-sm border-slate-300"
                        placeholder="Observaciones internas..." />
                </div>

                <div className="flex justify-end gap-2 pt-4">
                    <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button type="submit" disabled={createMutation.isPending}>
                        {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Crear Perfil
                    </Button>
                </div>
            </form>
        </Modal>
    );
}
```

### 6.8 StatusTimeline — Pseudocódigo

```tsx
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import type { StatusLog } from '@/lib/api/tax-backup';
import { TaxStatusBadge } from './tax-status-badge';

export function StatusTimeline({ logs }: { logs: StatusLog[] }) {
    if (!logs.length) return null;

    // Ordenar más reciente primero
    const sorted = [...logs].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

    return (
        <div className="space-y-3">
            {sorted.map((log, i) => (
                <div key={log.id} className="flex gap-3">
                    <div className="flex flex-col items-center">
                        <div className={`w-2.5 h-2.5 rounded-full mt-1.5 ${i === 0 ? 'bg-slate-900' : 'bg-slate-300'}`} />
                        {i < sorted.length - 1 && <div className="w-px flex-1 bg-slate-200 mt-1" />}
                    </div>
                    <div className="pb-4">
                        <div className="flex items-center gap-2 text-sm">
                            <TaxStatusBadge status={log.previous_status} />
                            <span className="text-slate-400">→</span>
                            <TaxStatusBadge status={log.new_status} />
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                            {format(new Date(log.created_at), "dd/MM/yyyy HH:mm", { locale: es })}
                            {log.rule_code && <> · Regla: <code className="text-xs bg-slate-100 px-1 rounded">{log.rule_code}</code></>}
                        </p>
                        {log.note && <p className="text-xs text-slate-400 mt-0.5 italic">{log.note}</p>}
                    </div>
                </div>
            ))}
        </div>
    );
}
```

### 6.9 DocumentUpload — Pseudocódigo

```tsx
export function DocumentUpload({ profileId, canManage, onUploaded }: {
    profileId: number; canManage: boolean; onUploaded: () => void;
}) {
    const [isFormOpen, setIsFormOpen] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [docType, setDocType] = useState<DocumentType>('factura');
    const [isFiscal, setIsFiscal] = useState(true);
    const [issuerName, setIssuerName] = useState('');
    const [issuerTaxId, setIssuerTaxId] = useState('');
    const [invoiceNumber, setInvoiceNumber] = useState('');
    const [issueDate, setIssueDate] = useState('');
    const [total, setTotal] = useState('');

    const uploadMutation = useMutation({
        mutationFn: (formData: FormData) => uploadDocument(profileId, formData),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: taxBackupKeys.profile(profileId) });
            queryClient.invalidateQueries({ queryKey: taxBackupKeys.summary() });
            resetForm();
            onUploaded();
        },
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!file) return;

        // Client-side validation
        if (file.size > 10 * 1024 * 1024) { /* show error */ return; }
        const validTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
        if (!validTypes.includes(file.type)) { /* show error */ return; }

        const fd = new FormData();
        fd.append('file', file);
        fd.append('document_type', docType);
        fd.append('is_fiscal_document', String(isFiscal));
        if (issuerName) fd.append('issuer_name', issuerName);
        if (issuerTaxId) fd.append('issuer_tax_id', issuerTaxId);
        if (invoiceNumber) fd.append('invoice_number', invoiceNumber);
        if (issueDate) fd.append('issue_date', issueDate);
        if (total) fd.append('total', total);

        uploadMutation.mutate(fd);
    };

    // Render: file drop zone + expandable inline form
    // ...
}
```

---

## 7. Próximo Paso Recomendado

**Cierre de Fase 4**: Una vez aprobadas estas correcciones, la Fase 4 (Diseño Frontend) queda cerrada.

**Fase 5 — Generación de Código Frontend.** Implementar los archivos en el orden listado en §5:

1. `lib/api/tax-backup.ts` (tipos + API client)
2. Modificar `gastos-client.tsx` (4ta tab)
3. `tax-backup-client.tsx` (shell + layout 2-panel)
4. `create-profile-modal.tsx`
5. `tax-backup-table.tsx` + `TaxStatusBadge` + paginación
6. `tax-backup-dashboard.tsx` (6 stat cards)
7. `tax-backup-detail.tsx` + sub-components
8. `tax-backup-services.tsx`

Cada archivo se valida incrementalmente con el dev server. La EntitlementGate actúa como control de visibilidad natural durante desarrollo (solo visible con plan Business).

---

## Apéndice: Query Keys Reference

```
['tax-backup', 'profiles', {filters}]  — listado
['tax-backup', 'profiles', id]          — detalle
['tax-backup', 'summary']               — dashboard counters
['tax-backup', 'services']              — servicios recurrentes
['tax-backup', 'alerts', {filters}]     — alertas
['tax-backup', 'duplicates']            — flags de duplicados
```

Invalidation on mutations:
- Create/Update profile → invalidate `['tax-backup']` (all)
- Upload document → invalidate `['tax-backup', 'profiles', id]` + `['tax-backup', 'summary']`
- Delete document → same
- Add payment → invalidate `['tax-backup', 'profiles', id]`
- Re-evaluate → invalidate `['tax-backup', 'profiles', id]` + `['tax-backup', 'summary']`
- Resolve duplicate → invalidate `['tax-backup', 'duplicates']`
- Resolve alert → invalidate `['tax-backup', 'alerts']`
