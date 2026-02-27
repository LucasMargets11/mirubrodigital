# 🔍 AUDITORÍA: Configuración de Negocio & Emisión de Documentos

> Fecha: 2026-02-17  
> Estado: ✅ AUDITORÍA COMPLETADA - PENDIENTE IMPLEMENTACIÓN

---

## 📋 RESUMEN EJECUTIVO

**PROBLEMA IDENTIFICADO:**  
Los datos del emisor (razón social, CUIT, domicilio, etc.) NO están centralizados. Cada documento los pide en el momento de emisión o usa datos parciales del modelo Business (solo name).

**IMPACTO:**  
- ❌ Modal "Generar factura" pide datos del emisor cada vez
- ❌ PDFs generados con datos incompletos (CUIT: "—", sin domicilio fiscal)
- ❌ No hay branding configurado (sin logos)
- ❌ Series limitadas (solo para facturas, sin letra/punto de venta)
- ❌ No hay configuración fiscal/legal centralizada

---

## 1️⃣ BACKEND - ESTADO ACTUAL

### 1.1 Modelos Existentes

#### ✅ `Business` (apps/business/models.py)
**Ubicación:** `services/api/src/apps/business/models.py`

```python
class Business(models.Model):
  name = models.CharField(max_length=255)
  parent = models.ForeignKey('self', null=True, blank=True, related_name='branches', on_delete=models.PROTECT)
  default_service = models.CharField(max_length=32, choices=SERVICE_CHOICES, default='gestion')
  status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active') 
  created_at = models.DateTimeField(auto_now_add=True)
```

**GAPS DETECTADOS:**
- ❌ NO tiene: razón_social, nombre_fantasia
- ❌ NO tiene: tax_id (CUIT/CUIL/DNI), tax_id_type
- ❌ NO tiene: domicilio_comercial, domicilio_fiscal
- ❌ NO tiene: condicion_iva (RI/Monotributo/Exento/CF)
- ❌ NO tiene: iibb, inicio_actividades
- ❌ NO tiene: email, phone, website
- ❌ NO tiene: logo, logo_square, brand_color

**¿Es multi-sucursal?** ✅ SÍ - tiene parent/branches

---

#### ✅ `CommercialSettings` (apps/business/models.py)
**Ubicación:** `services/api/src/apps/business/models.py`

```python
class CommercialSettings(models.Model):
  business = models.OneToOneField('business.Business', related_name='commercial_settings', on_delete=models.CASCADE)
  allow_sell_without_stock = models.BooleanField(default=False)
  block_sales_if_no_open_cash_session = models.BooleanField(default=True)
  require_customer_for_sales = models.BooleanField(default=False)
  allow_negative_price_or_discount = models.BooleanField(default=False)
  warn_on_low_stock_threshold_enabled = models.BooleanField(default=True)
  low_stock_threshold_default = models.PositiveIntegerField(default=5)
  enable_sales_notes = models.BooleanField(default=True)
  enable_receipts = models.BooleanField(default=True)
```

**Endpoint:** `GET/PATCH /api/v1/business/commercial/settings/`  
**Permiso:** `manage_commercial_settings`

**GAPS DETECTADOS:**
- ✅ Correcto: solo configuraciones operativas
- ❌ NO tiene: datos fiscales/legales (es el lugar correcto, pero faltan)

---

#### ✅ `InvoiceSeries` (apps/invoices/models.py)
**Ubicación:** `services/api/src/apps/invoices/models.py`

```python
class InvoiceSeries(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='invoice_series', on_delete=models.CASCADE)
  code = models.CharField(max_length=8, default='X')  # "A", "B", "X"
  prefix = models.CharField(max_length=16, blank=True)
  next_number = models.PositiveIntegerField(default=1)
  is_active = models.BooleanField(default=True)
```

**GAPS DETECTADOS:**
- ❌ NO tiene: document_type (Invoice/Quote/Receipt/CreditNote/DebitNote)
- ❌ NO tiene: letra (A/B/C/M) - usa "code" pero sin validación
- ❌ NO tiene: punto_de_venta / branch (está a nivel Business, falta por sucursal/caja)
- ❌ NO tiene: is_default (para autoselección)
- ⚠️  Constraint: único por business+code, no por business+code+tipo_doc

---

#### ✅ `Invoice` (apps/invoices/models.py)
**Ubicación:** `services/api/src/apps/invoices/models.py`

