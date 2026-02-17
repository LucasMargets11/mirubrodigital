# 🚀 PLAN DE IMPLEMENTACIÓN: Configuración del Negocio

> Basado en: BUSINESS_SETTINGS_AUDIT.md  
> Fecha: 2026-02-17  
> Prioridad: 🔴 ALTA

---

## 📋 RESUMEN EJECUTIVO

Implementar sistema centralizado de configuración de negocio que incluya:
- ✅ Datos fiscales/legales del emisor (CUIT, razón social, domicilios)
- ✅ Branding (logos, color corporativo)
- ✅ Series y numeración unificada para todos los tipos de documentos
- ✅ Validación pre-emisión (bloquear si falta configuración)
- ✅ PDFs con datos completos del emisor

**Impacto:** TODOS los módulos que emiten documentos (Ventas, Órdenes, Finanzas, Presupuestos)

---

## 🎯 OBJETIVOS ESPECÍFICOS

1. **Eliminar datos hardcodeados** del modal "Generar factura" y PDFs
2. **Centralizar configuración** en una sola pantalla `/settings/negocio`
3. **Unificar series** de todos los tipos de documento (Invoice, Quote, Receipt, NC, ND)
4. **Validar antes de emitir** que el negocio tenga datos fiscales completos
5. **Mejorar PDFs** con logos y datos profesionales

---

## 📐 ARQUITECTURA DECIDIDA

### Modelos

1. **Business (extendido)**
   - Agregar campos fiscales: legal_name, tax_id, tax_id_type, iva_condition, domicilios, contacto
   - Mantener estructura actual (parent/branches para multi-sucursal)

2. **BusinessBranding (1-to-1 con Business)**
   - logo_horizontal, logo_square, brand_color
   - FileField separados para mejor performance

3. **DocumentSeries (refactor de InvoiceSeries)**
   - Unificar series para: Invoice, Quote, Receipt, CreditNote, DebitNote, DeliveryNote
   - Añadir: document_type, is_default, branch, punto_de_venta
   - Migrar QuoteSequence → DocumentSeries

---

## 🔢 FASES DE IMPLEMENTACIÓN

### ⚙️ FASE 1: Backend - Fundaciones (5-7 días)

#### 1.1 Extender Business con datos fiscales

**Archivos a modificar:**
- `services/api/src/apps/business/models.py`
- `services/api/src/apps/business/serializers.py`
- `services/api/src/apps/business/views.py`
- `services/api/src/apps/business/urls.py`

**Tareas:**

1. **Crear migración:**
```bash
cd services/api
python manage.py makemigrations business --name add_fiscal_fields
```

2. **Agregar campos al modelo Business:**
```python
# En Business model
legal_name = models.CharField(max_length=255, blank=True)
trade_name = models.CharField(max_length=255, blank=True)
tax_id_type = models.CharField(max_length=16, choices=TAX_ID_TYPE_CHOICES, blank=True)
tax_id = models.CharField(max_length=64, blank=True, db_index=True)
iva_condition = models.CharField(max_length=32, choices=IVA_CONDITION_CHOICES, blank=True)
iibb = models.CharField(max_length=64, blank=True)
business_start_date = models.DateField(null=True, blank=True)
commercial_address = models.TextField(blank=True)
fiscal_address = models.TextField(blank=True)
email = models.EmailField(blank=True)
phone = models.CharField(max_length=64, blank=True)
website = models.URLField(blank=True)
```

3. **Crear serializer BusinessBillingProfileSerializer:**
```python
class BusinessBillingProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = [
            'legal_name', 'trade_name', 'tax_id_type', 'tax_id',
            'iva_condition', 'iibb', 'business_start_date',
            'commercial_address', 'fiscal_address',
            'email', 'phone', 'website'
        ]
```

4. **Crear endpoint:**
```python
# En views.py
class BusinessBillingProfileView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_settings'
    
    def get(self, request):
        business = getattr(request, 'business')
        serializer = BusinessBillingProfileSerializer(business)
        return Response(serializer.data)
    
    def patch(self, request):
        business = getattr(request, 'business')
        serializer = BusinessBillingProfileSerializer(
            business, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

# En urls.py
path('settings/billing/', BusinessBillingProfileView.as_view(), name='business-billing-profile'),
```

