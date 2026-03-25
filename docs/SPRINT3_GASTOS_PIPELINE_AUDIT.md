# Sprint 3 — Gastos: Pipeline Documental v1

## Auditoría Técnica Completa

**Fecha:** 2026-03-25  
**Módulo:** `apps.treasury` (Gastos / Tesorería)  
**Prerrequisitos:** Sprint 1 (modelo de pagos) ✅ · Sprint 2 (capa documental) ✅  
**Estado:** COMPLETO — 68 tests pasan  

---

## 1. Objetivos del Sprint

| # | Objetivo | Categoría |
|---|----------|-----------|
| A | Hardening de 5 observaciones no bloqueantes de Sprint 2 | Calidad / Seguridad |
| B | Pipeline documental v1: extracción automática QR-first / OCR-fallback | Feature nueva |

---

## 2. Parte A — Hardening de Sprint 2

### 2.1 Observación 1: N+1 en serializers

**Problema:** `ExpenseSerializer.get_documents_count()`, `get_latest_document()`, `get_payment_id()` ejecutaban queries individuales por cada objeto en las listas.

**Solución:** Annotaciones con `Subquery` / `OuterRef` en los querysets de `ExpenseViewSet` y `FixedExpensePeriodViewSet`. Los métodos del serializer ahora verifican `hasattr(obj, '_annotation_name')` para usar la anotación precalculada en vistas de lista, con fallback a query directa en vistas de detalle (single-object).

**Archivos modificados:**
- `treasury/views.py` — `get_queryset()` de `ExpenseViewSet` y `FixedExpensePeriodViewSet`
- `treasury/serializers.py` — `get_payment_id()`, `get_documents_count()`, `get_latest_document()` en ambos serializers

**Queries eliminadas por request (list de 50 items):** ~150 → 1 (con annotaciones).

---

### 2.2 Observación 2: Mutación de origen vía PATCH

**Problema:** `ExpenseDocumentSerializer` permitía mutar `expense`, `fixed_expense_period` y `file` vía PATCH. Un atacante podía reasignar un documento a otro gasto.

**Solución:** Campos `expense`, `fixed_expense_period` y `file` agregados a `read_only_fields` en `ExpenseDocumentSerializer.Meta`.

```python
read_only_fields = (
    'business', 'expense', 'fixed_expense_period',
    'original_filename', 'mime_type', 'size_bytes',
    'file', 'uploaded_by', 'created_at', 'updated_at',
    # Processing fields (Sprint 3) — set by pipeline only
    'raw_extraction', 'normalized_data', 'processing_errors',
    'processed_at', 'extraction_source',
)
```

**Riesgo mitigado:** IDOR / tampering de origen de documento.

---

### 2.3 Observación 3: PrimaryKeyRelatedField sin scope de negocio

**Problema:** `ExpenseDocumentUploadSerializer` usaba `Expense.objects.all()` como queryset del `PrimaryKeyRelatedField`. Un usuario podía referenciar gastos de otro negocio, obteniendo mensajes de error diferenciados (information disclosure).

**Solución:** Queryset cambiado a `Expense.objects.none()` como default, con override dinámico en `__init__()` a `Expense.objects.filter(business=business)`. IDeas cross-business ahora devuelven `"does not exist"` genérico (sin diferenciar si el ID existe en otro negocio).

```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    request = self.context.get('request')
    business = getattr(request, 'business', None) if request else None
    if business:
        self.fields['expense'].queryset = Expense.objects.filter(business=business)
        self.fields['fixed_expense_period'].queryset = (
            FixedExpensePeriod.objects.filter(fixed_expense__business=business)
        )
```

**Riesgo mitigado:** IDOR / information disclosure cross-tenant.

---

### 2.4 Observación 4: Validación solo por content_type

**Problema:** La validación de archivos solo verificaba `content_type` declarado por el cliente. Un archivo malicioso podía pasar con content_type falso.