```python
class Invoice(models.Model):
  business = models.ForeignKey('business.Business', related_name='invoices', on_delete=models.CASCADE)
  sale = models.OneToOneField('sales.Sale', related_name='invoice', on_delete=models.PROTECT)
  series = models.ForeignKey(InvoiceSeries, related_name='invoices', on_delete=models.PROTECT)
  number = models.PositiveIntegerField()
  full_number = models.CharField(max_length=48)
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.ISSUED)
  issued_at = models.DateTimeField(default=timezone.now)
  # CLIENTE (receptor)
  customer_name = models.CharField(max_length=255, blank=True)
  customer_tax_id = models.CharField(max_length=64, blank=True)
  customer_address = models.CharField(max_length=255, blank=True)
  # TOTALES
  subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  # PDF
  pdf_file = models.FileField(upload_to='invoices/', null=True, blank=True)
```

**GAPS DETECTADOS:**
- ❌ NO tiene: issuer_* (emisor) - se asume que todo viene de Business
- ❌ Hardcodeado: "CUIT: —" en el PDF

---

#### ✅ `Quote` (apps/sales/models.py)
**Ubicación:** `services/api/src/apps/sales/models.py`

```python
class Quote(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='quotes', on_delete=models.CASCADE)
  number = models.CharField(max_length=20)  # Formato: P-000001
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
  customer = models.ForeignKey('customers.Customer', null=True, blank=True, on_delete=models.PROTECT)
  customer_name = models.CharField(max_length=255, blank=True)
  customer_email = models.EmailField(blank=True)
  customer_phone = models.CharField(max_length=50, blank=True)
  valid_until = models.DateField(null=True, blank=True)
  # ...totales
```

**Serie:** usa `QuoteSequence` (tabla separada) con formato "P-000001"  
**PDF:** ✅ SÍ - `apps/sales/quote_pdf.py` → `build_quote_pdf()`

**GAPS DETECTADOS:**
- ❌ NO usa InvoiceSeries (tiene su propio sistema de numeración)
- ❌ PDF intenta usar `business.address`, `business.phone`, `business.email` pero NO existen en el modelo

---

### 1.2 Generación de PDF

#### 📄 Facturas (Invoice PDF)
**Archivo:** `services/api/src/apps/invoices/pdf.py`

```python
def render_invoice_pdf(invoice: Invoice) -> bytes:
  # ...
  pdf.drawString(margin, current_y, 'MiRubro · Comprobante interno')
  pdf.drawString(margin, current_y - 14, f"Factura {invoice.full_number}")
  
  # EMISOR HARDCODEADO ❌
  pdf.drawString(margin, current_y, 'Emisor')
  pdf.drawString(margin, current_y - 14, f"Negocio: {invoice.business.name}")
  pdf.drawString(margin, current_y - 28, 'CUIT: —')  # ❌ HARDCODEADO
```

**Endpoint:** `GET /api/v1/invoices/{id}/pdf/`

---

#### 📄 Presupuestos (Quote PDF)
**Archivo:** `services/api/src/apps/sales/quote_pdf.py`

```python
def build_quote_pdf(quote: Quote) -> bytes:
  # ...
  business_name = quote.business.name if hasattr(quote.business, 'name') else "Nombre del Negocio"
  story.append(Paragraph(f"<b>{business_name}</b>", heading_style))
  
  # INTENTA USAR CAMPOS QUE NO EXISTEN ❌
  if hasattr(quote.business, 'address') and quote.business.address:
    story.append(Paragraph(quote.business.address, small_style))
  if hasattr(quote.business, 'phone') and quote.business.phone:
    story.append(Paragraph(f"Tel: {quote.business.phone}", small_style))
  if hasattr(quote.business, 'email') and quote.business.email:
    story.append(Paragraph(f"Email: {quote.business.email}", small_style))
```

**Endpoint:** `GET /api/v1/sales/quotes/{id}/pdf/`

---

### 1.3 Endpoints de Configuración

#### ✅ CommercialSettings
```
GET    /api/v1/business/commercial/settings/
PATCH  /api/v1/business/commercial/settings/
```
**Permiso:** `manage_commercial_settings`  
**Vista:** `CommercialSettingsView` (APIView)

#### ❌ BusinessBillingProfile / BusinessSettings
**NO EXISTE**

---

## 2️⃣ FRONTEND - ESTADO ACTUAL

