# Fase 1 Implementation Summary - Business Configuration System

## 📋 Overview

Se ha completado la **Fase 1** de la implementación del sistema centralizado de configuración de negocios, incluyendo:

- ✅ Datos fiscales y legales del emisor (BusinessBillingProfile)
- ✅ Branding corporativo (BusinessBranding)
- ✅ Sistema unificado de series de documentos (DocumentSeries)
- ✅ Endpoints REST API para gestión
- ✅ Actualización de generadores de PDF
- ✅ Helper service para acceso centralizado

---

## 🗂️ Files Modified/Created

### Backend Models

#### 1. `services/api/src/apps/business/models.py`
**Status:** ✅ Modified
**Changes:**
- Added `BusinessBillingProfile` model (OneToOne with Business)
  - Fields: legal_name, tax_id, tax_id_type, vat_condition, addresses, contact info
  - Method: `is_complete()` - validates if profile has required data for emission
- Added `BusinessBranding` model (OneToOne with Business)
  - Fields: logo_horizontal, logo_square, accent_color
- Updated `post_save` signal to auto-create both profiles on Business creation

#### 2. `services/api/src/apps/invoices/models.py`
**Status:** ✅ Modified
**Changes:**
- Added `DocumentSeries` model - unified numbering system for all document types
  - Supports: invoice, quote, receipt, credit_note, debit_note, delivery_note
  - Fields: document_type, letter, prefix, suffix, point_of_sale, next_number, is_active, is_default
  - Method: `get_next_number()` - atomic number increment with `select_for_update()`
  - Method: `format_full_number()` - formats number as "0001-00000123"
- Marked `InvoiceSeries` as DEPRECATED (kept for backward compatibility)

### Backend Serializers

#### 3. `services/api/src/apps/business/serializers.py`
**Status:** ✅ Modified
**Changes:**
- Added `BusinessBillingProfileSerializer`
  - Includes `is_complete` field (read-only)
  - Display fields for enums (tax_id_type_display, vat_condition_display)
  - Validates tax_id format (XX-XXXXXXXX-X)
- Added `BusinessBrandingSerializer`
  - SerializerMethodFields for full URLs: logo_horizontal_url, logo_square_url
  - Uses `request.build_absolute_uri()` for complete logo paths

#### 4. `services/api/src/apps/invoices/serializers.py`
**Status:** ✅ Modified
**Changes:**
- Added `DocumentSeriesSerializer`
  - Includes document_type_display and business_name (read-only)
  - Validates uniqueness constraint (business + document_type + letter + point_of_sale)
  - Validates only one default series per document type

### Backend Views

#### 5. `services/api/src/apps/business/views.py`
**Status:** ✅ Modified
**Changes:**
- Added `BusinessBillingProfileView` (GET, PATCH)
  - Permission: `manage_commercial_settings`
  - Endpoint: `/api/business/settings/billing/`
- Added `BusinessBrandingView` (GET, PATCH)
  - Permission: `manage_commercial_settings`
  - Endpoint: `/api/business/settings/branding/`

#### 6. `services/api/src/apps/invoices/views.py`
**Status:** ✅ Modified
**Changes:**
- Added `DocumentSeriesListCreateView` (GET, POST)
  - Permission: `manage_commercial_settings`
  - Endpoint: `/api/invoices/document-series/`
- Added `DocumentSeriesDetailView` (PATCH, DELETE)
  - Permission: `manage_commercial_settings`
  - Endpoint: `/api/invoices/document-series/<uuid:pk>/`
  - Delete protection: prevents deletion if series has issued documents
- Added `DocumentSeriesSetDefaultView` (POST)
  - Permission: `manage_commercial_settings`
  - Endpoint: `/api/invoices/document-series/<uuid:pk>/set-default/`
  - Auto-deactivates other default series of same type

### Backend URLs

#### 7. `services/api/src/apps/business/urls.py`
**Status:** ✅ Modified
**Changes:**
- Added route: `settings/billing/` → BusinessBillingProfileView
- Added route: `settings/branding/` → BusinessBrandingView

#### 8. `services/api/src/apps/invoices/urls.py`
**Status:** ✅ Modified
**Changes:**
- Added route: `document-series/` → DocumentSeriesListCreateView
- Added route: `document-series/<uuid:pk>/` → DocumentSeriesDetailView
- Added route: `document-series/<uuid:pk>/set-default/` → DocumentSeriesSetDefaultView

### Backend Services