5. **Tests:**
```python
# tests/test_business_settings.py
def test_get_billing_profile(self):
    # Test GET endpoint
    
def test_update_billing_profile(self):
    # Test PATCH endpoint
    
def test_requires_permission(self):
    # Test sin permiso → 403
```

**Verificación:**
```bash
# Migrar
python manage.py migrate

# Test manual
curl http://localhost:8000/api/v1/business/settings/billing/ \
  -H "Authorization: Bearer <token>"
```

---

#### 1.2 Crear BusinessBranding

**Archivos a crear:**
- `services/api/src/apps/business/models.py` (añadir modelo)
- `services/api/src/apps/business/serializers.py` (añadir serializer)
- `services/api/src/apps/business/views.py` (añadir views)

**Tareas:**

1. **Crear migración:**
```bash
python manage.py makemigrations business --name create_business_branding
```

2. **Modelo BusinessBranding:**
```python
class BusinessBranding(models.Model):
    business = models.OneToOneField(
        'business.Business',
        related_name='branding',
        on_delete=models.CASCADE
    )
    logo_horizontal = models.ImageField(
        upload_to='business/logos/',
        null=True,
        blank=True
    )
    logo_square = models.ImageField(
        upload_to='business/logos/',
        null=True,
        blank=True
    )
    brand_color = models.CharField(max_length=7, blank=True)  # HEX
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Branding · {self.business.name}"
```

3. **Serializers:**
```python
class BusinessBrandingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessBranding
        fields = ['logo_horizontal', 'logo_square', 'brand_color', 'updated_at']
        read_only_fields = ['updated_at']
```

4. **Views:**
```python
class BusinessBrandingView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_settings'
    
    def get(self, request):
        business = getattr(request, 'business')
        branding, _ = BusinessBranding.objects.get_or_create(business=business)
        serializer = BusinessBrandingSerializer(branding, context={'request': request})
        return Response(serializer.data)
    
    def patch(self, request):
        business = getattr(request, 'business')
        branding, _ = BusinessBranding.objects.get_or_create(business=business)
        serializer = BusinessBrandingSerializer(
            branding, data=request.data, partial=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

class BusinessBrandingUploadLogoView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_settings'
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        business = getattr(request, 'business')
        branding, _ = BusinessBranding.objects.get_or_create(business=business)
        
        logo_type = request.data.get('logo_type')
        file = request.FILES.get('file')
        
        if logo_type not in ['horizontal', 'square']:
            return Response({'error': 'logo_type debe ser "horizontal" o "square"'}, status=400)
        
        if not file:
            return Response({'error': 'Falta el archivo'}, status=400)
        
        # Validar tamaño (max 2MB)
        if file.size > 2 * 1024 * 1024:
            return Response({'error': 'Archivo muy grande (max 2MB)'}, status=400)
        
        # Guardar
        if logo_type == 'horizontal':
            branding.logo_horizontal = file
        else:
            branding.logo_square = file
        branding.save()
        
        serializer = BusinessBrandingSerializer(branding, context={'request': request})
        return Response(serializer.data)

# URLs
path('settings/branding/', BusinessBrandingView.as_view(), name='business-branding'),
path('settings/branding/upload-logo/', BusinessBrandingUploadLogoView.as_view(), name='business-branding-upload'),
```

5. **Tests:**
```python
def test_upload_logo_horizontal(self):
    # Test upload logo
    
def test_upload_logo_too_large(self):
    # Test validación tamaño
    
def test_get_branding(self):
    # Test GET
```

**Verificación:**
```bash
python manage.py migrate

# Test upload
curl -X POST http://localhost:8000/api/v1/business/settings/branding/upload-logo/ \
  -H "Authorization: Bearer <token>" \
  -F "logo_type=horizontal" \
  -F "file=@logo.png"
```

---

#### 1.3 Refactor InvoiceSeries → DocumentSeries

⚠️ **CRÍTICO: Breaking change - requiere migración de datos**

**Archivos a modificar:**
- `services/api/src/apps/invoices/models.py` (renombrar modelo)
- `services/api/src/apps/invoices/serializers.py`
- `services/api/src/apps/invoices/views.py`
- `services/api/src/apps/sales/models.py` (Quote usa DocumentSeries)
- `services/api/src/apps/sales/quote_serializers.py`

