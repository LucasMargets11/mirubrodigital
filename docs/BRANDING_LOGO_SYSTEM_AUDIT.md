# Auditoría: Sistema de Logo/Branding en MiRubro

> Estado: **READ-ONLY — Solo auditoría. No se modificó ningún archivo.**  
> Alcance: Todos los productos — Gestión Comercial, Carta Online, QR de Reseñas, Carteles.

---

## 1. Resumen Ejecutivo

El sistema de branding de MiRubro usa **dos modelos completamente independientes** para almacenar logos:

| Modelo | App | Scope |
|---|---|---|
| `BusinessBranding` | `business` | Logo global del negocio |
| `MenuBrandingSettings` | `menu` | Logo específico de Carta Online |

Adicionalmente existe un tercer campo de logo en `PublicMenuConfig.logo_url` (URLField), que no se sincroniza automáticamente.

**El logo global (`BusinessBranding`) ya está conectado a QR de Reseñas (página pública) y a Carteles (PDF)**. La fragmentación real existe en Carta Online, que usa su propio logo desacoplado.

El sistema funciona correctamente en producción con S3 — la preocupación histórica sobre `NotImplementedError` en `.path` está resuelta en `resolve_document_logo_path()`.

---

## 2. Estado actual — Gestión Comercial

### Modelo

```python
# business/models.py
class BusinessBranding(models.Model):
    business      = OneToOneField('business.Business', primary_key=True, related_name='branding')
    logo_horizontal = ImageField(upload_to='business/logos/', storage=public_media_storage)
    logo_square     = ImageField(upload_to='business/logos/', storage=public_media_storage)
    accent_color    = CharField(max_length=7, blank=True)
```

- Auto-creado vía signal `post_save` al crear un `Business`.
- `accent_color` = color corporativo (hex, 7 chars, e.g. `#FF5A1F`).
- Storage path en S3: `business/logos/<filename>`

### Endpoints

| Verbo | URL | Función |
|---|---|---|
| `GET` | `/api/v1/business/settings/branding/` | Leer logo URLs y accent_color |
| `PATCH` | `/api/v1/business/settings/branding/` | Actualizar **solo** accent_color |
| `POST` | `/api/v1/business/settings/branding/upload-logo/` | Subir logo (horizontal o square) |

- Permiso requerido: `manage_commercial_settings`
- El upload endpoint acepta `{ file: File, type: 'horizontal' | 'square' }` via multipart.
- El endpoint GET devuelve URLs absolutas vía `request.build_absolute_uri()`.

### Frontend

- `features/gestion/api.ts` → `fetchBusinessBranding()`, `updateBusinessBranding()`, `uploadBusinessLogo()`
- `features/gestion/hooks.ts` → `useBusinessBrandingQuery()`, `useUpdateBusinessBrandingMutation()`, `useUploadBusinessLogoMutation()`
- `features/gestion/types.ts` → `BusinessBranding { logo_horizontal_url, logo_square_url, accent_color }`
- UI en `app/app/gestion/configuracion/negocio/branding-tab.tsx`
  - Validación client-side: max 5 MB, solo `image/*`
  - Preview local vía `FileReader` antes de confirmar upload
  - Subida automática al seleccionar archivo (sin botón "Guardar" separado)

### Service Layer

`BusinessDocumentConfig` en `business/services.py`:
- `.branding` → lazy-load `BusinessBranding` (auto-crea si no existe)
- `.get_invoice_branding()` → devuelve `{logo_header, logo_horizontal, logo_square}` como `ImageFieldFile`

`resolve_document_logo_path(image_field)`:
- Intenta primero `image_field.path` (FileSystemStorage local)
- Si `NotImplementedError` (S3), fallback a `storage.open(name) → BytesIO`
- SVGs filtrados explícitamente (no soportados por ReportLab)
- **Maneja S3 correctamente** — el comentario viejo en `printables/services.py` es obsoleto.

---