#### 9. `services/api/src/apps/business/services.py`
**Status:** ✅ Created (NEW)
**Description:** Helper service for centralized business configuration access
**Features:**
- `BusinessDocumentConfig` class:
  - `billing_profile` property (lazy load)
  - `branding` property (lazy load)
  - `is_ready_to_emit()` - checks if business has complete config
  - `get_default_series(document_type)` - gets default series for document type
  - `get_series_by_letter(document_type, letter)` - gets specific series
  - `get_issuer_data()` - returns formatted issuer data dict for PDFs
  - `get_branding_data()` - returns branding data dict
- `get_business_document_config(business)` - factory function
- `get_next_document_number(series_id)` - atomic number fetch wrapper

### PDF Generators

#### 10. `services/api/src/apps/invoices/pdf.py`
**Status:** ✅ Modified
**Changes:**
- Now uses `get_business_document_config()` to get issuer data
- Displays: legal_name, tax_id, vat_condition, commercial_address
- Replaces hardcoded "CUIT: —" with actual data

#### 11. `services/api/src/apps/sales/quote_pdf.py`
**Status:** ✅ Modified
**Changes:**
- Now uses `get_business_document_config()` to get issuer data
- Displays: legal_name, tax_id, vat_condition, addresses, contact info
- Replaces conditional checks with centralized data access

### Migrations

#### 12. `services/api/src/apps/business/migrations/0008_businessbillingprofile_businessbranding.py`
**Status:** ✅ Created
**Description:** Schema migration for new models
**Operations:**
- Creates `business_billing_profile` table
- Creates `business_branding` table
- Both with OneToOne FK to Business

#### 13. `services/api/src/apps/business/migrations/0009_create_profiles_for_existing_businesses.py`
**Status:** ✅ Created
**Description:** Data migration
**Operations:**
- Auto-creates BillingProfile for all existing businesses
- Auto-creates Branding for all existing businesses
- Ensures no business is left without profiles

#### 14. `services/api/src/apps/invoices/migrations/0003_documentseries.py`
**Status:** ✅ Created
**Description:** Schema migration for DocumentSeries
**Operations:**
- Creates `document_series` table
- Adds unique constraint: (business, document_type, letter, point_of_sale)
- Adds index: (business, document_type, is_default)

#### 15. `services/api/src/apps/invoices/migrations/0004_migrate_series_data.py`
**Status:** ✅ Created
**Description:** Data migration
**Operations:**
- Migrates InvoiceSeries → DocumentSeries (document_type='invoice')
- Migrates QuoteSequence → DocumentSeries (document_type='quote', letter='P')
- Infers letter from InvoiceSeries.code format

---

## 📡 API Endpoints

### Business Settings

#### Get Billing Profile
```bash
GET /api/business/settings/billing/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
```
**Response:**
```json
{
  "id": "uuid",
  "business": "uuid",
  "legal_name": "Mi Empresa S.A.",
  "tax_id_type": "CUIT",
  "tax_id_type_display": "CUIT",
  "tax_id": "30-12345678-9",
  "vat_condition": "RI",
  "vat_condition_display": "Responsable Inscripto",
  "legal_address": "Av. Libertador 1234",
  "commercial_address": "Av. Corrientes 5678",
  "city": "Buenos Aires",
  "state_province": "CABA",
  "postal_code": "C1001",
  "country": "Argentina",
  "phone": "+54 11 1234-5678",
  "email": "contacto@miempresa.com",
  "website": "https://miempresa.com",
  "is_complete": true,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

#### Update Billing Profile
```bash
PATCH /api/business/settings/billing/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
Content-Type: application/json

