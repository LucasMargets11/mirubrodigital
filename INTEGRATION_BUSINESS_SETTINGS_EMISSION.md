# Integración de Business Settings en Emisión de Documentos

## 🎯 Objetivo

Centralizar la configuración de datos fiscales del negocio (BillingProfile) y series de documentos (DocumentSeries) en todos los flujos de emisión de facturas, presupuestos y otros comprobantes.

**Cambios principales:**
- ✅ Ningún modal/form pide datos del emisor (razón social, CUIT, dirección)
- ✅ Los datos del emisor vienen desde **BillingProfile**
- ✅ Cada documento usa la **serie default** configurada en DocumentSeries
- ✅ Si BillingProfile está incompleto → **Bloquea emisión** + CTA para completar datos

---

## 📁 Archivos Modificados

### Frontend - Emisión de Facturas (2 componentes)

#### 1. `apps/web/src/components/invoicing/invoice-actions.tsx`
**Ubicación:** Componente genérico usado en órdenes y ventas  
**Cambios:**
- ✅ Importa `useBusinessBillingProfileQuery` y `useDocumentSeriesQuery`
- ✅ Valida `billingProfile.is_complete` antes de habilitar emisión
- ✅ Filtra series por `document_type='invoice'` y `is_active=true`
- ✅ Auto-selecciona serie con `is_default=true`
- ✅ Muestra sección read-only "Emisor" con datos del BillingProfile
- ✅ Bloquea botón si `!isProfileComplete`
- ✅ Agrega banner de error con link a `/app/gestion/configuracion/negocio`

**Modal antes:**
```tsx
// Pedía manualmente:
- Serie (select)
- Nombre o razón social (input)
- CUIT / Documento (input)
- Dirección (input)
```

**Modal después:**
```tsx
// Ahora muestra:
- [Read-only] Emisor:
  - Razón social: {billingProfile.legal_name}
  - CUIT: {billingProfile.tax_id}
  - Dirección: {billingProfile.commercial_address}
  
- Serie (select con series de tipo INVOICE)
  - Auto-seleccionada la default con ⭐
  - Formato: "INVOICE A - FAC (PV 0001 - Próx: #00000023)"
  
- Nombre del cliente (input)
- CUIT del cliente (input)
- Dirección del cliente (input)
```

**Bloqueo de emisión:**
```tsx
// Si !isProfileComplete:
disabled={!canIssue || !isProfileComplete}

// Banner mostrado:
⛔ Perfil fiscal incompleto
Completá los datos de tu negocio para emitir facturas.
[Completar datos del negocio →] // Link a /configuracion/negocio
```

---

#### 2. `apps/web/src/app/app/gestion/ventas/invoice-actions.tsx`
**Ubicación:** Componente específico de ventas  
**Cambios:** Idénticos a `components/invoicing/invoice-actions.tsx`

**Diferencias menores:**
- Solo maneja ventas (no órdenes)
- Texto del botón: `"Perfil incompleto"` cuando está disabled

---

### Frontend - Emisión de Presupuestos

#### 3. `apps/web/src/app/app/gestion/ventas/presupuestos/nuevo/new-quote-client.tsx`
**Ubicación:** Form completo de creación de presupuestos  
**Cambios:**
- ✅ Importa `useBusinessBillingProfileQuery` y `useDocumentSeriesQuery`
- ✅ Valida `billingProfile.is_complete` antes de habilitar submit
- ✅ Filtra series por `document_type='quote'` y `is_active=true`
- ✅ Auto-selecciona serie con `is_default=true`
- ✅ Agrega selector de serie obligatorio
- ✅ Agrega sección "Emisor" (read-only) con fondo verde
- ✅ Agrega banner de advertencia si perfil incompleto
- ✅ Deshabilita botón "Guardar presupuesto" si `!isProfileComplete`
- ✅ Envía `document_series_id` en el payload

**Nuevo flujo de validación:**
```tsx
// handleSubmit ahora valida:
1. if (!isProfileComplete) → Error + link
2. if (cart.length === 0) → Error
3. if (!selectedCustomer && !customerName) → Error
4. if (!selectedSeriesId) → Error
5. Crear presupuesto
```