### 2.1 Sidebar & Navegación

**Archivo:** `apps/web/src/components/navigation/sidebar.tsx`

**Secciones de configuración actuales:**

**Servicio "gestion":**
```tsx
{
  href: '/app/gestion/configuracion',  // ✅ EXISTE
  label: 'Configuración',
  permissionKey: 'manage_commercial_settings',
  featureKey: 'settings',
}
```

**Servicio "restaurante":**
```tsx
{
  label: 'Configuración',
  permissionKey: 'manage_settings',
  featureKey: 'settings',
  children: [
    { href: '/app/settings', label: 'General' },
    { href: '/app/settings/access', label: 'Roles & Accesos' },
    { href: '/app/settings/branches', label: 'Sucursales' },
    { href: '/app/settings/online-menu', label: 'Carta Online' },
    { href: '/app/resto/settings/tables', label: 'Configurar mesas' },
  ],
}
```

**GAPS DETECTADOS:**
- ❌ NO existe: "Configuración del negocio" o "Perfil fiscal"
- ❌ NO existe: "Series y comprobantes"
- ❌ NO existe: "Branding"
- ⚠️  `/app/gestion/configuracion` solo edita CommercialSettings (toggles)

---

### 2.2 Pantallas de Configuración

#### ✅ `/app/gestion/configuracion`
**Archivos:**
- `apps/web/src/app/app/gestion/configuracion/page.tsx`
- `apps/web/src/app/app/gestion/configuracion/settings-client.tsx`

**Función:** Edita CommercialSettings (toggles booleanos + umbral de stock bajo)

**GAPS:**
- ✅ Correcto para lo que hace
- ❌ NO edita datos fiscales/legales
- ❌ NO edita series
- ❌ NO edita branding

---

#### ✅ `/app/settings` (General)
**Archivo:** `apps/web/src/app/app/settings/page.tsx`

**Función:** Landing con cards de acceso a:
- Roles & Accesos
- Sucursales
- Menú Online

**GAPS:**
- ❌ NO tiene card "Configuración del negocio"
- ❌ NO tiene card "Perfil fiscal"
- ❌ NO tiene card "Series de comprobantes"

---

### 2.3 Modal "Generar factura"

**Archivo:** `apps/web/src/components/invoicing/invoice-actions.tsx`

**Campos que pide:**
```tsx
{
  series_code: string;          // ✅ Serie (select)
  customer_name: string;        // ✅ Cliente
  customer_tax_id: string;      // ✅ CUIT del cliente
  customer_address: string;     // ✅ Dirección del cliente
}
```

**PROBLEMA:** ❌ NO pide datos del emisor porque se asume que están en Business (pero NO están)

**Endpoint que llama:**
- Ventas: `POST /api/v1/sales/invoices/` (useIssueInvoice)
- Órdenes: `POST /api/v1/resto/orders/{id}/invoice/` (useIssueOrderInvoice)

---

### 2.4 Módulos que Generan Documentos

#### 📊 Estado Actual

| Módulo | Documento | ¿Tiene Series? | ¿Genera PDF? | ¿Campos emisor? |
|--------|-----------|----------------|--------------|-----------------|
| **Ventas** | Factura (Invoice) | ✅ InvoiceSeries | ✅ Sí | ❌ No |
| **Ventas** | Presupuesto (Quote) | ⚠️  QuoteSequence (separado) | ✅ Sí | ❌ No |
| **Órdenes** | Factura (Invoice) | ✅ InvoiceSeries | ✅ Sí | ❌ No |
| **Finanzas** | ¿Recibos? | ❌ No | ❓ | ❌ No |
| **Tesorería** | ¿NC/ND? | ❌ No | ❓ | ❌ No |

**Rutas frontend:**
- ✅ `/app/gestion/ventas` - Ventas + Presupuestos
- ✅ `/app/gestion/facturas` - Listado de facturas
- ✅ `/app/gestion/ventas/presupuestos` - Presupuestos
- ❓ `/app/gestion/finanzas` - ¿Hay documentos acá?

---

## 3️⃣ GAPS IDENTIFICADOS (Lista Completa)

### 🔴 CRÍTICO (Bloqueante para emisión correcta)

1. **NO existe modelo BusinessBillingProfile / BusinessSettings**
   - Falta: razón_social, tax_id, tax_id_type, condicion_iva, domicilios, etc.
   - Impacto: PDFs con datos incompletos o hardcodeados