{
  "legal_name": "Mi Empresa S.A.",
  "tax_id_type": "CUIT",
  "tax_id": "30-12345678-9",
  "vat_condition": "RI",
  "legal_address": "Av. Libertador 1234",
  "city": "Buenos Aires",
  "email": "contacto@miempresa.com"
}
```

#### Get Branding
```bash
GET /api/business/settings/branding/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
```
**Response:**
```json
{
  "id": "uuid",
  "business": "uuid",
  "logo_horizontal": "/media/business/2024/01/logo-h.png",
  "logo_horizontal_url": "https://domain.com/media/business/2024/01/logo-h.png",
  "logo_square": "/media/business/2024/01/logo-sq.png",
  "logo_square_url": "https://domain.com/media/business/2024/01/logo-sq.png",
  "accent_color": "#6366f1",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

#### Update Branding
```bash
PATCH /api/business/settings/branding/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
Content-Type: multipart/form-data

logo_horizontal: <file>
accent_color: #6366f1
```

### Document Series

#### List Series
```bash
GET /api/invoices/document-series/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
```
**Response:**
```json
[
  {
    "id": "uuid",
    "business": "uuid",
    "business_name": "Mi Empresa",
    "document_type": "invoice",
    "document_type_display": "Factura",
    "letter": "A",
    "prefix": "FAC",
    "suffix": "",
    "point_of_sale": 1,
    "next_number": 123,
    "is_active": true,
    "is_default": true,
    "branch": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

#### Create Series
```bash
POST /api/invoices/document-series/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
Content-Type: application/json

{
  "document_type": "invoice",
  "letter": "B",
  "prefix": "FAC",
  "point_of_sale": 1,
  "is_active": true,
  "is_default": false
}
```

#### Update Series
```bash
PATCH /api/invoices/document-series/<uuid>/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
Content-Type: application/json

{
  "is_active": false,
  "next_number": 200
}
```

#### Delete Series
```bash
DELETE /api/invoices/document-series/<uuid>/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
```
**Note:** Only allowed if `next_number == 1` (no documents issued)

#### Set as Default
```bash
POST /api/invoices/document-series/<uuid>/set-default/
Authorization: Bearer <token>
X-Business-ID: <business_uuid>
```
**Effect:** Sets this series as default for its document type, deactivates other defaults

---

## 🔧 Database Migrations

### Run Migrations

```bash
cd services/api
python manage.py makemigrations
python manage.py migrate
```

**Migration Order:**
1. `business.0008_businessbillingprofile_businessbranding` - Creates profile tables
2. `business.0009_create_profiles_for_existing_businesses` - Populates profiles
3. `invoices.0003_documentseries` - Creates series table
4. `invoices.0004_migrate_series_data` - Migrates old series data

### Verify Data

```bash
python manage.py shell

from apps.business.models import Business, BusinessBillingProfile, BusinessBranding
from apps.invoices.models import DocumentSeries

# Check profiles created
print(f"Businesses: {Business.objects.count()}")
print(f"Billing Profiles: {BusinessBillingProfile.objects.count()}")
print(f"Brandings: {BusinessBranding.objects.count()}")

# Check series migrated
print(f"Document Series: {DocumentSeries.objects.count()}")
DocumentSeries.objects.values('document_type', 'letter').annotate(count=Count('id'))
```

---

## 🧪 Testing

### Manual Tests to Perform

#### 1. Billing Profile CRUD
- GET `/api/business/settings/billing/` - should return empty profile
- PATCH with complete data
- Verify `is_complete: true`
- GET again - should show updated data
- Verify PDF shows new data

#### 2. Branding CRUD
- GET `/api/business/settings/branding/`
- PATCH with logo_horizontal file
- PATCH with hex color
- Verify URLs are absolute
- Check PDF uses new logo/color

#### 3. Document Series
- GET `/api/invoices/document-series/` - list all
- POST new series for 'quote' type with letter 'P'
- POST duplicate series (should fail - unique constraint)
- PATCH series to set is_default=true
- Verify old default was deactivated
- Try DELETE series with next_number > 1 (should fail)
- DELETE series with next_number == 1 (should succeed)

#### 4. Atomic Number Generation
Test concurrent access (simulate with multiple terminals):
```python
from apps.invoices.models import DocumentSeries
from django.db import transaction

series = DocumentSeries.objects.first()

# Terminal 1
num1 = series.get_next_number()
print(num1)  # e.g., "0001-00000001"

# Terminal 2 (at same time)
num2 = series.get_next_number()
print(num2)  # e.g., "0001-00000002"

# Verify no duplicates
assert num1 != num2
```

#### 5. PDF Generation
- Emit invoice with complete billing profile
- Check PDF shows:
  - Legal name
  - CUIT formatted
  - IVA condition
  - Address
- Emit quote
- Verify same data appears

#### 6. Service Helper
```python
from apps.business.services import get_business_document_config
from apps.business.models import Business

business = Business.objects.first()
config = get_business_document_config(business)

print(config.is_ready_to_emit())  # Should be True if profile complete
print(config.get_issuer_data())  # Should return dict
print(config.get_branding_data())  # Should return dict

series = config.get_default_series('invoice')
print(series)  # Should return DocumentSeries or None
```

---

## 🔐 Permissions

All new endpoints require:
- `IsAuthenticated`
- `HasBusinessMembership`
- `HasPermission` with `manage_commercial_settings`

Users with 'owner' or 'admin' roles typically have this permission.

---

## 📝 Model Constraints

### BusinessBillingProfile
- OneToOne with Business (auto-created on Business save)
- `is_complete()` requires: legal_name, tax_id, vat_condition, legal_address

### BusinessBranding
- OneToOne with Business (auto-created on Business save)
- Images stored in `business/%Y/%m/` path
- accent_color defaults to `#000000`

### DocumentSeries
- **Unique constraint:** (business, document_type, letter, point_of_sale)
- Cannot have multiple default series per document_type
- `get_next_number()` uses `select_for_update()` for atomicity
- point_of_sale range: 1-9999

---

## 🚀 Next Steps (Not in this Phase)

### Frontend (Fase 2)
- [ ] Create settings UI at `/app/settings/negocio`
- [ ] Tabs: Facturación, Branding, Series
- [ ] Form validation with is_complete indicator
- [ ] Logo upload with preview
- [ ] Series CRUD interface
- [ ] Pre-emission validation alerts

### PDF Enhancements (Fase 3)
- [ ] Use logo_horizontal in PDF header
- [ ] Apply accent_color to PDF theme
- [ ] QR code for quote validation
- [ ] Multi-language support

### Advanced Features (Fase 4+)
- [ ] AFIP integration (electronic invoicing)
- [ ] Multiple point-of-sale support
- [ ] Branch-specific series
- [ ] Series templates
- [ ] Bulk series creation

---

## 📚 Code Examples

### Using in Views

```python
from apps.business.services import get_business_document_config

def my_invoice_view(request):
    business = request.business
    config = get_business_document_config(business)
    
    # Check if ready to emit
    if not config.is_ready_to_emit():
        return Response({
            'error': 'Complete billing profile first',
            'profile_url': '/api/business/settings/billing/'
        }, status=400)
    
    # Get default series
    series = config.get_default_series('invoice')
    if not series:
        return Response({
            'error': 'No default invoice series configured'
        }, status=400)
    
    # Get next number atomically
    invoice_number = series.get_next_number()
    
    # Get issuer data for PDF
    issuer = config.get_issuer_data()
    
    # Create invoice...
```

### Using in Signals

```python
from django.db.models.signals import pre_save
from django.dispatch import receiver
from apps.invoices.models import Invoice
from apps.business.services import get_business_document_config

@receiver(pre_save, sender=Invoice)
def validate_invoice_emission(sender, instance, **kwargs):
    if not instance.pk:  # New invoice
        config = get_business_document_config(instance.business)
        if not config.is_ready_to_emit():
            raise ValidationError(
                'Cannot emit invoice. Business billing profile incomplete.'
            )
```

---

## ✅ Implementation Checklist

- [x] Create BusinessBillingProfile model
- [x] Create BusinessBranding model
- [x] Create DocumentSeries model
- [x] Update post_save signals
- [x] Create serializers (BillingProfile, Branding, DocumentSeries)
- [x] Create views for CRUD operations
- [x] Add URL routes
- [x] Create migrations (schema + data)
- [x] Create helper service
- [x] Update invoice PDF generator
- [x] Update quote PDF generator
- [x] Document API endpoints
- [x] Write implementation summary

**Pending Tasks:**
- [ ] Run migrations in development
- [ ] Populate test data
- [ ] Manual testing of all endpoints
- [ ] Write automated tests
- [ ] Frontend implementation (Fase 2)

---

## 🐛 Known Issues / Notes

1. **Old Models:** `InvoiceSeries` and `QuoteSequence` are marked DEPRECATED but not removed to maintain backward compatibility. They should be removed in a future major version after ensuring all code uses `DocumentSeries`.

2. **Logo Storage:** Logo files are stored in `MEDIA_ROOT/business/%Y/%m/`. Ensure:
   - `MEDIA_ROOT` is configured in settings.py
   - `MEDIA_URL` is served in development
   - Production uses cloud storage (S3, etc.)

3. **Atomic Operations:** `DocumentSeries.get_next_number()` uses `select_for_update()` which requires proper transaction handling. Always call within an atomic block or let the view's transaction middleware handle it.

4. **Migration Dependencies:** The data migration `0004_migrate_series_data` depends on both `invoices` and `sales` apps. Ensure both are migrated before running this migration.

---

## 👥 Contributors

- Implementation: GitHub Copilot Agent
- Planning: Based on BUSINESS_SETTINGS_IMPLEMENTATION_PLAN.md
- Audit: BUSINESS_SETTINGS_AUDIT.md

---

**Generated:** 2024-01-15  
**Phase:** 1 of 4  
**Status:** ✅ Complete and ready for testing