**Estrategia de migración:**
1. Crear DocumentSeries sin modificar InvoiceSeries
2. Migrar datos: InvoiceSeries → DocumentSeries (document_type='invoice')
3. Migrar datos: QuoteSequence → DocumentSeries (document_type='quote')
4. Actualizar ForeignKeys
5. Eliminar InvoiceSeries y QuoteSequence

**Tareas:**

1. **Crear DocumentSeries (sin eliminar InvoiceSeries aún):**

```python
# En invoices/models.py (nuevo modelo)
class DocumentSeries(models.Model):
    class DocumentType(models.TextChoices):
        INVOICE = 'invoice', 'Factura'
        QUOTE = 'quote', 'Presupuesto'
        RECEIPT = 'receipt', 'Recibo'
        CREDIT_NOTE = 'credit_note', 'Nota de Crédito'
        DEBIT_NOTE = 'debit_note', 'Nota de Débito'
        DELIVERY_NOTE = 'delivery_note', 'Remito'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'business.Business',
        related_name='document_series',
        on_delete=models.CASCADE
    )
    document_type = models.CharField(
        max_length=32,
        choices=DocumentType.choices
    )
    code = models.CharField(max_length=8)  # A, B, C, M, X
    prefix = models.CharField(max_length=16, blank=True)
    suffix = models.CharField(max_length=16, blank=True)
    punto_de_venta = models.CharField(max_length=8, blank=True)  # "0001"
    next_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    branch = models.ForeignKey(
        'business.Business',
        null=True,
        blank=True,
        related_name='series_by_branch',
        on_delete=models.CASCADE
    )
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
        parts = [self.code]
        if self.punto_de_venta:
            parts.append(self.punto_de_venta.zfill(4))
        if self.prefix:
            parts.append(self.prefix)
        parts.append(str(number).zfill(8))
        return '-'.join(parts)
```

2. **Migración de datos:**

```python
# En migration file (data migration)
from django.db import migrations

def migrate_invoice_series_to_document_series(apps, schema_editor):
    InvoiceSeries = apps.get_model('invoices', 'InvoiceSeries')
    DocumentSeries = apps.get_model('invoices', 'DocumentSeries')
    
    for old_series in InvoiceSeries.objects.all():
        DocumentSeries.objects.create(
            id=old_series.id,  # Mantener UUID
            business=old_series.business,
            document_type='invoice',
            code=old_series.code,
            prefix=old_series.prefix,
            next_number=old_series.next_number,
            is_active=old_series.is_active,
            is_default=False,  # Por ahora ninguna es default
            created_at=old_series.created_at,
            updated_at=old_series.updated_at,
        )

def migrate_quote_sequence_to_document_series(apps, schema_editor):
    QuoteSequence = apps.get_model('sales', 'QuoteSequence')
    DocumentSeries = apps.get_model('invoices', 'DocumentSeries')
    
    for quote_seq in QuoteSequence.objects.all():
        # Crear serie para presupuestos
        DocumentSeries.objects.get_or_create(
            business=quote_seq.business,
            document_type='quote',
            code='P',  # Código para presupuestos
            defaults={
                'next_number': quote_seq.last_number + 1,
                'is_active': True,
                'is_default': True,
            }
        )

class Migration(migrations.Migration):
    dependencies = [
        ('invoices', '0002_create_document_series'),
        ('sales', '0010_last_migration'),
    ]
    
    operations = [
        migrations.RunPython(
            migrate_invoice_series_to_document_series,
            reverse_code=migrations.RunPython.noop
        ),
        migrations.RunPython(
            migrate_quote_sequence_to_document_series,
            reverse_code=migrations.RunPython.noop
        ),
    ]
```

3. **Actualizar FK en Invoice:**

```python
# En Invoice model
series = models.ForeignKey(
    'invoices.DocumentSeries',  # Cambió de InvoiceSeries
    related_name='invoices',
    on_delete=models.PROTECT
)
```

4. **Actualizar Quote para usar DocumentSeries:**