2. **Modal "Generar factura" NO pregunta datos del emisor**
   - Impacto: Asume que Business tiene todo (pero no)

3. **PDFs con datos hardcodeados**
   - Invoice: `CUIT: —`
   - Quote: Intenta leer campos que no existen

4. **NO hay branding configurado**
   - Sin logo, sin color acento
   - PDFs sin identidad visual

### 🟡 IMPORTANTE (Mejora necesaria)

5. **InvoiceSeries limitado**
   - Solo para facturas (no para Quote/Receipt/CN/ND)
   - No tiene document_type
   - No tiene is_default
   - No tiene punto_de_venta/branch

6. **Quote usa sistema de numeración separado (QuoteSequence)**
   - No reutiliza InvoiceSeries
   - Imposible unificar series por tipo de documento

7. **NO hay gestión de series en UI**
   - No hay CRUD de series
   - No se pueden crear/editar/desactivar

8. **NO hay validación previa a emitir**
   - No valida si BillingProfile está completo
   - No muestra CTA "Completar configuración"

### 🟢 MENOR (Mejora opcional / futuro)

9. **NO hay plantillas de PDF configurables**
   - PDF hardcodeado en código
   - No hay opción A4/Ticket/Custom

10. **NO hay campos de leyendas/footer**
    - No hay "condiciones de pago", "validez", "nota legal"

11. **NO hay multi-sucursal en series**
    - InvoiceSeries a nivel Business, no por Branch

---

## 4️⃣ DECISIONES DE ARQUITECTURA

### ¿Dónde colgar los datos fiscales?

#### Opción A: Extender `Business` ✅ RECOMENDADO
**PRO:**
- Ya existe como raíz del tenant
- Ya tiene multi-sucursal (parent/branches)
- Menos migraciones complejas

**CONTRA:**
- Modelo grande (pero manejable con related)

#### Opción B: Crear `BusinessBillingProfile` (1-to-1)
**PRO:**
- Separación de responsabilidades
- Más limpio conceptualmente

**CONTRA:**
- 1 JOIN extra en cada query
- Más modelos

**DECISIÓN:** Opción A (extender Business) para datos fiscales básicos  
**RAZÓN:** Evitar JOIN innecesario, Business ya es la raíz

---

### ¿Dónde poner branding?

#### Opción A: En Business ⚠️ NO
**PRO:** Todo junto
**CONTRA:** Mezclamos datos fiscales con assets (logos)

#### Opción B: BusinessBranding (1-to-1) ✅ RECOMENDADO
**PRO:** Separación clara, assets en tabla aparte
**CONTRA:** 1 modelo más

**DECISIÓN:** Crear `BusinessBranding` separado  
**RAZÓN:** Los FileField/ImageField mejor en tabla aparte para performance

---

### ¿Cómo unificar series?

#### Opción A: Refactorizar InvoiceSeries → DocumentSeries ✅ RECOMENDADO
**Cambios:**
```python
class DocumentType(models.TextChoices):
  INVOICE = 'invoice', 'Factura'
  QUOTE = 'quote', 'Presupuesto'
  RECEIPT = 'receipt', 'Recibo'
  CREDIT_NOTE = 'credit_note', 'Nota de Crédito'
  DEBIT_NOTE = 'debit_note', 'Nota de Débito'
  DELIVERY_NOTE = 'delivery_note', 'Remito'

class DocumentSeries(models.Model):
  business = models.ForeignKey('business.Business', ...)
  document_type = models.CharField(max_length=32, choices=DocumentType.choices)
  code = models.CharField(max_length=8)  # A/B/C/X
  prefix = models.CharField(max_length=16, blank=True)
  punto_de_venta = models.CharField(max_length=8, blank=True)  # "0001"
  next_number = models.PositiveIntegerField(default=1)
  is_active = models.BooleanField(default=True)
  is_default = models.BooleanField(default=False)  # ✨ NUEVO
  branch = models.ForeignKey('business.Business', null=True, blank=True, ...)  # ✨ NUEVO (multi-sucursal)
```

**Constraint:**
```python
models.UniqueConstraint(
  fields=['business', 'document_type', 'code', 'punto_de_venta'],
  name='unique_series_per_document_type'
)
```

#### Opción B: Mantener InvoiceSeries + QuoteSequence ❌ NO
**Razón:** Imposible escalar a más tipos de documento