**Nueva sección agregada:**
```tsx
{/* Banner de advertencia */}
{!isProfileComplete && (
  <div className="rounded-2xl border-amber bg-amber">
    ⚠️ Perfil fiscal incompleto
    Completá los datos de tu negocio para crear presupuestos.
    [Ir a configuración →]
  </div>
)}

{/* Emisor (solo si completo) */}
{billingProfile && isProfileComplete && (
  <div className="border-emerald bg-emerald">
    <h3>Emisor</h3>
    ✓ Razón social: {billingProfile.legal_name}
    ✓ CUIT: {billingProfile.tax_id}
    ✓ Dirección: {billingProfile.commercial_address}
  </div>
)}

{/* Serie del presupuesto (solo si completo) */}
{isProfileComplete && (
  <select>
    {quoteSeries.map(serie => (
      <option>
        QUOTE P - PRE (PV 0001 - Próx: #00000001) ⭐
      </option>
    ))}
  </select>
)}
```

**Payload actualizado:**
```typescript
const payload: QuotePayload = {
  customer_id: selectedCustomer?.id ?? null,
  customer_name: customerName.trim() || undefined,
  // ... otros campos
  document_series_id: selectedSeriesId || undefined, // ← NUEVO
  items: [...]
};
```

---

### Frontend - Tipos

#### 4. `apps/web/src/features/gestion/types.ts`
**Cambio:**
```typescript
export type QuotePayload = {
  // ... campos existentes
  document_series_id?: string; // ← AGREGADO
  items: QuoteItemPayload[];
};
```

---

## 🔄 Flujo de Uso Integrado

### Para Facturas

1. **Usuario hace clic en "Generar factura"**
2. **Sistema valida:**
   - ¿`billingProfile.is_complete === true`?
     - ❌ NO → Deshabilita botón + muestra CTA "Completar datos del negocio"
     - ✅ SÍ → Abre modal

3. **En el modal:**
   - Muestra sección "Emisor" (read-only) con datos del BillingProfile
   - Pre-carga serie default de tipo INVOICE
   - Usuario solo completa:
     - Nombre del cliente (opcional)
     - CUIT del cliente (opcional)
     - Dirección del cliente (opcional)

4. **Al confirmar:**
   - Envía `series_code` (ID de la serie seleccionada)
   - Backend usa BillingProfile automáticamente
   - Backend incrementa `next_number` de la serie atómicamente

---

### Para Presupuestos

1. **Usuario entra a "Nuevo presupuesto"**
2. **Sistema valida:**
   - ¿`billingProfile.is_complete === true`?
     - ❌ NO → Muestra banner amarillo + CTA + deshabilita submit
     - ✅ SÍ → Muestra sección verde "Emisor" + selector de serie

3. **En el form:**
   - Muestra datos del emisor (read-only)
   - Selector de serie de presupuestos (auto-seleccionada la default)
   - Usuario completa:
     - Cliente
     - Ítems del presupuesto
     - Válido hasta (opcional)
     - Notas/términos (opcional)

4. **Al guardar:**
   - Envía `document_series_id` en el payload
   - Backend crea presupuesto con la serie especificada
   - Backend incrementa `next_number` de la serie

---

## 🧪 Checklist de Testing Manual

### Test 1: Factura con perfil completo ✅
**Precondición:** BillingProfile.is_complete = true

1. Ir a una venta sin factura
2. Click "Generar factura"
3. **Verificar:**
   - ✅ Modal se abre
   - ✅ Sección "Emisor" muestra:
     - Razón social correcta
     - CUIT correcto
     - Dirección correcta
   - ✅ Serie pre-seleccionada (la default con ⭐)
   - ✅ Opciones muestran: "INVOICE A - FAC (PV 0001 - Próx: #00000023)"
4. Completar datos del cliente (opcional)
5. Click "Confirmar emisión"
6. **Verificar:**
   - ✅ Factura creada exitosamente
   - ✅ PDF generado con datos del emisor
   - ✅ Serie incrementa `next_number`

---

### Test 2: Factura sin perfil completo 🚫
**Precondición:** BillingProfile.is_complete = false (falta campo obligatorio)

1. Ir a una venta sin factura
2. **Verificar:**
   - ✅ Botón "Generar factura" está disabled
   - ✅ Banner rojo debajo muestra:
     - "⛔ Perfil fiscal incompleto"
     - "Completá los datos de tu negocio para emitir facturas."
     - Link "Completar datos del negocio →"