```python
# En Quote model
series = models.ForeignKey(
    'invoices.DocumentSeries',
    related_name='quotes',
    on_delete=models.PROTECT,
    null=True,  # Temporal para migración
    blank=True
)

# Eliminar campo "number" (ahora lo genera la serie)
# Agregar "number" como PositiveIntegerField (como Invoice)
```

5. **CRUD endpoints para DocumentSeries:**

```python
# En invoices/views.py
class DocumentSeriesListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentSeriesSerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_settings'
    
    def get_queryset(self):
        business = getattr(self.request, 'business')
        queryset = DocumentSeries.objects.filter(business=business)
        
        # Filtros
        doc_type = self.request.query_params.get('document_type')
        if doc_type in DocumentSeries.DocumentType.values:
            queryset = queryset.filter(document_type=doc_type)
        
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset

class DocumentSeriesDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DocumentSeriesSerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_settings'
    
    def get_queryset(self):
        business = getattr(self.request, 'business')
        return DocumentSeries.objects.filter(business=business)

class DocumentSeriesSetDefaultView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_settings'
    
    def post(self, request, pk):
        business = getattr(request, 'business')
        series = get_object_or_404(DocumentSeries, pk=pk, business=business)
        
        # Quitar default de otras series del mismo tipo de documento
        DocumentSeries.objects.filter(
            business=business,
            document_type=series.document_type,
            is_default=True
        ).update(is_default=False)
        
        # Marcar esta como default
        series.is_default = True
        series.save()
        
        return Response(DocumentSeriesSerializer(series).data)

# URLs
path('document-series/', DocumentSeriesListCreateView.as_view(), name='document-series-list'),
path('document-series/<uuid:pk>/', DocumentSeriesDetailView.as_view(), name='document-series-detail'),
path('document-series/<uuid:pk>/set-default/', DocumentSeriesSetDefaultView.as_view(), name='document-series-set-default'),
```

6. **Tests:**
```python
def test_migrate_invoice_series(self):
    # Test migración correcta
    
def test_create_document_series(self):
    # Test crear nueva serie
    
def test_set_default(self):
    # Test marcar como default
    
def test_unique_constraint(self):
    # Test no duplicados
```

**Verificación:**
```bash
python manage.py migrate
python manage.py test apps.invoices.tests.test_document_series
```

---

### 🖥️ FASE 2: Frontend - UI Configuración (7-10 días)

#### 2.1 Crear estructura base `/app/settings/negocio`

**Archivos a crear:**
- `apps/web/src/app/app/settings/negocio/page.tsx`
- `apps/web/src/app/app/settings/negocio/layout.tsx`
- `apps/web/src/app/app/settings/negocio/fiscal/page.tsx`
- `apps/web/src/app/app/settings/negocio/branding/page.tsx`
- `apps/web/src/app/app/settings/negocio/series/page.tsx`

**Tareas:**

1. **Crear layout con tabs:**

```tsx
// apps/web/src/app/app/settings/negocio/layout.tsx
"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

export default function NegocioSettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  
  const tabs = [
    { href: '/app/settings/negocio/fiscal', label: 'Perfil fiscal' },
    { href: '/app/settings/negocio/branding', label: 'Branding' },
    { href: '/app/settings/negocio/series', label: 'Series y comprobantes' },
  ];
  
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold text-slate-900">Configuración del negocio</h1>
        <p className="mt-2 text-slate-500">
          Datos fiscales, branding y series de comprobantes para todos los documentos del sistema.
        </p>
      </header>
      
      <nav className="flex gap-2 border-b border-slate-200">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              'border-b-2 px-4 py-2 text-sm font-semibold transition',
              pathname === tab.href
                ? 'border-slate-900 text-slate-900'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            )}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
      
      {children}
    </div>
  );
}
```

2. **Crear redirect en page.tsx:**

```tsx
// apps/web/src/app/app/settings/negocio/page.tsx
import { redirect } from 'next/navigation';

export default function NegocioSettingsPage() {
  redirect('/app/settings/negocio/fiscal');
}
```

3. **Agregar link en sidebar:**

```tsx
// En sidebar.tsx
{
  label: 'Configuración',
  children: [
    { href: '/app/settings', label: 'General' },
    { href: '/app/settings/negocio/fiscal', label: 'Negocio', permissionKey: 'manage_settings' },  // ✨ NUEVO
    { href: '/app/settings/access', label: 'Roles & Accesos' },
    { href: '/app/settings/branches', label: 'Sucursales' },
  ],
}
```