## 3. Estado actual — Carta Online

### Modelo

```python
# menu/models.py
class MenuBrandingSettings(models.Model):
    business     = OneToOneField('business.Business', related_name='menu_branding')
    display_name = CharField(...)
    logo_image   = ImageField(upload_to='menu/branding/logos/', storage=public_media_storage)
    palette_primary, palette_secondary, palette_background, palette_text = ...
    font_heading, font_body = ...
    font_scale_heading, font_scale_body = ...

    @property
    def logo_url(self) -> str | None:
        return self.logo_image.url if self.logo_image else None
```

Modelo SEPARADO de `BusinessBranding`. No comparten ningún campo de logo.

### Segundo modelo de logo: `PublicMenuConfig`

```python
class PublicMenuConfig(models.Model):
    logo_url = models.URLField(blank=True, null=True)  # ← URLField, no ImageField
```

Es un string URL arbitrario. Se gestiona vía `PublicMenuConfigSerializer` directamente. **NO** se actualiza automáticamente cuando cambia `MenuBrandingSettings.logo_image`.

### Endpoints

| Verbo | URL | Función |
|---|---|---|
| `GET/PATCH` | `/api/v1/menu/branding/` | Leer/actualizar branding de menú (texto, paleta, fuentes) |
| `POST` | `/api/v1/menu/branding/upload-logo/` | Subir logo del menú |

- Permiso: `manage_menu_branding`
- El upload usa nombre de archivo personalizado: `business/{id}/menu-logo-{timestamp}.{ext}`
- El `MenuBrandingSettingsSerializer.update()` sincroniza `brand_name` → `PublicMenuConfig`, pero **no** sincroniza `logo_url`.

### Frontend

- `features/menu/types.ts` → `MenuBrandingSettings { logo_url: string | null, ... }`
- `features/menu/hooks.ts` → `useMenuBrandingSettings()`, `useUpdateMenuBrandingSettings()`
- `features/menu/api.ts` → `getMenuBrandingSettings()` → `GET /api/v1/menu/branding/`

---

## 4. Estado actual — QR de Reseñas

### Modelo

```python
# reviews/models.py
class ReviewConfig(models.Model):
    # NO tiene campos de logo ni accent_color
    google_place_id, google_review_url, redirect_threshold, mode, trial_ends_at, ...
```

El `ReviewConfig` no tiene branding propio. El logo se toma de `BusinessBranding` en el serializer público.

### Serializer público

```python
# reviews/serializers.py
class PublicReviewConfigSerializer(serializers.ModelSerializer):
    def get_logo_url(self, obj) -> str | None:
        branding = getattr(obj.business, 'branding', None)
        if branding and branding.logo_square:
            # build_absolute_uri si hay request, .url directo si no
            return request.build_absolute_uri(branding.logo_square.url)
        return None

    def get_accent_color(self, obj) -> str | None:
        branding = getattr(obj.business, 'branding', None)
        if branding and branding.accent_color:
            return branding.accent_color
        return None
```

**La página pública de captura de reseñas ya usa `BusinessBranding.logo_square` y `accent_color`.**

### Frontend — página de captura

- `features/reviews/types.ts` → `PublicReviewConfig { logo_url: string | null, accent_color: string | null }`

### Frontend — dashboard privado

- No existe sección de branding en la UI de Reseñas (`app/app/resenas/configuracion/`)
- El negocio debe ir a Gestión → Configuración → Branding para subir/cambiar el logo.

---

## 5. Estado actual — Carteles / PDF

### Flujo de logo en PDF

```
QrPosterGeneratePDFView (reviews/views.py)
  → _try_draw_logo(pdf, business, include_logo, logo_variant, x, y, w, h)
      → resolve_signage_logo(business, logo_variant)   [printables/services.py]
          → get_business_document_config(business)      [business/services.py]
          → .get_invoice_branding()
          → devuelve logo_horizontal / logo_square / logo_horizontal-fallback-square
      → _draw_logo(pdf, logo_field, x, y, max_w, max_h) [printables/pdf.py]
          → resolve_document_logo_path(logo_field)
          → ImageReader(path_or_bytesio)
          → pdf.drawImage(...)
```