3. Click en el link
4. **Verificar:**
   - ✅ Redirige a `/app/gestion/configuracion/negocio`
   - ✅ Tab "Perfil Fiscal" está activo
   - ✅ Banner amarillo muestra "⚠️ Completá los campos obligatorios"

---

### Test 3: Presupuesto con perfil completo ✅
**Precondición:** BillingProfile.is_complete = true + Serie de QUOTE configurada

1. Ir a "Nuevo presupuesto"
2. **Verificar:**
   - ✅ No hay banner de advertencia amarillo
   - ✅ Sección "Emisor"Visible (fondo verde) con:
     - ✓ Razón social
     - ✓ CUIT
     - ✓ Dirección
   - ✅ Selector "Serie del presupuesto" visible con opciones
   - ✅ Serie default pre-seleccionada con ⭐
3. Agregar cliente + ítems
4. Click "Guardar presupuesto"
5. **Verificar:**
   - ✅ Presupuesto creado con serie correcta
   - ✅ Serie incrementa `next_number`

---

### Test 4: Presupuesto sin perfil completo 🚫
**Precondición:** BillingProfile.is_complete = false

1. Ir a "Nuevo presupuesto"
2. **Verificar:**
   - ✅ Banner amarillo en la parte superior:
     - "⚠️ Perfil fiscal incompleto"
     - "Completá los datos de tu negocio para crear presupuestos."
     - Link "Ir a configuración →"
   - ✅ NO se muestra sección "Emisor"
   - ✅ NO se muestra selector de serie
   - ✅ Botón "Guardar presupuesto" está disabled
3. Intentar agregar ítems y guardar
4. **Verificar:**
   - ✅ Submit bloqueado
   - ✅ Error: "Tu perfil fiscal está incompleto. Completá los datos antes de crear presupuestos."
5. Click en link "Ir a configuración"
6. **Verificar:**
   - ✅ Redirige a `/app/gestion/configuracion/negocio`

---

### Test 5: Series - Establecer default y verificar pre-carga
**Objetivo:** Comprobar que al cambiar la serie default, se pre-selecciona correctamente

1. Ir a `/app/gestion/configuracion/negocio`
2. Tab "Series de Documentos"
3. Crear 2 series de INVOICE:
   - INVOICE A - PV 0001 (Default ✓)
   - INVOICE B - PV 0001
4. Establecer B como default (click "Establecer default")
5. **Verificar:**
   - ✅ Badge "Default" se mueve de A a B
6. Ir a una venta → "Generar factura"
7. **Verificar:**
   - ✅ Serie B está pre-seleccionada (la nueva default con ⭐)
   - ✅ Serie A está disponible pero no seleccionada

---

### Test 6: Presupuesto sin series configuradas
**Precondición:** No hay series de tipo QUOTE

1. Ir a "Nuevo presupuesto"
2. Completar perfil fiscal si está incompleto
3. **Verificar:**
   - ✅ Selector de serie muestra: "No hay series de presupuesto configuradas. [Crear una serie]"
   - ✅ Link lleva a `/app/gestion/configuracion/negocio`
4. Click en link → Crear serie QUOTE P - PV 0001
5. Volver a "Nuevo presupuesto"
6. **Verificar:**
   - ✅ Serie ahora aparece en el selector
   - ✅ Está pre-seleccionada si es default

---

## 📊 Resumen de Cambios

| Componente | Archivos Modificados | Líneas Agregadas | Funcionalidad |
|------------|---------------------|-----------------|---------------|
| **Facturas (invoicing)** | invoice-actions.tsx | ~50 | BillingProfile + DocumentSeries |
| **Facturas (ventas)** | ventas/invoice-actions.tsx | ~50 | BillingProfile + DocumentSeries |
| **Presupuestos** | new-quote-client.tsx | ~80 | BillingProfile + DocumentSeries + Serie selector |
| **Tipos** | types.ts | 1 | document_series_id en QuotePayload |
| **Total** | 4 archivos | ~181 líneas | ✅ Integración completa |

---

## 🔗 Dependencias