4. **Agregar card en `/app/settings/page.tsx`:**

```tsx
<Link
  href="/app/settings/negocio/fiscal"
  className="group rounded-xl border border-slate-200 bg-white p-6 hover:border-blue-300 hover:shadow-md transition-all"
>
  <div className="flex items-start gap-4">
    <div className="rounded-lg bg-emerald-100 p-3 text-emerald-700 group-hover:bg-emerald-200 transition-colors">
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    </div>
    <div className="flex-1">
      <h3 className="text-sm font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
        Configuración del negocio
      </h3>
      <p className="mt-1 text-xs text-slate-500">
        Datos fiscales, branding y series de comprobantes
      </p>
    </div>
  </div>
</Link>
```

---

#### 2.2 Implementar Tab "Perfil fiscal"

**Archivos:**
- `apps/web/src/app/app/settings/negocio/fiscal/page.tsx`
- `apps/web/src/app/app/settings/negocio/fiscal/fiscal-form-client.tsx`
- `apps/web/src/features/business-settings/hooks.ts` (crear)
- `apps/web/src/features/business-settings/api.ts` (crear)
- `apps/web/src/features/business-settings/types.ts` (crear)

**Tareas:**

1. **Crear API hooks:**

```typescript
// apps/web/src/features/business-settings/api.ts
import { apiGet, apiPatch } from '@/lib/api/client';
import type { BusinessBillingProfile } from './types';

export function fetchBusinessBillingProfile() {
  return apiGet<BusinessBillingProfile>('/api/v1/business/settings/billing/');
}

export function updateBusinessBillingProfile(data: Partial<BusinessBillingProfile>) {
  return apiPatch<BusinessBillingProfile>('/api/v1/business/settings/billing/', data);
}

// apps/web/src/features/business-settings/hooks.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchBusinessBillingProfile, updateBusinessBillingProfile } from './api';

export function useBusinessBillingProfile() {
  return useQuery({
    queryKey: ['business', 'billing-profile'],
    queryFn: fetchBusinessBillingProfile,
  });
}

export function useUpdateBusinessBillingProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updateBusinessBillingProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['business', 'billing-profile'] });
    },
  });
}

// apps/web/src/features/business-settings/types.ts
export type TaxIdType = 'cuit' | 'cuil' | 'dni' | 'other';

export type IvaCondition =
  | 'responsable_inscripto'
  | 'monotributo'
  | 'exento'
  | 'consumidor_final'
  | 'no_responsable';

export interface BusinessBillingProfile {
  legal_name: string;
  trade_name: string;
  tax_id_type: TaxIdType;
  tax_id: string;
  iva_condition: IvaCondition;
  iibb: string;
  business_start_date: string | null;
  commercial_address: string;
  fiscal_address: string;
  email: string;
  phone: string;
  website: string;
}
```

2. **Crear formulario:**