Los Carteles PDF ya usan `BusinessBranding` correctamente. La resolución de storage es robusta (FS local + S3 vía `storage.open`).

### Parámetros del poster

```typescript
// reviews/qr-posters/types.ts
export type PosterLogoVariant = 'default' | 'horizontal' | 'square' | 'none';

// PosterFields:
include_logo: boolean;
logo_variant: PosterLogoVariant;
```

### Frontend — preview

- `QrPosterPreview.tsx` muestra un **placeholder de logo** (espacio reservado), **no el logo real**.
- No llama a `useBusinessBrandingQuery()` ni carga la imagen del logo en el preview.
- La imagen real solo aparece en el PDF descargado.

---

## 6. Storage y AWS

### `public_media_storage()` callable

```python
# common/storages.py
def public_media_storage():
    bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '')
    if bucket:
        return S3Boto3Storage()
    return FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
```

- Callable (no clase), usado como `storage=public_media_storage` en ImageFields.
- En S3: `AWS_QUERYSTRING_AUTH = False` → URLs públicas sin firma.
- En dev: archivos locales en `services/api/media/`.

### Qué usa este storage

| Campo | Model | Path en S3 |
|---|---|---|
| `BusinessBranding.logo_horizontal` | `business` | `business/logos/` |
| `BusinessBranding.logo_square` | `business` | `business/logos/` |
| `MenuBrandingSettings.logo_image` | `menu` | `menu/branding/logos/` |
| `MenuCategory.image` | `menu` | `menu/categories/` |
| `MenuItem.image` | `menu` | `menu/items/` |

### S3 y PDFs: estado actual

`resolve_document_logo_path()` maneja S3 correctamente:
1. Intenta `image_field.path` (FileSystemStorage)
2. Si `NotImplementedError` → `storage.open(name) → BytesIO` (S3)
3. `BytesIO` es aceptado directamente por `ImageReader` de ReportLab

**Nota:** El comentario en `printables/services.py` que dice "puede fallar en S3" es **obsoleto**. La implementación actual en `business/services.py` resuelve esto.

---

## 7. Problemas detectados

### P1 — Logo de Carta Online completamente siloed [MAYOR]

`MenuBrandingSettings.logo_image` es un modelo independiente. Un negocio que sube su logo en Gestión → Configuración → Branding **no lo verá automáticamente en su Carta Online**. Debe subir el logo dos veces en dos lugares distintos.

### P2 — `PublicMenuConfig.logo_url` desincronizado [MENOR]

`PublicMenuConfig.logo_url` es un `URLField` (string arbitrario), no un ImageField. No se actualiza automáticamente cuando cambia `MenuBrandingSettings.logo_image`. El serializer `MenuBrandingSettingsSerializer.update()` solo sincroniza `brand_name`, no `logo_url`.

### P3 — Sin validación de tamaño/tipo en el backend [SEGURIDAD]

`BusinessLogoUploadView.post()` delega la validación de tipo al `ImageField` de DRF (que verifica headers de imagen), pero **no valida tamaño de archivo** en el backend. La limitación de 5 MB existe solo en el frontend. Un cliente malicioso puede subir archivos de múltiples GB directamente a la API.

`MenuLogoUploadView` tiene el mismo problema.

### P4 — Sin preview real del logo en Carteles [UX]

`QrPosterPreview.tsx` muestra un placeholder vacío en lugar del logo real del negocio. El usuario no puede saber cómo quedará el logo hasta descargar el PDF.

### P5 — Sin UI de branding en QR de Reseñas [UX]

La configuración de Reseñas (`/app/resenas/configuracion/`) no menciona ni vincula el branding. El usuario no sabe que debe ir a Gestión para configurar el logo.