**DECISIÓN:** Refactorizar a DocumentSeries  
**RAZÓN:** Escalable, unificado, soporta todos los tipos de documento

---

## 5️⃣ ESTRUCTURA DE DATOS PROPUESTA

### Nuevos campos en `Business`

```python
class Business(models.Model):
  # ... existentes (name, parent, default_service, status, created_at)
  
  # PERFIL FISCAL/LEGAL ✨ NUEVO
  legal_name = models.CharField(max_length=255, blank=True)  # Razón social
  trade_name = models.CharField(max_length=255, blank=True)  # Nombre de fantasía (opcional)
  
  TAX_ID_TYPE_CHOICES = [
    ('cuit', 'CUIT'),
    ('cuil', 'CUIL'),
    ('dni', 'DNI'),
    ('other', 'Otro'),
  ]
  tax_id_type = models.CharField(max_length=16, choices=TAX_ID_TYPE_CHOICES, blank=True)
  tax_id = models.CharField(max_length=64, blank=True, db_index=True)  # CUIT/CUIL/DNI
  
  IVA_CONDITION_CHOICES = [
    ('responsable_inscripto', 'Responsable Inscripto'),
    ('monotributo', 'Monotributo'),
    ('exento', 'Exento'),
    ('consumidor_final', 'Consumidor Final'),
    ('no_responsable', 'No Responsable'),
  ]
  iva_condition = models.CharField(max_length=32, choices=IVA_CONDITION_CHOICES, blank=True)
  
  iibb = models.CharField(max_length=64, blank=True)  # Ingresos Brutos
  business_start_date = models.DateField(null=True, blank=True)  # Inicio de actividades
  
  # DOMICILIOS
  commercial_address = models.TextField(blank=True)  # Domicilio comercial
  fiscal_address = models.TextField(blank=True)  # Domicilio fiscal (legal)
  
  # CONTACTO
  email = models.EmailField(blank=True)
  phone = models.CharField(max_length=64, blank=True)
  website = models.URLField(blank=True)
```

---

### Nuevo modelo `BusinessBranding`

```python
class BusinessBranding(models.Model):
  business = models.OneToOneField('business.Business', related_name='branding', on_delete=models.CASCADE)
  
  # LOGOS
  logo_horizontal = models.ImageField(upload_to='business/logos/', null=True, blank=True)
  logo_square = models.ImageField(upload_to='business/logos/', null=True, blank=True)
  
  # COLOR
  brand_color = models.CharField(max_length=7, blank=True)  # HEX: #0066CC
  
  # METADATA
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
```

---

### Refactor `InvoiceSeries` → `DocumentSeries`

```python
class DocumentSeries(models.Model):
  class DocumentType(models.TextChoices):
    INVOICE = 'invoice', 'Factura'
    QUOTE = 'quote', 'Presupuesto'
    RECEIPT = 'receipt', 'Recibo'
    CREDIT_NOTE = 'credit_note', 'Nota de Crédito'
    DEBIT_NOTE = 'debit_note', 'Nota de Débito'
    DELIVERY_NOTE = 'delivery_note', 'Remito'
  
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='document_series', on_delete=models.CASCADE)
  document_type = models.CharField(max_length=32, choices=DocumentType.choices)
  
  # LETRA (A/B/C/M/X)
  code = models.CharField(max_length=8)
  
  # FORMATO
  prefix = models.CharField(max_length=16, blank=True)
  suffix = models.CharField(max_length=16, blank=True)
  punto_de_venta = models.CharField(max_length=8, blank=True)  # "0001"
  
  # NUMERACIÓN
  next_number = models.PositiveIntegerField(default=1)
  
  # ESTADO
  is_active = models.BooleanField(default=True)
  is_default = models.BooleanField(default=False)  # ✨ Para autoselección
  
  # MULTI-SUCURSAL (opcional)
  branch = models.ForeignKey('business.Business', null=True, blank=True, related_name='series_by_branch', on_delete=models.CASCADE)
  
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  
  class Meta:
    ordering = ['document_type', 'code']
    constraints = [
      models.UniqueConstraint(
        fields=['business', 'document_type', 'code', 'punto_de_venta'],
        name='unique_series_per_doc_type',
      ),
    ]
  
  def format_full_number(self, number: int) -> str:
    """
    Formato configurable:
    - Con PV: A-0001-00000123
    - Sin PV: A-00000123
    - Con prefix: A-SUCU1-00000123
    """
    parts = [self.code]
    if self.punto_de_venta:
      parts.append(self.punto_de_venta.zfill(4))
    if self.prefix:
      parts.append(self.prefix)
    parts.append(str(number).zfill(8))
    return '-'.join(parts)
```