```tsx
// apps/web/src/app/app/settings/negocio/fiscal/fiscal-form-client.tsx
"use client";

import { useState, useEffect } from 'react';
import { useBusinessBillingProfile, useUpdateBusinessBillingProfile } from '@/features/business-settings/hooks';
import type { BusinessBillingProfile } from '@/features/business-settings/types';

export function FiscalFormClient() {
  const billingQuery = useBusinessBillingProfile();
  const updateMutation = useUpdateBusinessBillingProfile();
  
  const [form, setForm] = useState<Partial<BusinessBillingProfile>>({});
  const [feedback, setFeedback] = useState<string | null>(null);
  
  useEffect(() => {
    if (billingQuery.data) {
      setForm(billingQuery.data);
    }
  }, [billingQuery.data]);
  
  const handleChange = (field: keyof BusinessBillingProfile, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    
    try {
      await updateMutation.mutateAsync(form);
      setFeedback('Guardado correctamente');
    } catch (error) {
      setFeedback('No pudimos guardar los cambios');
    }
  };
  
  if (billingQuery.isLoading) {
    return <div>Cargando...</div>;
  }
  
  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Identificación fiscal</h2>
        <p className="text-sm text-slate-500">Datos legales que aparecerán en todos los comprobantes.</p>
        
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">
              Razón social <span className="text-rose-600">*</span>
            </span>
            <input
              type="text"
              value={form.legal_name || ''}
              onChange={(e) => handleChange('legal_name', e.target.value)}
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
              required
            />
          </label>
          
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Nombre de fantasía (opcional)</span>
            <input
              type="text"
              value={form.trade_name || ''}
              onChange={(e) => handleChange('trade_name', e.target.value)}
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
            />
          </label>
          
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">
              Tipo de documento <span className="text-rose-600">*</span>
            </span>
            <select
              value={form.tax_id_type || ''}
              onChange={(e) => handleChange('tax_id_type', e.target.value)}
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
              required
            >
              <option value="">Seleccionar</option>
              <option value="cuit">CUIT</option>
              <option value="cuil">CUIL</option>
              <option value="dni">DNI</option>
              <option value="other">Otro</option>
            </select>
          </label>
          
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">
              Número de documento <span className="text-rose-600">*</span>
            </span>
            <input
              type="text"
              value={form.tax_id || ''}
              onChange={(e) => handleChange('tax_id', e.target.value)}
              placeholder="30-12345678-9"
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
              required
            />
          </label>
          
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Condición IVA</span>
            <select
              value={form.iva_condition || ''}
              onChange={(e) => handleChange('iva_condition', e.target.value)}
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
            >
              <option value="">Seleccionar</option>
              <option value="responsable_inscripto">Responsable Inscripto</option>
              <option value="monotributo">Monotributo</option>
              <option value="exento">Exento</option>
              <option value="consumidor_final">Consumidor Final</option>
              <option value="no_responsable">No Responsable</option>
            </select>
          </label>
          
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Ingresos Brutos (opcional)</span>
            <input
              type="text"
              value={form.iibb || ''}
              onChange={(e) => handleChange('iibb', e.target.value)}
              placeholder="901-123456-7"
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
            />
          </label>
        </div>
      </section>
      
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Domicilios</h2>
        
        <div className="mt-6 space-y-4">
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">
              Domicilio comercial <span className="text-rose-600">*</span>
            </span>
            <textarea
              value={form.commercial_address || ''}
              onChange={(e) => handleChange('commercial_address', e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
              required
            />
          </label>
          
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Domicilio fiscal (opcional)</span>
            <textarea
              value={form.fiscal_address || ''}
              onChange={(e) => handleChange('fiscal_address', e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
            />
          </label>
        </div>
      </section>
      
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Contacto</h2>
        
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Email</span>
            <input
              type="email"
              value={form.email || ''}
              onChange={(e) => handleChange('email', e.target.value)}
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
            />
          </label>
          
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Teléfono</span>
            <input
              type="tel"
              value={form.phone || ''}
              onChange={(e) => handleChange('phone', e.target.value)}
              className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 focus:border-slate-900 focus:outline-none"
            />
          </label>
        </div>
      </section>
      
      {feedback && (
        <div className="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          {feedback}
        </div>
      )}
      
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={updateMutation.isPending}
          className="rounded-full bg-slate-900 px-6 py-2 font-semibold text-white hover:bg-slate-700 disabled:bg-slate-300"
        >
          {updateMutation.isPending ? 'Guardando...' : 'Guardar cambios'}
        </button>
      </div>
    </form>
  );
}
```

3. **Page wrapper:**

```tsx
// apps/web/src/app/app/settings/negocio/fiscal/page.tsx
import { redirect } from 'next/navigation';
import { getSession } from '@/lib/auth';
import { AccessMessage } from '@/components/app/access-message';
import { FiscalFormClient } from './fiscal-form-client';

export default async function FiscalSettingsPage() {
  const session = await getSession();
  
  if (!session) {
    redirect('/entrar');
  }
  
  const canManage = session.permissions?.manage_settings ?? false;
  
  if (!canManage) {
    return (
      <AccessMessage
        title="Sin acceso"
        description="Tu rol no tiene permiso para editar la configuración del negocio."
      />
    );
  }
  
  return <FiscalFormClient />;
}
```

---

#### 2.3 Implementar Tab "Branding" (similar estructura)