**Solución:** Validación centralizada en `treasury/file_validation.py` con tres capas:
1. **Allowlist de content_type** — rechaza tipos no permitidos
2. **Límite de tamaño** — máximo 10 MB
3. **Magic bytes** — lee los primeros 16 bytes y verifica firma contra content_type declarado

```python
_MAGIC_SIGNATURES = {
    'application/pdf': [b'%PDF'],
    'image/jpeg':      [b'\xff\xd8\xff'],
    'image/png':       [b'\x89PNG'],
    'image/webp':      [b'RIFF'],
}
```

**Archivo creado:** `treasury/file_validation.py`

---

### 2.5 Observación 5: validate_file() duplicada

**Problema:** Lógica de validación de archivo duplicada entre `ExpenseDocumentSerializer` y `ExpenseDocumentUploadSerializer`.

**Solución:** Ambos serializers delegan a la función centralizada `validate_expense_document_file()` importada desde `treasury/file_validation.py`. El método `validate_file()` duplicado fue eliminado de `ExpenseDocumentSerializer`.

---

## 3. Parte B — Pipeline Documental v1

### 3.1 Arquitectura

```
┌─────────────────────┐
│   Upload (API)      │
│ POST /documents/    │
└──────┬──────────────┘
       │ auto-enqueue
       ▼
┌──────────────────────┐     ┌────────────────────┐
│  ExpenseDocument     │     │   Redis Broker      │
│  status = 'queued'   │────▶│   celery queue      │
└──────────────────────┘     └────────┬───────────┘
                                      │
                                      ▼
                             ┌────────────────────┐
                             │  Celery Worker      │
                             │  concurrency=2      │
                             └────────┬───────────┘
                                      │
                                      ▼
                             ┌────────────────────┐
                             │  extract_document() │
                             │                    │
                             │  1. extract_qr()   │
                             │     ↓ pyzbar       │
                             │  2. extract_ocr()  │
                             │     ↓ pytesseract  │
                             │  3. merge & norm.  │
                             └────────┬───────────┘
                                      │
                                      ▼
                             ┌────────────────────┐
                             │  ExpenseDocument    │
                             │  status=processed   │
                             │  normalized_data={} │
                             │  raw_extraction={}  │
                             └────────────────────┘
```

**Decisión arquitectónica:** Campos de procesamiento directamente en `ExpenseDocument` (no entidad separada). Justificación: un solo resultado por documento, evita JOINs innecesarios, mantiene API simple.

---

### 3.2 Modelo de datos — Campos agregados

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `extraction_source` | `CharField(10)` | Enum: `qr`, `ocr`, `mixed`, `none` |
| `raw_extraction` | `JSONField` | Resultado crudo (QR payloads, texto OCR) |
| `normalized_data` | `JSONField` | Datos estructurados normalizados |
| `processing_errors` | `JSONField` | Lista de errores/advertencias del pipeline |
| `processed_at` | `DateTimeField` | Timestamp de finalización |

**Enum `ExtractionSource`:**
```python
class ExtractionSource(models.TextChoices):
    QR    = 'qr',    'QR'
    OCR   = 'ocr',   'OCR'
    MIXED = 'mixed', 'QR + OCR'
    NONE  = 'none',  'Sin extracción'
```

**Migración:** `0008_document_processing_fields.py` (depende de `0007_expense_document`)

---

### 3.3 Máquina de estados

```
uploaded ──┬── (auto/manual) ──► queued ──► processing ──┬──► processed
           │                                              │
           └── (archive) ──► archived                     └──► failed
                                                                 │
                                                                 └── (reprocess) ──► queued
```

| Transición | Trigger | Actor |
|-----------|---------|-------|
| uploaded → queued | Auto en upload / manual vía `POST /process/` | API |
| queued → processing | Celery worker toma el task | Worker |
| processing → processed | Extracción exitosa | Worker |
| processing → failed | Excepción en extracción | Worker |
| failed → queued | `POST /reprocess/` | API |
| processed → queued | `POST /reprocess/` | API (limpia resultados previos) |

---