### P6 — Comentario obsoleto en `printables/services.py` [TÉCNICA]

El comentario dice que el logo "se omite silenciosamente" en S3. Esto fue cierto antes, pero `resolve_document_logo_path()` ya resuelve S3 correctamente. El comentario puede causar confusión.

### P7 — SVGs silenciosamente filtrados [TÉCNICA]

`resolve_document_logo_path()` filtra SVGs sin avisar al usuario. Si un negocio sube su logo en SVG, el PDF saldrá sin logo y no recibirá ningún error ni warning en la UI.

---

## 8. Riesgos de seguridad

| # | Riesgo | Severidad | Ubicación |
|---|---|---|---|
| S1 | Sin límite de tamaño en upload de logo (backend) | Media | `BusinessLogoUploadView`, `MenuLogoUploadView` |
| S2 | Logos servidos desde S3 sin CloudFront ni signed URLs | Baja | `public_media_storage()` |
| S3 | MIME check solo por DRF ImageField (puede bypassearse con políglotos) | Baja | `ImageField` |
| S4 | Ruta en S3 predecible: `business/logos/<filename>` — enumeración posible | Baja | `BusinessBranding.logo_horizontal` |

**S1 es el más accionable**. Agregar `MAX_UPLOAD_SIZE = 5 * 1024 * 1024` y validación en ambas vistas.

---

## 9. Recomendación de arquitectura

### Opción A — Sincronización unidireccional (recomendada, bajo costo)

`MenuBrandingSettings` mantiene su propio `logo_image`, pero se agrega un flag `use_business_logo: boolean`. Si está activo, el `get_logo_url()` resuelve el logo desde `BusinessBranding`. Default = `True` para nuevos negocios.

- Mínima fricción: quien quiere logo distinto en el menú puede hacerlo.
- Sin migración de datos compleja.
- Un solo upload global alcanza para QR Reseñas + Carteles + Carta Online.

### Opción B — Consolidación total

Eliminar `MenuBrandingSettings.logo_image` y usar siempre `BusinessBranding`. `MenuBrandingSettings` guarda solo `display_name`, paleta y fuentes.

- Más limpio arquitecturalmente.
- Requiere migración de datos y un PR mayor.
- Pierde la capacidad de tener logos distintos por producto.

### Opción C — Logo URL derivada en serializer

`MenuBrandingSettingsSerializer.get_logo_url()` verifica primero `MenuBrandingSettings.logo_image`, luego fallback a `BusinessBranding.logo_square`. Sin cambios de modelo.

- Más rápida de implementar.
- No modifica ningún modelo ni migración.
- Silenciosa: si el negocio sube logo en menú luego de haberlo subido globalmente, el menú lo usa; si no hay logo específico del menú, usa el global.

---

## 10. Propuesta de modelo de datos (Opción A)

```python
# menu/models.py — agregar campo
class MenuBrandingSettings(models.Model):
    ...
    use_business_logo = models.BooleanField(default=True)
    # logo_image: se mantiene pero solo se usa si use_business_logo=False

    @property
    def logo_url(self) -> str | None:
        if self.use_business_logo:
            # Delegar a BusinessBranding
            branding = getattr(self.business, 'branding', None)
            if branding and branding.logo_square:
                return branding.logo_square.url
        return self.logo_image.url if self.logo_image else None
```

Migración: `ALTER TABLE menu_menubrandingsettings ADD COLUMN use_business_logo BOOLEAN DEFAULT TRUE`.

---

## 11. Propuesta de endpoints

No se necesitan nuevos endpoints para Opciones A o C. Los existentes son suficientes.

Para la Opción A, `MenuBrandingSettingsSerializer` expone `use_business_logo` en `PATCH`.

---

## 12. Propuesta frontend / componentes

### Fix inmediato: Mostrar logo real en QrPosterPreview