**NO incluyo código completo por brevedad, pero sigue el mismo patrón:**
- Upload de logos con preview
- Color picker
- Preview "Así se verá en comprobantes"

---

#### 2.4 Implementar Tab "Series" (CRUD completo)

**Componentes:**
- Tabla con filtros (document_type, is_active)
- Modal "Nueva serie"
- Botón "Set default"
- Validaciones (unicidad, campos obligatorios)

---

### 🔗 FASE 3: Integración - Documentos usan config central (5-7 días)

#### 3.1 Refactor modal "Generar factura"

**Archivo:** `apps/web/src/components/invoicing/invoice-actions.tsx`

**Cambios:**

1. **Agregar validación de billing profile:**

```tsx
const billingProfileQuery = useBusinessBillingProfile();

const canIssueCheck = useMemo(() => {
  if (!billingProfileQuery.data?.legal_name || !billingProfileQuery.data?.tax_id) {
    return {
      allowed: false,
      reason: 'Completá los datos fiscales del negocio antes de emitir facturas.',
      ctaLabel: 'Ir a Configuración del negocio',
      ctaHref: '/app/settings/negocio/fiscal',
    };
  }
  return { allowed: true };
}, [billingProfileQuery.data]);
```

2. **Mostrar CTA si falta configuración:**

```tsx
{!canIssueCheck.allowed && (
  <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
    <p className="text-sm font-semibold text-amber-800">{canIssueCheck.reason}</p>
    <Link
      href={canIssueCheck.ctaHref!}
      className="mt-2 inline-block rounded-full bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700"
    >
      {canIssueCheck.ctaLabel}
    </Link>
  </div>
)}
```

3. **Remover campos del emisor del formulario** (ya no se piden)

---

#### 3.2 Actualizar serializers de emisión (Backend)

**Archivo:** `services/api/src/apps/invoices/serializers.py`

**Cambios:**

1. **Validar billing profile completo:**

```python
class InvoiceIssueSerializer(serializers.Serializer):
    sale_id = serializers.UUIDField()
    series_code = serializers.CharField(max_length=8, required=False)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    customer_tax_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    customer_address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    
    def validate(self, attrs):
        business = self.context['business']
        
        # Validar billing profile completo
        if not business.legal_name or not business.tax_id:
            raise serializers.ValidationError({
                'billing_profile': 'Completá los datos fiscales del negocio antes de emitir facturas.'
            })
        
        return attrs
    
    def create(self, validated_data):
        # ... resto del código (sin cambios en lógica)
        pass
```

---

#### 3.3 Actualizar PDFs

**Archivo:** `services/api/src/apps/invoices/pdf.py`

**Cambios:**

```python
def render_invoice_pdf(invoice: Invoice) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    margin = 20 * mm
    current_y = height - margin
    
    # ✨ NUEVO: Logo si existe
    if hasattr(invoice.business, 'branding') and invoice.business.branding.logo_horizontal:
        logo_path = invoice.business.branding.logo_horizontal.path
        try:
            pdf.drawImage(logo_path, margin, current_y - 30, width=60*mm, height=20*mm, preserveAspectRatio=True)
            current_y -= 40
        except:
            pass  # Ignorar si falla
    
    # TÍTULO
    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(margin, current_y, f'{invoice.business.legal_name or invoice.business.name}')
    current_y -= 20
    
    # EMISOR (datos fiscales) ✨ NUEVO
    pdf.setFont('Helvetica', 10)
    if invoice.business.tax_id:
        pdf.drawString(margin, current_y, f"{invoice.business.get_tax_id_type_display()}: {invoice.business.tax_id}")
        current_y -= 14
    
    if invoice.business.iva_condition:
        pdf.drawString(margin, current_y, f"Condición IVA: {invoice.business.get_iva_condition_display()}")
        current_y -= 14
    
    if invoice.business.commercial_address:
        pdf.drawString(margin, current_y, f"Domicilio: {invoice.business.commercial_address}")
        current_y -= 14
    
    pdf.drawString(margin, current_y, f"Email: {invoice.business.email or '—'} · Tel: {invoice.business.phone or '—'}")
    current_y -= 20
    
    # Separador
    pdf.line(margin, current_y, width - margin, current_y)
    current_y -= 10
    
    # FACTURA
    pdf.setFont('Helvetica-Bold', 14)
    pdf.drawString(margin, current_y, f"FACTURA {invoice.full_number}")
    pdf.setFont('Helvetica', 10)
    pdf.drawString(margin, current_y - 14, f"Fecha: {invoice.issued_at.strftime('%d/%m/%Y %H:%M')} hs")
    current_y -= 40
    
    # ... resto del PDF (cliente, items, totales)
```