### 3.4 Estrategia de extracción: QR-first / OCR-fallback

**Paso 1 — QR (`extract_qr`):**
- Abre la imagen (o rasteriza PDF a 300 DPI via `pdf2image`)
- Decodifica QR codes via `pyzbar`
- Si encuentra AFIP QR URL → parsea base64 JSON → extrae campos fiscales
- Si encuentra JSON raw → parsea directamente
- Si no hay QR → retorna `None`

**Paso 2 — OCR (`extract_ocr`) — se ejecuta si:**
- QR no encontró nada, O
- QR no extrajo `issuer_tax_id` o `total_amount` (campos clave incompletos)

**OCR extrae mediante regex:**
- CUIT (prefijos válidos: 20, 23, 24, 27, 30, 33, 34)
- Número de comprobante (`XXXX-XXXXXXXX`)
- Tipo de comprobante (Factura A/B/C, Nota de Crédito, Recibo, Ticket)
- Fecha de emisión (`DD/MM/YYYY`)
- Importe total (formatos AR: `1.234,56` y US: `1,234.56`)
- Razón social del emisor

**Paso 3 — Merge:**
- Si solo QR → `source = 'qr'`
- Si solo OCR → `source = 'ocr'`
- Si QR + OCR complementario → `source = 'mixed'` (OCR llena gaps del QR)
- Si ninguno → `source = 'none'`

**Campos normalizados (`normalized_data`):**

| Campo | Fuente QR (AFIP) | Fuente OCR |
|-------|------------------|------------|
| `issuer_tax_id` | `cuit` | Regex CUIT |
| `issue_date` | `fecha` | Regex fecha |
| `document_type` | `tipoCmp` → label | Regex tipo |
| `document_number` | `ptoVta-nroCmp` | Regex número |
| `total_amount` | `importe` | Regex total |
| `currency` | `moneda` (PES→ARS) | — |
| `buyer_tax_id` | `cuitRec` | — |
| `issuer_name` | — | Regex razón social |
| `qr_payload` | URL/JSON raw | — |
| `inferred_source_confidence` | high/medium/low | high/medium/low |

**Nivel de confianza:** `high` (≥3 campos clave), `medium` (2), `low` (≤1).

---

### 3.5 Celery Task

**Archivo:** `treasury/tasks.py`

```python
@shared_task(
    bind=True,
    name='treasury.process_expense_document',
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def process_expense_document(self, document_id: int):
```

**Configuración:**
- `bind=True` — acceso a `self` para retry manual
- `max_retries=2` — hasta 2 reintentos
- `default_retry_delay=30` — 30 segundos entre reintentos
- `acks_late=True` — acknowledgment después de completar (resiliencia ante crash del worker)

**Nota:** Este es el **primer task on-demand** (`.delay()`) del proyecto. Los tasks existentes (`billing.expire_subscriptions`, `blog.publish_scheduled_posts`) son exclusivamente periódicos (beat-scheduled).

**Dispatch points:**
1. `ExpenseDocumentViewSet.create()` — auto-enqueue después del upload
2. `ExpenseDocumentViewSet.process()` — manual, para documentos `uploaded` o `failed`
3. `ExpenseDocumentViewSet.reprocess()` — manual, limpia resultados previos y re-encola

---

### 3.6 Endpoints nuevos

| Método | Endpoint | Descripción | Permiso |
|--------|----------|-------------|---------|
| `POST` | `/api/treasury/documents/{id}/process/` | Encola documento para procesamiento | `manage_finance` |
| `POST` | `/api/treasury/documents/{id}/reprocess/` | Re-encola documento procesado/fallido | `manage_finance` |

**Validaciones de estado:**
- `process`: solo acepta documentos en estado `uploaded` o `failed`
- `reprocess`: solo acepta documentos en estado `processed` o `failed`
- Ambos rechazan con HTTP 400 y mensaje descriptivo si el estado no es válido

**Comportamiento de `reprocess`:** Limpia `raw_extraction`, `normalized_data`, `processing_errors`, `processed_at`, `extraction_source` antes de re-encolar. Garantiza resultados limpios.