---

## 6️⃣ ENDPOINTS A CREAR

### BusinessSettings / BillingProfile

```
GET    /api/v1/business/settings/billing/
PATCH  /api/v1/business/settings/billing/
```

**Payload:**
```json
{
  "legal_name": "MiRubro SRL",
  "trade_name": "MiRubro",
  "tax_id_type": "cuit",
  "tax_id": "30-12345678-9",
  "iva_condition": "responsable_inscripto",
  "iibb": "901-123456-7",
  "business_start_date": "2020-01-15",
  "commercial_address": "Av. Corrientes 1234, CABA",
  "fiscal_address": "Av. Corrientes 1234, CABA",
  "email": "contacto@mirubro.com",
  "phone": "+54 11 1234-5678",
  "website": "https://mirubro.com"
}
```

---

### BusinessBranding

```
GET    /api/v1/business/settings/branding/
POST   /api/v1/business/settings/branding/upload-logo/
PATCH  /api/v1/business/settings/branding/
DELETE /api/v1/business/settings/branding/logo/{type}/  # type: horizontal | square
```

**Upload:**
```
POST /api/v1/business/settings/branding/upload-logo/
Content-Type: multipart/form-data

logo_type: "horizontal" | "square"
file: <binary>
```

---

### DocumentSeries (CRUD)

```
GET    /api/v1/business/document-series/
POST   /api/v1/business/document-series/
PATCH  /api/v1/business/document-series/{id}/
DELETE /api/v1/business/document-series/{id}/
POST   /api/v1/business/document-series/{id}/set-default/
```

**Filtros:**
```
?document_type=invoice
?is_active=true
?branch=<branch_id>
```

**Payload crear:**
```json
{
  "document_type": "invoice",
  "code": "A",
  "prefix": "",
  "punto_de_venta": "0001",
  "next_number": 1,
  "is_active": true,
  "is_default": false,
  "branch": null
}
```

---

## 7️⃣ FRONTEND - PANTALLAS A CREAR

### Nueva sección: `/app/configuracion/negocio`

**Tabs:**

#### A) Perfil fiscal (Emisor)
- Formulario con todos los campos de Business (legal_name, tax_id, etc.)
- Validación en frontend (CUIT formato correcto)
- Guardar con `PATCH /api/v1/business/settings/billing/`

#### B) Branding
- Upload logo horizontal (preview)
- Upload logo cuadrado (preview)
- Color picker para brand_color
- Vista previa "Así se verá en comprobantes" (mockup)

#### C) Comprobantes (Series y numeración)
- Tabla con ordenar/filtrar
- Columnas: Tipo Doc | Letra | Prefijo | Punto de Venta | Próximo # | Activa | Default | Acciones
- Botón "Nueva serie" → Modal
- Acción "Set default" (solo 1 default por tipo de documento)
- Validaciones:
  - Unicidad: business + documento + letra + PV
  - No permitir eliminar serie con documentos emitidos

#### D) Plantillas (Opcional - Fase 2)
- Seleccionar: A4 / Ticket / Custom
- Footer / Leyendas
- Campos extra

---

### Integración en sidebar

**Opción 1: Dentro de `/app/settings`**
```tsx
{
  label: 'Configuración',
  children: [
    { href: '/app/settings', label: 'General' },
    { href: '/app/settings/negocio', label: 'Negocio', permissionKey: 'manage_settings' },  // ✨ NUEVO
    { href: '/app/settings/access', label: 'Roles & Accesos' },
    { href: '/app/settings/branches', label: 'Sucursales' },
  ],
}
```

**Opción 2: Sección independiente**
```tsx
{
  label: 'Negocio',
  href: '/app/configuracion/negocio',
  permissionKey: 'manage_settings',
}
```

**DECISIÓN:** Opción 1 (dentro de `/app/settings`)  
**RAZÓN:** Coherencia con estructura actual

---

### Validación pre-emisión

**Actualizar:** `invoice-actions.tsx`