### Frontend Hooks Utilizados
```typescript
// Ya existentes en features/gestion/hooks.ts:
useBusinessBillingProfileQuery()    // Obtiene perfil fiscal
useDocumentSeriesQuery()            // Obtiene todas las series
```

### Validaciones Agregadas
```typescript
// En todos los componentes de emisión:
const isProfileComplete = billingProfile?.is_complete ?? false;

// Filtrado de series por tipo:
const invoiceSeries = allSeries.filter(s => 
  s.document_type === 'invoice' && s.is_active
);

const quoteSeries = allSeries.filter(s => 
  s.document_type === 'quote' && s.is_active
);

// Auto-selección de default:
const defaultSeries = useMemo(
  () => series.find(s => s.is_default)?.id ?? series[0]?.id ?? '',
  [series]
);
```

---

## 🚀 Próximos Pasos

### Backend Pendiente
**Nota:** El frontend ya envía `document_series_id`, pero el backend actual podría no usarlo. Verificar y actualizar:

#### En Facturas (invoices)
```python
# services/api/src/apps/invoices/serializers.py
class InvoiceIssueSerializer(serializers.Serializer):
    # Agregar:
    document_series_id = serializers.UUIDField(required=False, allow_null=True)
    
    def create(self, validated_data):
        series_id = validated_data.get('document_series_id')
        if series_id:
            # Usar DocumentSeries en lugar de InvoiceSeries
            series = DocumentSeries.objects.get(pk=series_id, business=business)
            next_number = series.get_next_number()  # Atómico
            # ... crear factura con series.letter, series.point_of_sale, next_number
```

#### En Presupuestos (quotes)
```python
# services/api/src/apps/sales/quote_serializers.py
class QuoteCreateSerializer(serializers.Serializer):
    # Ya agregado en tipos, verificar backend:
    document_series_id = serializers.UUIDField(required=False, allow_null=True)
    
    def create(self, validated_data):
        series_id = validated_data.get('document_series_id')
        if series_id:
            series = DocumentSeries.objects.get(pk=series_id, business=business)
            next_number = series.get_next_number()
            # ... crear quote con next_number
```

---

### Documentos Futuros
Los siguientes documentos están definidos en DocumentSeries pero **no tienen flujo de emisión aún**:
- ❌ Recibo (receipt)
- ❌ Nota de Crédito (credit_note)
- ❌ Nota de Débito (debit_note)
- ❌ Remito (delivery_note)

**Patrón a seguir:** Replicar la integración de facturas/presupuestos:
1. Validar `BillingProfile.is_complete`
2. Filtrar series por `document_type`
3. Auto-seleccionar serie default
4. Mostrar datos del emisor (read-only)
5. Bloquear emisión si incompleto

---

## 🎓 Aprendizajes

### Patrón de Integración Universal
```typescript
// 1. Cargar perfil y series
const billingProfile = useBusinessBillingProfileQuery();
const documentSeries = useDocumentSeriesQuery();

// 2. Validar completitud
const isProfileComplete = billingProfile.data?.is_complete ?? false;

// 3. Filtrar series por tipo de documento
const series = documentSeries.data?.filter(s => 
  s.document_type === 'TYPE' && s.is_active
) ?? [];

// 4. Auto-seleccionar default
const defaultSeriesId = series.find(s => s.is_default)?.id;

// 5. Bloquear UI si incompleto
disabled={!isProfileComplete}

// 6. Mostrar CTA con link a config
{!isProfileComplete && (
  <Link href="/app/gestion/configuracion/negocio">
    Completar datos del negocio →
  </Link>
)}
```

---

## 📚 Referencias

- **Fase 1 Backend:** [FINANCE_GASTOS_AUDIT.md](FINANCE_GASTOS_AUDIT.md)
- **Frontend Settings UI:** [FRONTEND_BUSINESS_SETTINGS_UI.md](FRONTEND_BUSINESS_SETTINGS_UI.md)
- **BillingProfile Endpoint:** `/api/v1/business/settings/billing/`
- **DocumentSeries Endpoint:** `/api/v1/invoices/document-series/`

---

**Estado:** ✅ **Integración completa en frontend - Facturas y Presupuestos**  
**Pendiente:** Backend actualizar para usar `document_series_id` en lugar de `series_code`