**Similar para:** `apps/sales/quote_pdf.py`

---

### ✅ FASE 4: Pruebas & Deploy (3-5 días)

#### 4.1 Tests E2E

```python
# tests/e2e/test_business_settings_flow.py
def test_complete_flow(self):
    """
    1. Crear negocio
    2. Configurar datos fiscales
    3. Subir logo
    4. Crear serie
    5. Emitir factura
    6. Verificar PDF tiene datos correctos
    """
    # ... implementación
```

#### 4.2 Migración de datos existentes

```bash
# Script manual (ejecutar en producción)
python manage.py shell

>>> from apps.business.models import Business
>>> for b in Business.objects.all():
...     if not b.legal_name:
...         b.legal_name = b.name
...         b.save()
...     # Crear serie default si no tiene
...     from apps.invoices.models import DocumentSeries
...     if not b.document_series.exists():
...         DocumentSeries.objects.create(
...             business=b,
...             document_type='invoice',
...             code='X',
...             is_default=True
...         )
```

---

## 📊 CHECKLIST FINAL

### Backend
- [ ] Migration: Business fiscal fields
- [ ] Migration: BusinessBranding
- [ ] Migration: DocumentSeries (refactor InvoiceSeries)
- [ ] Migration: Data migration (InvoiceSeries + QuoteSequence)
- [ ] Endpoint: GET/PATCH billing profile
- [ ] Endpoint: GET/POST/PATCH branding
- [ ] Endpoint: Upload logo
- [ ] Endpoint: CRUD DocumentSeries
- [ ] Validación: billing profile completo al emitir
- [ ] PDF: render_invoice_pdf con datos fiscales + logo
- [ ] PDF: build_quote_pdf con datos fiscales + logo
- [ ] Tests: Unit tests (models, serializers, views)
- [ ] Tests: Integration tests (emisión bloqueada sin billing profile)

### Frontend
- [ ] Pantalla: /settings/negocio con tabs
- [ ] Tab: Perfil fiscal (formulario + validaciones)
- [ ] Tab: Branding (upload + preview)
- [ ] Tab: Series (CRUD + set default)
- [ ] Sidebar: Link a nueva pantalla
- [ ] Card en /settings: Link a configuración del negocio
- [ ] Modal factura: Validación billing profile + CTA
- [ ] Hooks: useBusinessBillingProfile, useBusinessBranding, useDocumentSeries
- [ ] Tests: E2E smoke test

### Deploy
- [ ] Backup de base de datos
- [ ] Ejecutar migraciones en staging
- [ ] Validar en staging
- [ ] Ejecutar migraciones en producción
- [ ] Script de migración de datos (rellenar legal_name, crear series default)
- [ ] Comunicar cambios al equipo
- [ ] Documentar en README / Changelog

---

## 🚨 NOTAS IMPORTANTES

### Breaking Changes
1. **InvoiceSeries → DocumentSeries:** Requiere migración de datos. Mantener backward compatibility durante 1 release si hay clientes externos.
2. **QuoteSequence → DocumentSeries:** Cambio en lógica de numeración de presupuestos.

### Rollback Plan
Si algo falla:
1. Revertir migraciones: `python manage.py migrate invoices <previous_migration>`
2. Revertir deploy de frontend
3. Restaurar backup de base de datos (último recurso)

### Comunicación
- Informar al equipo antes de migrar
- Email/Slack con resumen de cambios
- Slack channel #dev-releases

---

## 📞 CONTACTO

**Autor:** GitHub Copilot  
**Fecha:** 2026-02-17  
**Versión:** 1.0  
**Próxima revisión:** Al completar Fase 1

---

**¿Listo para empezar?** 🚀

1. Clonar issue en GitHub
2. Crear feature branch: `feature/business-settings-config`
3. Empezar con Commit 1.1 (Business fiscal fields)