```tsx
// QrPosterPreview.tsx
import { useBusinessBrandingQuery } from '@/features/gestion/hooks';

// En el componente:
const brandingQuery = useBusinessBrandingQuery();
const logoUrl = brandingQuery.data?.logo_square_url;

// En el JSX donde está el placeholder:
{include_logo && logoUrl && (
  <img src={logoUrl} alt="Logo" className="..." />
)}
{include_logo && !logoUrl && (
  <div className="logo-placeholder" />
)}
```

### Fix UX: Enlace a branding desde configuración de Reseñas

En `app/app/resenas/configuracion/review-config-client.tsx`, agregar un bloque informativo:

```tsx
<InfoBanner>
  El logo de tu negocio se toma del branding global.{' '}
  <Link href="/app/gestion/configuracion/negocio">
    Configurar logo y colores →
  </Link>
</InfoBanner>
```

---

## 13. Propuesta para PDF / ReportLab

El flujo actual es correcto y robusto. Las mejoras sugeridas son menores:

1. **Actualizar el comentario obsoleto** en `printables/services.py` sobre S3.
2. **Avisar en el frontend** si el usuario activa `include_logo` pero no tiene logo subido, en lugar de generar PDF silenciosamente sin logo.

```typescript
// QrPosterEditor o componente de controles del poster:
const hasLogo = !!brandingQuery.data?.logo_square_url;
if (fields.include_logo && !hasLogo) {
  // Mostrar warning: "No tenés logo cargado. El PDF se generará sin logo."
}
```

---

## 14. Propuesta para AWS / S3

### Problema: Sin validación de tamaño en backend

```python
# business/views.py — BusinessLogoUploadView.post()
MAX_LOGO_SIZE = 5 * 1024 * 1024  # 5 MB

def post(self, request):
    file_obj = request.data.get('file')
    if file_obj and hasattr(file_obj, 'size') and file_obj.size > MAX_LOGO_SIZE:
        return Response({'error': 'El archivo supera el límite de 5 MB.'}, status=400)
    # ... resto del código
```

Mismo fix para `MenuLogoUploadView`.

### Opción: nombres de archivo no predecibles (seguridad de enumeración)

```python
# Usar UUID en nombre de archivo para evitar enumeración:
import uuid
filename = f"business/logos/{uuid.uuid4()}{ext}"
```

`AWS_S3_FILE_OVERWRITE = False` ya está configurado, lo que es correcto.

---

## 15. Plan de implementación por PRs

| PR | Título | Prioridad | Costo |
|---|---|---|---|
| PR-B1 | **Backend: validación de tamaño en upload de logos** | Alta (seguridad) | Muy bajo (~5 líneas) |
| PR-B2 | **Backend: fix comentario obsoleto en printables/services.py** | Baja | Trivial |
| PR-F1 | **Frontend: logo real en QrPosterPreview** | Media (UX) | Bajo |
| PR-F2 | **Frontend: aviso de branding en config de Reseñas** | Media (UX) | Bajo |
| PR-F3 | **Frontend: warning si include_logo pero sin logo cargado** | Media | Bajo |
| PR-A1 | **Opción C: MenuBrandingSettingsSerializer fallback a BusinessBranding** | Media | Bajo (solo serializer) |
| PR-A2 | **Opción A: campo use_business_logo en MenuBrandingSettings** | Baja | Medio (migración) |

---

## 16. Tests mínimos

```python
# test_logo_upload_size.py
def test_upload_logo_rejects_large_file():
    big_file = BytesIO(b'x' * (6 * 1024 * 1024))
    big_file.name = 'big.png'
    response = client.post('/api/v1/business/settings/branding/upload-logo/',
                           {'file': big_file, 'type': 'horizontal'})
    assert response.status_code == 400

# test_public_review_logo.py
def test_public_review_config_exposes_logo_from_branding():
    business.branding.logo_square = ...  # fixture con imagen
    response = client.get(f'/api/v1/reviews/public/{slug}/')
    assert response.data['logo_url'] is not None

# test_resolve_document_logo_path_s3.py
def test_resolve_logo_path_falls_back_to_storage_open():
    mock_field = Mock()
    mock_field.name = 'test.png'
    mock_field.path = PropertyMock(side_effect=NotImplementedError)
    mock_field.storage.open.return_value.__enter__ = ...
    result = resolve_document_logo_path(mock_field)
    assert isinstance(result, BytesIO)
```