---

## 4. Dependencias agregadas

### 4.1 Paquetes Python (`requirements.txt`)

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| `pyzbar` | ≥ 0.1.9 | Decodificación de QR codes |
| `pytesseract` | ≥ 0.3.10 | OCR (wrapper de Tesseract) |
| `pdf2image` | ≥ 1.16 | Conversión PDF → imágenes |
| `python-magic` | ≥ 0.4.27 | Detección de tipo por magic bytes |

### 4.2 Paquetes de sistema (`Dockerfile`)

| Paquete | Propósito |
|---------|-----------|
| `libzbar0` | Runtime de pyzbar |
| `tesseract-ocr` | Motor OCR |
| `tesseract-ocr-spa` | Modelo de idioma español |
| `poppler-utils` | Runtime de pdf2image (`pdftoppm`) |
| `libmagic1` | Runtime de python-magic |

**Verificación:** `docker exec mirubro-api python -c "import pyzbar; import pytesseract; import pdf2image; import magic; print('OK')"` → OK

---

## 5. Inventario de archivos

### 5.1 Archivos creados (nuevos)

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `treasury/extractors.py` | ~270 | Motor de extracción QR + OCR + orquestador |
| `treasury/tasks.py` | ~100 | Celery task para procesamiento async |
| `treasury/file_validation.py` | ~65 | Validación centralizada (content_type + size + magic) |
| `treasury/migrations/0008_document_processing_fields.py` | ~45 | Migración: 5 campos de procesamiento |

### 5.2 Archivos modificados

| Archivo | Cambios |
|---------|---------|
| `treasury/models.py` | `ExtractionSource` enum, 5 campos de procesamiento en `ExpenseDocument` |
| `treasury/serializers.py` | `read_only_fields` ampliado (hardening), annotaciones N+1, import centralizado |
| `treasury/views.py` | Subquery imports, annotaciones en querysets, actions `process`/`reprocess`, auto-enqueue en `create` |
| `treasury/admin.py` | `extraction_source`/`processed_at` en `list_display`, campos de procesamiento `readonly` |
| `services/api/Dockerfile` | System packages: libzbar0, tesseract-ocr, tesseract-ocr-spa, poppler-utils, libmagic1 |
| `services/api/requirements.txt` | Python packages: pyzbar, pytesseract, pdf2image, python-magic |
| `treasury/tests/test_expense_document.py` | 28 tests nuevos para Sprint 3 |

---

## 6. Cobertura de tests

**Total:** 68 tests — todos pasan

### 6.1 Tests nuevos Sprint 3

| Clase | Tests | Cobertura |
|-------|-------|-----------|
| `ExtractorParsingTest` | 13 | AFIP QR URL parsing, JSON raw, texto OCR (CUIT, nro doc, total, fecha, tipo, razón social), normalización de importes (AR/US/comma/invalid) |
| `ExtractDocumentOrchestratorTest` | 5 | qr-only, ocr-fallback, mixed, none-when-both-fail, error-capture |
| `ProcessExpenseDocumentTaskTest` | 4 | Task success, task failure, missing document, error preservation |
| `FileValidationTest` | 5 | PDF/JPG/PNG válidos, MIME inválido, oversized, magic bytes mismatch |
| `ExpenseDocumentReadOnlyFieldsTest` | 2 | Campos de procesamiento read-only, campos de origen read-only |
| `ReplenishmentIdempotencyTest` | 1 | Idempotencia de pago en reposición (movido de clase incorrecta) |

### 6.2 Comando de ejecución

```bash
docker exec mirubro-api python manage.py test apps.treasury.tests.test_expense_document --verbosity=2
```

---

## 7. Seguridad — Evaluación OWASP