**Lógica:**
```tsx
const canIssue = useMemo(() => {
  if (!billingProfile?.legal_name || !billingProfile?.tax_id) {
    return {
      allowed: false,
      reason: 'Completá los datos fiscales del negocio antes de emitir facturas.',
      ctaLabel: 'Ir a Configuración',
      ctaHref: '/app/settings/negocio?tab=fiscal',
    };
  }
  return { allowed: true };
}, [billingProfile]);
```

---

## 8️⃣ PLAN DE IMPLEMENTACIÓN

### Fase 1: Backend - Modelos y Migraciones

**Commits:**

#### Commit 1.1: Extender Business con datos fiscales
- Migration: Add fiscal fields to Business
- Update Business model
- Update serializers
- Create endpoint: `GET/PATCH /api/v1/business/settings/billing/`
- Create permission: `manage_business_settings` (o reusar `manage_settings`)
- Unit tests

#### Commit 1.2: Crear BusinessBranding
- Migration: Create BusinessBranding
- Update Business model (related)
- Create serializers
- Create endpoints: upload/get/patch/delete
- Unit tests

#### Commit 1.3: Refactor InvoiceSeries → DocumentSeries
- Migration: Rename + add fields (document_type, is_default, branch, punto_de_venta)
- Data migration: Migrate existing InvoiceSeries (set document_type='invoice')
- Update Invoice model (FK rename)
- Update Quote model (usar DocumentSeries en lugar de QuoteSequence)
- Update serializers
- Create CRUD endpoints
- Unit tests
- ⚠️  **CRÍTICO:** Migración de datos reversible

---

### Fase 2: Frontend - UI Configuración Negocio

#### Commit 2.1: Crear pantalla /settings/negocio
- Crear componentes:
  - `apps/web/src/app/app/settings/negocio/page.tsx`
  - `apps/web/src/app/app/settings/negocio/fiscal-tab.tsx`
  - `apps/web/src/app/app/settings/negocio/branding-tab.tsx`
  - `apps/web/src/app/app/settings/negocio/series-tab.tsx`
- Agregar link en sidebar
- Agregar card en `/app/settings`

#### Commit 2.2: Implementar Tab "Perfil fiscal"
- Formulario completo (campos validados)
- API hooks: `useBusinessBillingProfile`, `useUpdateBillingProfile`
- Validaciones frontend (CUIT/CUIL format)

#### Commit 2.3: Implementar Tab "Branding"
- Upload de logos (con preview)
- Color picker
- API hooks: `useBusinessBranding`, `useUploadLogo`, `useUpdateBranding`
- Preview de comprobante (mockup)

#### Commit 2.4: Implementar Tab "Series"
- Tabla con filtros
- Modal "Nueva serie"
- CRUD completo
- Set default
- API hooks: `useDocumentSeries`, `useCreateSeries`, etc.

---

### Fase 3: Integración - Documentos usan config central

#### Commit 3.1: Refactor modal "Generar factura"
- Remover campos del emisor (ya no se piden)
- Pre-cargar serie default
- Agregar validación: bloquear si falta billing profile
- Mostrar CTA "Completar configuración del negocio"

#### Commit 3.2: Actualizar serializers de emisión
- InvoiceIssueSerializer: No pedir emisor, tomar de Business
- QuoteCreateSerializer: Usar DocumentSeries
- Validar billing profile completo en backend

#### Commit 3.3: Actualizar PDFs
- render_invoice_pdf: Usar business.legal_name, business.tax_id, etc.
- build_quote_pdf: Usar business.legal_name, business.tax_id, etc.
- Incluir logo si existe (from BusinessBranding)
- Template con slots para futuro CAE/QR

#### Commit 3.4: Actualizar emisión en otros módulos
- Órdenes (orders)
- ¿Finanzas? (si generan docs)
- ¿Tesorería? (si generan docs)

---

### Fase 4: Pruebas & Refinamiento

#### Commit 4.1: Tests E2E
- Smoke test: Crear negocio → Cargar fiscal → Cargar logo → Crear serie → Emitir factura → Verificar PDF
- Test: Emitir sin billing profile → Bloqueado
- Test: Numeración secuencial (race condition)

#### Commit 4.2: Migración de datos existentes
- Script: Rellenar legal_name con name para Business existentes
- Script: Crear series default para Business sin series
- Script: Validar integridad

---