---

## 17. Archivos a modificar (por PR)

### PR-B1 (validación tamaño)
- `services/api/src/apps/business/views.py` — agregar check de tamaño en `BusinessLogoUploadView`
- `services/api/src/apps/menu/views.py` — agregar check de tamaño en `MenuLogoUploadView`

### PR-B2 (comentario obsoleto)
- `services/api/src/apps/printables/services.py` — actualizar comentario en `resolve_signage_logo`

### PR-F1 (logo real en preview)
- `apps/web/src/features/reviews/qr-posters/components/QrPosterPreview.tsx`

### PR-F2 (aviso branding en Reseñas)
- `apps/web/src/app/app/resenas/configuracion/review-config-client.tsx`

### PR-F3 (warning sin logo en poster)
- Componente editor del poster (a determinar cuál según contexto)

### PR-A1 (fallback en serializer)
- `services/api/src/apps/menu/serializers.py` — `MenuBrandingSettingsSerializer.get_logo_url()`

### PR-A2 (campo use_business_logo)
- `services/api/src/apps/menu/models.py` — agregar `use_business_logo`
- `services/api/src/apps/menu/serializers.py` — exponer campo
- Nueva migración en `services/api/src/apps/menu/migrations/`

---

## 18. Decisiones pendientes

| # | Decisión | Opciones | Impacto |
|---|---|---|---|
| D1 | ¿Carta Online usa logo global o mantiene logo propio? | A (flag), B (consolidar), C (fallback en serializer) | Modelo de datos |
| D2 | ¿El preview de Carteles muestra el logo real? | Sí (requiere auth en el componente) / No (mantener placeholder) | UX + complejidad |
| D3 | ¿Agregar validación de tamaño en backend? | Sí / No | Seguridad |
| D4 | ¿Avisar en UI de Reseñas que el logo viene de Gestión? | Sí / No | UX |
| D5 | ¿Migrar `PublicMenuConfig.logo_url` a sincronizarse con MenuBrandingSettings? | Sí (agregar signal/hook en view) / Dejar manual | Consistencia |

---

## Apéndice: Mapa de logos por producto

```
┌─────────────────────────────────────────────────────────────────────┐
│  UPLOAD ÚNICO: Gestión → Configuración → Branding                   │
│  BusinessBranding.logo_horizontal + .logo_square + .accent_color    │
│  Endpoint: POST /api/v1/business/settings/branding/upload-logo/     │
└────────┬──────────────────────────┬───────────────────────────────  ┘
         │                          │
         ▼                          ▼
┌────────────────────┐   ┌────────────────────────────┐
│  QR de Reseñas     │   │  Carteles PDF               │
│  (página pública)  │   │  (qr_posters.py)            │
│                    │   │                             │
│  PublicReview-     │   │  resolve_signage_logo()     │
│  ConfigSerializer  │   │  → get_invoice_branding()   │
│  .get_logo_url()   │   │  → logo_horizontal/square   │
│  ← logo_square     │   │  → _draw_logo() con S3 OK  │
│  ← accent_color    │   │                             │
└────────────────────┘   └─────────────────────────────┘

         ✗ NO conectado:
┌─────────────────────────────────────────────────────┐
│  Carta Online                                       │
│  MenuBrandingSettings.logo_image                    │
│  → UPLOAD SEPARADO:                                 │
│    POST /api/v1/menu/branding/upload-logo/          │
│  → PublicMenuConfig.logo_url (URLField, manual)     │
└─────────────────────────────────────────────────────┘
```