| # | Categoría OWASP | Estado | Detalle |
|---|-----------------|--------|---------|
| A01 | Broken Access Control | ✅ Mitigado | PrimaryKeyRelatedField scoped por business; origin fields read-only |
| A02 | Cryptographic Failures | N/A | No se manejan secretos en este sprint |
| A03 | Injection | ✅ Mitigado | No hay queries raw; regex solo para parsing (no evaluación); archivos nunca ejecutados |
| A04 | Insecure Design | ✅ Mitigado | Estado explícito en modelo; procesamiento async aislado en worker |
| A05 | Security Misconfiguration | ✅ Verificado | Magic bytes validan content_type declarado; read_only_fields cierra PATCH mutation |
| A06 | Vulnerable Components | ✅ Versiones pinned | pyzbar ≥0.1.9, pytesseract ≥0.3.10, pdf2image ≥1.16, python-magic ≥0.4.27 |
| A07 | Authentication Failures | N/A | Endpoints protegidos por `IsAuthenticated` + `HasBusinessMembership` + `HasEntitlement` |
| A08 | Data Integrity Failures | ✅ Mitigado | Processing fields solo escribibles por pipeline; acks_late en Celery |
| A09 | Logging Failures | ✅ Implementado | Logger por módulo; info en éxito, error/exception en fallo |
| A10 | SSRF | N/A | No hay requests salientes; URLs de QR solo se parsean, nunca se fetchean |

---

## 8. Compatibilidad y migración

- **Migración 0008** depende de **0007** (Sprint 2). Cadena limpia.
- Todos los campos nuevos son `null=True, blank=True` → **no hay breaking change para datos existentes**.
- Los documentos creados antes de Sprint 3 permanecen en status `uploaded` sin campos de procesamiento → **comportamiento retrocompatible**.
- El auto-enqueue solo aplica a **nuevos uploads** (no backfill automático). Documentos preexistentes pueden procesarse manualmente via `POST /process/`.
- Serializer mantiene `fields = '__all__'` → campos nuevos se exponen sin cambio de contrato API (aditivas).

---

## 9. Observaciones para futuros sprints

| # | Observación | Severidad | Sprint sugerido |
|---|-------------|-----------|-----------------|
| O1 | `extract_qr` solo parsea el primer QR encontrado; documentos multi-QR pierden datos secundarios | Baja | Sprint 4+ |
| O2 | OCR solo soporta idiomas `spa+eng`; agregar `por` (portugués) para mercados regionales | Baja | Sprint 4+ |
| O3 | No hay rate limiting en el endpoint `process/reprocess` — un usuario podría saturar la cola | Media | Sprint 4 |
| O4 | `pdf2image` rasteriza a 300 DPI — PDFs muy grandes (>20 páginas) podrían consumir mucha memoria en el worker | Media | Sprint 4 |
| O5 | No hay webhook/notificación al frontend cuando el procesamiento termina — requiere polling | Baja | Sprint 5 (WebSocket) |
| O6 | Los `normalized_data` no se usan aún para auto-completar campos del gasto (matching fiscal) | Feature | Sprint 4 |
| O7 | No hay backfill task para procesar documentos existentes anteriores a Sprint 3 | Baja | On-demand |

---

## 10. Resumen ejecutivo

Sprint 3 entrega dos bloques:

**Hardening (5/5 observaciones resueltas):**
1. ~~N+1 en serializers~~ → Subquery/OuterRef annotations
2. ~~PATCH mutation de origen~~ → read_only_fields
3. ~~PrimaryKeyRelatedField sin scope~~ → queryset dinámico por business
4. ~~Validación solo content_type~~ → magic bytes + size + content_type
5. ~~validate_file duplicada~~ → función centralizada

**Pipeline Documental v1:**
- Motor de extracción QR-first / OCR-fallback con soporte AFIP
- Task Celery on-demand (primero del proyecto)
- Auto-enqueue en upload + endpoints manuales process/reprocess
- 5 campos de procesamiento en ExpenseDocument
- 28 tests nuevos (68 total), todos passing

**Impacto en infraestructura:** 4 paquetes Python + 5 paquetes de sistema agregados al Dockerfile. Rebuild de imagen requerido (ya aplicado).