## 9️⃣ RIESGOS & MITIGACIONES

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Breaking change en InvoiceSeries → DocumentSeries | 🔴 Alto | Migración de datos + mantener backward compatibility durante 1 release |
| PDFs sin logo (si no suben) | 🟡 Medio | Fallback: si no hay logo, usar nombre del negocio |
| Series duplicadas al migrar QuoteSequence | 🟡 Medio | Validar unicidad en migración + tests |
| Usuarios emiten docs antes de configurar negocio | 🟡 Medio | Validación en backend + CTA en frontend |
| Upload de logos muy grandes | 🟢 Bajo | Validación de tamaño (max 2MB) + resize en backend |
| Multi-sucursal (series por branch) | 🟢 Bajo | Implementar en Fase 2, ahora dejarlo opcional (null) |

---

## 🔟 CHECKLIST DE ENTREGA

### Backend
- [ ] Migration: Extender Business con campos fiscales
- [ ] Migration: Crear BusinessBranding
- [ ] Migration: Refactor InvoiceSeries → DocumentSeries
- [ ] Migration: Migrar datos existentes (QuoteSequence → DocumentSeries)
- [ ] Endpoint: GET/PATCH billing profile
- [ ] Endpoint: GET/POST/PATCH/DELETE branding
- [ ] Endpoint: CRUD DocumentSeries
- [ ] Serializer: Validar billing profile completo al emitir
- [ ] PDF: render_invoice_pdf usa billing profile + logo
- [ ] PDF: build_quote_pdf usa billing profile + logo
- [ ] Tests: Unit tests para nuevos modelos
- [ ] Tests: Integration test emisión sin billing profile (bloqueado)

### Frontend
- [ ] Pantalla: /settings/negocio con tabs
- [ ] Tab: Perfil fiscal (formulario completo)
- [ ] Tab: Branding (upload logos + preview)
- [ ] Tab: Series (CRUD + set default)
- [ ] Sidebar: Link a nueva pantalla
- [ ] Validación: Bloquear emisión si falta billing profile
- [ ] CTA: "Completar configuración del negocio"
- [ ] Hooks: useBusinessBillingProfile, useBusinessBranding, useDocumentSeries
- [ ] Tests: E2E smoke test (configurar → emitir → verificar PDF)

### Documentación
- [ ] README: Sección "Configuración del negocio"
- [ ] README: Sección "Series de comprobantes"
- [ ] Changelog: Añadir breaking changes (si aplica)
- [ ] Screenshots/GIFs de nuevas pantallas

---

## 📸 SCREENSHOTS / WIREFRAMES (Pendiente)

*Agregar capturas de pantalla de:*
- [ ] Modal "Generar factura" (antes vs después)
- [ ] Pantalla /settings/negocio (tabs)
- [ ] PDF de factura (con logo y datos fiscales)
- [ ] Tabla de series

---

## 📚 REFERENCIAS

**Archivos clave auditados:**

**Backend:**
- `services/api/src/apps/business/models.py` - Business, CommercialSettings
- `services/api/src/apps/invoices/models.py` - Invoice, InvoiceSeries
- `services/api/src/apps/invoices/pdf.py` - render_invoice_pdf
- `services/api/src/apps/sales/models.py` - Quote, QuoteSequence
- `services/api/src/apps/sales/quote_pdf.py` - build_quote_pdf
- `services/api/src/apps/business/views.py` - CommercialSettingsView

**Frontend:**
- `apps/web/src/components/invoicing/invoice-actions.tsx` - Modal generar factura
- `apps/web/src/components/navigation/sidebar.tsx` - Navegación
- `apps/web/src/app/app/gestion/configuracion/` - Configuración comercial
- `apps/web/src/app/app/settings/page.tsx` - Settings landing

---

## ✅ CONCLUSIONES

**Estado actual:**
- ✅ Auditoría completa
- ✅ Gaps identificados
- ✅ Arquitectura propuesta
- ✅ Plan de implementación detallado

**Próximos pasos:**
1. Revisión de este documento con el equipo
2. Decisión de arquitectura (aprobar o ajustar)
3. Priorizar fases
4. Comenzar implementación (Commit 1.1)

**Estimación de esfuerzo:**
- Backend (Fase 1): 5-7 días
- Frontend (Fase 2): 7-10 días
- Integración (Fase 3): 5-7 días
- Tests & Deploy (Fase 4): 3-5 días
- **Total:** 20-29 días (4-6 semanas, 1 dev full-time)

---

**Autor:** GitHub Copilot  
**Fecha:** 2026-02-17  
**Versión:** 1.0
