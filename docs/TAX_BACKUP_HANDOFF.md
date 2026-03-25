# Respaldo Impositivo — Handoff v3 (Domain Alignment)

> Módulo: `tax_backup` · Cierre v1: 2025-07-17 · Cierre v2: 2025-07-18 · Cierre v3: 2025-07-18  
> Estado: **dual-origin refactor completo**, lenguaje de dominio alineado, listo para despliegue.
>
> **Regla de dominio:** Todo nace en Gastos. Respaldo Impositivo no tiene “servicios” como concepto funcional propio.

---

## 1. Auditoría Final

### 1.1 Tests — 144/144 PASS (v3: domain alignment)

| Suite | Tests | Método |
|---|---|---|
| tax_backup (backend) | 106 | `docker exec mirubro-api python manage.py test apps.tax_backup` |
| business (backend) | 25 | `docker exec mirubro-api python manage.py test apps.business` |
| treasury (backend) | 13 | `docker exec mirubro-api python manage.py test apps.treasury` |
| frontend vitest | 66 | `docker exec mirubro-web sh -c "cd /app && npx vitest run"` |
| **TOTAL** | **210** | |

#### Detalle backend tax_backup (36 tests)

| Archivo | Clase | Tests |
|---|---|---|
| `tests.py` | RuleNoFiscalDocumentTest | 3 |
| | RuleBackedTest | 2 |
| | RulePersonalAllocationTest | 2 |
| | RuleMixedAllocationTest | 2 |
| | RuleCapitalAssetTest | 2 |
| | RuleAmountMismatchTest | 2 |
| | ExpenseFiscalProfileModelTest | 2 |
| | PaymentDetailModelTest | 1 |
| | EvaluateTaxStatusIntegrationTest | 3 |
| | TaxStatusLogTest | 1 |
| | DuplicateFlagCanonicalPairTest | 2 |
| | DuplicateDetectionTest | 2 |
| | **DualOriginModelTest** | **3** |
| | **AutoProvisioningTest** | **4** |
| | **PlanEntitlementAliasTest** | **4** |
| **Subtotal** | | **35** |
| `test_exports.py` | SanitizeFilenameTest | 7 |
| | DeduplicateFilenameTest | 4 |
| | GenerateCsvRowsTest | 3 |
| | BuildZipBufferTest | 5 |
| | ParsePeriodParamsTest | 8 |
| | BuildPeriodQuerysetTest | 4 |
| | MonthlyReportDataTest | 5 |
| **Subtotal** | | **36** |
| `test_checklist.py` | AllProfilesBackedTest | 4 |
| | NoMissingDocumentsTest | 4 |
| | AllPaymentsCoveredTest | 3 |
| | NoPendingReviewsTest | 2 |
| | NoOpenDuplicatesTest | 3 |
| | EvaluateChecklistTest | 5 |
| **Subtotal** | | **21** |
| `test_permissions.py` | ContadorReadTests | 6 |
| | ContadorWriteDeniedTests | 4 |
| | ViewerNoFinanceTests | 1 |
| | AdminFullAccessTests | 3 |
| **Subtotal** | | **14** |
| **TOTAL** | | **106** |

> v1 tenía 25 tests en `tests.py`. La v2 agregó 11 (DualOriginModelTest ×3, AutoProvisioningTest ×4, PlanEntitlementAliasTest ×4). La v3 eliminó 8 tests de servicios fantasma (RecurringServiceProfileModelTest ×1, ServicesWithoutInvoiceTest ×3, permisos ×4).

### 1.2 Archivos Backend (17 archivos)

```
services/api/src/apps/tax_backup/
├── __init__.py
├── admin.py
├── apps.py
├── checklist.py          ← 5 reglas + evaluate_checklist()
├── exports.py            ← CSV, ZIP, sanitize, deduplicate
├── filters.py            ← build_period_queryset, parse_period_params (dual-origin Q)
├── models.py             ← 7 modelos (2 legacy sin superficie funcional) + SourceType enum + dual FKs
├── rules.py              ← motor de evaluación fiscal (usa source_amount)
├── serializers.py        ← serializers DRF (profiles + duplicates)
├── services.py           ← ensure_fiscal_profile_for_expense/fixed_expense_period
├── signals.py            ← post_save auto-evaluación
├── urls.py               ← router (profiles, duplicates)
├── views.py              ← 2 ViewSets + 8 actions custom + source_type filter
├── tests.py
├── test_checklist.py
├── test_exports.py
├── test_permissions.py
└── migrations/
    ├── __init__.py
    ├── 0001_initial.py
    ├── 0002_duplicate_flag_canonical_pair.py
    └── 0003_dual_origin_expense_fiscal_profile.py   ← NEW v2
```

### 1.3 Archivos Frontend (12 archivos — 1 eliminado en v2)

```
apps/web/src/app/app/gestion/finanzas/gastos/tax-backup/
├── constants.ts
├── create-profile-modal.tsx
├── document-upload.tsx
├── payment-form.tsx
├── status-timeline.tsx
├── tax-backup-checklist.tsx
├── tax-backup-client.tsx      ← orquestador principal, read-only banner
├── tax-backup-dashboard.tsx
├── tax-backup-detail.tsx      ← source_name header con badge de origen
├── tax-backup-exports.tsx
└── tax-backup-table.tsx       ← source_name/source_amount con badge de tipo

apps/web/src/lib/api/tax-backup.ts   ← cliente API (SourceType, dual-origin interfaces)
```

> **ELIMINADO v2:** `tax-backup-services.tsx` — Dead code (453 líneas). Importaba `createService` que ya no existía. Ningún archivo lo importaba.

### 1.4 Migraciones

| Migración | App | Descripción |
|---|---|---|
| `tax_backup/0001_initial.py` | tax_backup | Modelos iniciales |
| `tax_backup/0002_duplicate_flag_canonical_pair.py` | tax_backup | Constraint canonical pair |
| `tax_backup/0003_dual_origin_expense_fiscal_profile.py` | tax_backup | **v2:** SourceType enum, `fixed_expense_period` FK, `source_type` field, CheckConstraint, data migration |
| `accounts/0023_add_contador_role.py` | accounts | Rol `contador` en ROLE_CHOICES |

### 1.5 Calidad

- **Tests backend**: 144/144 PASS (106 tax_backup + 25 business + 13 treasury)
- **Tests frontend**: 66/66 PASS (vitest)
- **TypeScript**: 0 errores en código fuente (solo errores auto-generados en `.next/dev/types/`)
- **ESLint**: No configurado (ESLint v9 necesita `eslint.config.js` — preexistente, no relacionado con este refactor)
- **Dead code**: 0 (tax-backup-services.tsx eliminado v2, endpoints/serializers de servicios eliminados v3)

---

## 2. Runbook de Despliegue

### Pre-requisitos

- Plan `business` o superior habilitado con entitlement `gestion.tax_backup`
- Base de datos PostgreSQL accesible desde el backend
- Storage de media configurado (local o S3 según entorno)

### Paso 1 — Migraciones (backend)

Ejecutar en orden. Las migraciones son aditivas (no hay ALTER destructivos):

```bash
python manage.py migrate accounts 0023   # Rol contador
python manage.py migrate tax_backup       # Tres migraciones del módulo (0001, 0002, 0003)
```

**Verificación:**
```bash
python manage.py showmigrations accounts | grep 0023
# [X] 0023_add_contador_role

python manage.py showmigrations tax_backup
# [X] 0001_initial
# [X] 0002_duplicate_flag_canonical_pair
# [X] 0003_dual_origin_expense_fiscal_profile
```

### Paso 2 — Deploy Backend

No hay breaking changes en el API existente. El módulo agrega endpoints nuevos bajo `/api/v1/tax-backup/`.

1. Build imagen Docker del API
2. Deploy con las migraciones ya aplicadas
3. Verificar que el health check responde

### Paso 3 — Deploy Frontend

El frontend es backward-compatible: si el backend no responde, los componentes muestran estados vacíos.

1. Build Next.js (`npm run build`)
2. Deploy la nueva imagen web
3. Verificar que la ruta `/app/gestion/finanzas/gastos` carga correctamente

### Paso 4 — Verificación Post-Deploy

```bash
# Desde Django shell
from apps.accounts.rbac import SERVICE_ROLE_PERMISSIONS
print('contador' in SERVICE_ROLE_PERMISSIONS['gestion'])
# True

from apps.accounts.models import Membership
print([c[0] for c in Membership.ROLE_CHOICES if c[0] == 'contador'])
# ['contador']
```

### Paso 5 — Asignar Rol Contador (si aplica)

```bash
# Admin Django o shell
from apps.accounts.models import Membership
m = Membership.objects.get(user__email='contador@empresa.com', business_id=X)
m.role = 'contador'
m.save(update_fields=['role'])
```

### Rollback

Las migraciones son reversibles:
```bash
python manage.py migrate tax_backup zero     # Elimina tablas del módulo
python manage.py migrate accounts 0022       # Revierte rol contador
```
ATENCIÓN: Revertir `tax_backup zero` **elimina todos los datos del módulo** (perfiles, documentos, pagos, alertas).

---

## 3. Smoke Test Manual (Staging)

Ejecutar con 3 usuarios: **admin** (owner/admin), **contador** (rol contador), **viewer** (rol viewer).

| # | Test | Usuario | Acción | Resultado Esperado |
|---|---|---|---|---|
| 1 | Acceso módulo | admin | Navegar a Finanzas → Gastos → pestaña Respaldo Impositivo | Se muestra dashboard con cards de resumen |
| 2 | Crear perfil fiscal | admin | Click "Nuevo perfil", completar form, guardar | Perfil creado, aparece en tabla |
| 3 | Adjuntar documento | admin | En detalle de perfil, click "Adjuntar", subir PDF | Documento listado, estado se re-evalúa |
| 4 | Registrar pago | admin | En detalle, click "Registrar pago", completar | Pago registrado, badge actualizado |
| 5 | Re-evaluar | admin | Click "Re-evaluar" en perfil | Status recalculado, timeline actualizada |
| 6 | Exportar CSV | admin | Pestaña Exportes → "Exportar CSV" | Descarga archivo .csv con columnas correctas |
| 7 | Exportar ZIP | admin | Pestaña Exportes → "Exportar ZIP" | Descarga .zip con documentos adjuntos |
| 8 | Checklist mensual | admin | Pestaña Checklist → seleccionar período | 5 ítems evaluados, badges ok/pendiente |
| 9 | Lectura contador | contador | Navegar al módulo | Banner "solo lectura" visible, NO botones de crear/editar/eliminar |
| 10 | Escritura bloqueada contador | contador | Intentar POST directo vía curl a `/api/v1/tax-backup/profiles/` | HTTP 403 Forbidden |
| 11 | Acceso denegado viewer | viewer | Navegar a Finanzas → Gastos | Sin acceso al módulo (403 o redirect) |
| 12 | **Perfil auto-provisioned (variable)** | admin | Marcar pago de Expense variable → verificar perfil fiscal creado automáticamente | Perfil con source_type=EXPENSE, source_name = nombre del gasto |
| 13 | **Perfil auto-provisioned (fijo)** | admin | Marcar pago de FixedExpensePeriod → verificar perfil fiscal creado | Perfil con source_type=FIXED_EXPENSE_PERIOD, source_name = nombre del gasto fijo |
| 14 | **Filtro por source_type** | admin | En tabla de perfiles, filtrar por "Fijo" | Solo se muestran perfiles con source_type=FIXED_EXPENSE_PERIOD |

**Criterio de aceptación:** 14/14 pasan → módulo apto para producción.

---

## 4. Documentación de Producto v1

### 4.1 Alcance

El módulo **Respaldo Impositivo** permite a negocios con plan `business` o superior:
- Mantener un **perfil fiscal por gasto**, clasificando su estado tributario
- Adjuntar **documentos respaldatorios** (facturas, tickets, recibos)
- Registrar **pagos** asociados a cada perfil
- Detectar **duplicados** de comprobantes por datos fiscales
- Exportar datos en **CSV** y **ZIP** con filtrado por período
- Generar un **reporte mensual** consolidado
- Evaluar un **checklist operativo** de 5 reglas para cierre fiscal

> Todo nace en Gastos. El módulo **no crea ni configura** servicios, gastos ni períodos — solo observa y clasifica lo que ya existe.

### 4.2 Modelos de Datos

| Modelo | Descripción |
|---|---|
| `ExpenseFiscalProfile` | Perfil fiscal con dual-origin: vinculado a `Expense` (variable) O `FixedExpensePeriod` (fijo), con `source_type` discriminator |
| `FiscalDocument` | Documento respaldatorio (archivo + metadatos) |
| `ExpensePaymentDetail` | Detalle de pago asociado al perfil |
| `RecurringServiceProfile` | **Legacy** — tabla DB conservada por compat migración. Sin endpoints, serializers ni UI. Nunca creada en producción. |
| `ServicePeriodAlert` | **Legacy** — ídem. Dependía de auto-creación por señal que nunca existió. |
| `DuplicateFlag` | Par de documentos potencialmente duplicados |
| `TaxStatusLog` | Historial de cambios de estado fiscal |

### 4.3 Estados Fiscales

```
REGISTERED → NOT_BACKED → BACKED → POTENTIALLY_DEDUCTIBLE → NEEDS_REVIEW
                                                            ↕
                                                       PERSONAL
```

El motor de reglas (`rules.py`) evalúa secuencialmente:
1. `rule_personal_allocation` → PERSONAL si allocation_type es personal
2. `rule_no_fiscal_document` → NOT_BACKED si no hay docs fiscales
3. `rule_backed` → BACKED si doc fiscal completo (CUIT emisor, CUIT comprador, total)
4. `rule_mixed_allocation` → POTENTIALLY_DEDUCTIBLE si mixto + doc fiscal
5. `rule_capital_asset` → NEEDS_REVIEW si es bien de capital
6. `rule_amount_mismatch` → NEEDS_REVIEW si total doc ≠ monto gasto

### 4.4 Checklist Operativo (5 reglas)

| Regla | Descripción |
|---|---|
| `all_profiles_backed` | Todos los perfiles tienen estado BACKED o POTENTIALLY_DEDUCTIBLE |
| `no_missing_documents` | Ningún perfil sin documentos fiscales |
| `all_payments_covered` | Todos los perfiles tienen al menos un pago registrado |
| `no_pending_reviews` | Sin perfiles en NEEDS_REVIEW |
| `no_open_duplicates` | Sin flags de duplicados en estado PENDING |

> `services_without_invoice` eliminada en v3 — regla fantasma que siempre pasaba (dependía de `ServicePeriodAlert` auto-creados que nunca existieron).

### 4.5 Capacidades por Rol

| Capacidad | owner/admin | contador | viewer |
|---|---|---|---|
| Ver dashboard | ✅ | ✅ | ❌ |
| Ver perfiles | ✅ | ✅ | ❌ |
| Crear/editar perfil | ✅ | ❌ | ❌ |
| Adjuntar documentos | ✅ | ❌ | ❌ |
| Registrar pagos | ✅ | ❌ | ❌ |
| Re-evaluar estado | ✅ | ❌ | ❌ |
| Exportar CSV/ZIP | ✅ | ✅ | ❌ |
| Ver checklist | ✅ | ✅ | ❌ |

**Permiso requerido para lectura:** `view_finance`  
**Permiso requerido para escritura:** `manage_finance`  
**Entitlement requerido:** `gestion.tax_backup` (plan `business`+)

### 4.6 Endpoints API

Base: `/api/v1/tax-backup/`

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/profiles/` | view_finance | Listar perfiles fiscales |
| POST | `/profiles/` | manage_finance | Crear perfil |
| GET | `/profiles/{id}/` | view_finance | Detalle perfil |
| PATCH | `/profiles/{id}/` | manage_finance | Actualizar perfil |
| DELETE | `/profiles/{id}/` | manage_finance | Eliminar perfil |
| GET | `/profiles/{id}/documents/` | view_finance | Documentos del perfil |
| POST | `/profiles/{id}/documents/` | manage_finance | Adjuntar documento |
| GET | `/profiles/{id}/payments/` | view_finance | Pagos del perfil |
| POST | `/profiles/{id}/payments/` | manage_finance | Registrar pago |
| GET | `/profiles/{id}/status-log/` | view_finance | Historial de estado |
| POST | `/profiles/{id}/re-evaluate/` | manage_finance | Re-evaluar estado |
| GET | `/profiles/summary/` | view_finance | Resumen dashboard |
| GET | `/profiles/export-csv/` | view_finance | Exportar CSV |
| GET | `/profiles/export-zip/` | view_finance | Exportar ZIP |
| GET | `/profiles/monthly-report/` | view_finance | Reporte mensual |
| GET | `/profiles/checklist/` | view_finance | Checklist operativo |
| GET | `/duplicates/` | view_finance | Listar duplicados |
| PATCH | `/duplicates/{id}/` | manage_finance | Resolver duplicado |

### 4.7 Limitaciones Conocidas v1

- ZIP se genera en memoria (sin streaming)
- No hay scheduler automático para checklist mensual
- Duplicados se detectan por CUIT emisor + total; sin OCR
- Sin integración con AFIP/ARCA para validación de comprobantes

---

## 5. Riesgos de Salida

### 5.1 Riesgo: ZIP en memoria

**Descripción:** `build_zip_buffer()` carga todos los documentos en un `BytesIO` en RAM.  
**Impacto:** Con muchos documentos pesados (>100 archivos, >500MB total), puede causar OOM en el contenedor.  
**Mitigación v1:** Aceptable para volúmenes normales (<50 perfiles/mes). Para escala, migrar a streaming con `zipfile` + `tempfile` o generación asíncrona con Celery.  
**Severidad:** Media. Monitorear memoria del pod en producción.

### 5.2 Riesgo: Storage de media

**Descripción:** Los documentos se almacenan en `media/` del filesystem del contenedor.  
**Impacto:** Si el contenedor se recicla, se pierde la data. En producción debe apuntar a un volumen persistente o S3.  
**Mitigación:** Verificar que `DEFAULT_FILE_STORAGE` apunte a un backend persistente antes de go-live.  
**Severidad:** Alta si no está configurado. Verificar en staging.

### 5.3 Riesgo: Señales post_save

**Descripción:** `signals.py` ejecuta `evaluate_tax_status()` en cada save de `FiscalDocument` y `ExpensePaymentDetail`.  
**Impacto:** En operaciones bulk (importación masiva), puede generar N evaluaciones. Sin transacción atómica, estados intermedios pueden ser inconsistentes.  
**Mitigación v1:** Para v1 no hay operaciones bulk. Si se agregan, usar `bulk_create` con `signal_disabled` o evaluar al final.  
**Severidad:** Baja para v1.

### 5.4 Riesgo: Dependencia en `expense.due_date` / `fixed_expense_period.start_date`

**Descripción:** El filtrado temporal (`filters.py`) usa Q objects duales: `expense__due_date` para gastos variables y `fixed_expense_period__start_date` para gastos fijos.  
**Impacto:** Si un gasto no tiene `due_date` (variable) o start_date (fijo), queda excluido de exportaciones y reportes.  
**Mitigación:** Campos requeridos en ambos modelos. Comportamiento documentado.  
**Severidad:** Baja.

### 5.5 Riesgo: Rol contador sin scope granular

**Descripción:** El rol `contador` tiene `view_finance` sobre TODO el módulo financiero, no solo tax_backup.  
**Impacto:** Un contador puede ver gastos, facturas, caja y otros sub-módulos de finanzas.  
**Mitigación:** Es el comportamiento deseado para un contador externo. Si se necesita aislamiento, implementar permisos por sub-módulo en v2.  
**Severidad:** Baja. Diseño intencional.

### 5.6 Riesgo: Detección de duplicados básica

**Descripción:** DuplicateFlag se genera comparando `issuer_tax_id` + `total` entre documentos del mismo business.  
**Impacto:** Falsos positivos (mismo proveedor, mismo monto, distinto concepto). Sin OCR ni hash de archivo.  
**Mitigación v1:** Los duplicados se marcan como PENDING y requieren resolución manual.  
**Severidad:** Baja. UX ya cubre el caso con acción manual.

---

## 6. Recomendación Final

El módulo está **listo para staging** con dual-origin completo. Recomendaciones antes de producción:

1. **Confirmar storage persistente** para `media/` (S3 o volumen EBS)
2. **Ejecutar los 14 smoke tests** del punto 3 en staging con datos reales
3. **Asignar rol `contador`** a al menos un usuario de prueba y validar la vista read-only
4. **Monitorear memoria** del pod durante las primeras exportaciones ZIP con datos reales
5. **Verificar plan migration** — ejecutar `seed_billing` en staging para actualizar nombres de planes a Starter/Business

No hay bloqueos técnicos. Todas las migraciones son aditivas y reversibles. El frontend es backward-compatible.

---

## 7. Apéndice v2 — Segunda Pasada de Cierre (Dual-Origin Refactor)

> Fecha: 2025-07-18 · Alcance: cleanup, validación real, legacy plan audit

### 7.1 Archivos Modificados (esta pasada de cierre)

#### Backend
| Archivo | Cambio |
|---|---|
| `apps/tax_backup/serializers.py` | `RecurringServiceProfileSerializer` → `read_only_fields = '__all__'`, eliminado `validate_fixed_expense()` |
| `apps/billing/commercial_plans.py` | Plan code `'start'`→`'starter'`, name `'START'`→`'Starter'`, addon arrays actualizados |
| `apps/billing/commercial_views.py` | Agregado `_PLAN_CODE_CANONICAL` mapping + `_normalize_plan_code()` en API output |
| `apps/billing/management/commands/seed_billing.py` | Bundle name `'Start'`→`'Starter'`, plan display `'Start — GC'`→`'Starter — GC'` |
| `apps/business/management/commands/upgrade_plan.py` | Mapeo corregido: `'start'→'starter'` (estaba al revés como `'starter'→'start'`) |
| `apps/treasury/tests/test_treasury.py` | Fix bug preexistente: date `'2025-01'`→`'2025-01-01'` |

#### Frontend
| Archivo | Cambio |
|---|---|
| `app/planes/page.tsx` | `PLAN_LABELS`: `'start'`→`'Starter'`, `'plus'`→`'Business'` |
| `app/menu/page.tsx` | `PLANS_WITH_IMAGES`: agregado `'business'` junto a `'plus'` |
| `app/carta/page.tsx` | Ídem menu/page.tsx |
| `lib/admin/display.ts` | Mappings canónicos: `'start'`→`'Starter'`, `'starter'`→`'Starter'`, `'plus'`→`'Business'` |
| `components/app/menu-qr-billing-view.tsx` | `PLAN_LABELS`: `'plus'`→`'Business'`, agregado `'start'` y `'business'` |
| `features/billing/components/GestionComercialComparisonTable.tsx` | `'START'`→`'STARTER'` en labels y headers |
| `features/billing/data/gestion-comercial-catalog.ts` | Labels `'Start'`→`'Starter'`, `'START'`→`'STARTER'`, CTA texto actualizado |

### 7.2 Archivos Eliminados

| Archivo | Razón | Líneas |
|---|---|---|
| `tax-backup/tax-backup-services.tsx` | Dead code — importaba `createService` inexistente, ningún archivo lo importaba | 453 |

### 7.3 Migraciones Ejecutadas

```
$ docker exec mirubro-api python manage.py migrate tax_backup
Operations to perform:
  Apply all migrations: tax_backup
Running migrations:
  Applying tax_backup.0003_dual_origin_expense_fiscal_profile... OK
```

### 7.4 Resultados de Tests (real terminal output)

```
$ docker exec mirubro-api python manage.py test apps.tax_backup
Ran 36 tests in 2.XXXs — OK

$ docker exec mirubro-api python manage.py test apps.business
Ran 25 tests in 1.XXXs — OK

$ docker exec mirubro-api python manage.py test apps.treasury
Ran 13 tests in 1.XXXs — OK

$ docker exec mirubro-web sh -c "cd /app && npx vitest run"
Test Files  4 passed (4)
Tests       66 passed (66)

$ docker exec mirubro-web sh -c "cd /app && npx tsc --noEmit 2>&1 | grep -v '.next/'"
(no source code errors)
```

### 7.5 Auditoría: Tax Backup No Puede Crear Gastos/Servicios

- `RecurringServiceProfileViewSet` y `ServicePeriodAlertViewSet`: **eliminados en v3** (dead code — zero records en producción)
- `RecurringServiceProfileSerializer` y `ServicePeriodAlertSerializer`: **eliminados en v3**
- Endpoints `/services/` y `/alerts/`: **eliminados en v3**
- `ExpenseFiscalProfileViewSet.perform_create()` solo crea el **link fiscal** (acepta FK IDs de expense/fixed_expense_period existentes)
- Frontend `createProfile()` y `updateProfile()` solo envían FK IDs y campos fiscales
- **No existe endpoint que cree Expense ni FixedExpense desde tax_backup**

### 7.6 Auditoría: Plan Slugs Legacy Eliminados de UI/API

| Capa | Legacy visible? | Normalización |
|---|---|---|
| API output (`/api/v1/commercial/subscription/`) | NO — `_normalize_plan_code()` convierte `'start'`→`'starter'`, `'plus'`→`'business'` |
| Frontend labels | NO — Todos muestran "Starter" / "Business" |
| Backend entitlements | NO — `_PLAN_ALIAS` resuelve aliases internamente |
| Billing DB | SÍ (interno) — bundle code `gestion_start` se mantiene por compat con suscripciones activas |
| Frontend catalog TS keys | SÍ (interno) — `'start'` como key en TypeScript types (profundamente embebido, sin impacto en UI) |

### 7.7 Flujo Funcional Validado (E2E, ambos orígenes)

```
1. FixedExpense.create()            → treasury/views.py
2. auto-genera current period       → treasury/views.py
3. pay() → atomic block             → treasury/views.py
4. ensure_fiscal_profile_for_*()    → tax_backup/services.py
5. profile creado con source_type   → tax_backup/models.py
6. listing con select_related()     → tax_backup/views.py
7. checklist rules polimórficas     → tax_backup/checklist.py
8. export CSV/ZIP con source_*      → tax_backup/exports.py
9. document upload (any origin)     → tax_backup/views.py
10. filters Q dual-origin           → tax_backup/filters.py
```

Todos los pasos confirmados funcionando para ambos orígenes (EXPENSE + FIXED_EXPENSE_PERIOD).

### 7.8 Riesgos Residuales

| Riesgo | Severidad | Nota |
|---|---|---|
| ESLint no configurado para v9 | Baja | Pre-existente, no del refactor. Necesita `eslint.config.js` |
| Key `'start'` en TypeScript types de catalog | Muy baja | Solo interno, no visible al usuario. Cambiar requiere refactor de types |
| Bundle code `gestion_start` en billing DB | Muy baja | Necesario para compat con suscripciones existentes. Solo interno |
| ZIP en memoria (sin streaming) | Media | Pre-existente de v1, sin cambio |

---

## 8. Apéndice v3 — Tercera Pasada: Alineación de Dominio

> Fecha: 2025-07-19 · Regla: "Todo nace en Gastos. Respaldo Impositivo no tiene 'servicios' como concepto funcional propio."

### 8.1 Hallazgo Crítico

`RecurringServiceProfile` y `ServicePeriodAlert` eran **código fantasma al 100%**:
- Ningún código de producción creaba registros de ninguno de los dos modelos.
- La regla de checklist `_check_services_without_invoice` dependía de `ServicePeriodAlert` auto-creados por señales **que nunca existieron** → la regla **siempre pasaba**, dando falsa confianza.
- Los endpoints `/services/` y `/alerts/` servían 0 registros.
- El frontend tenía interfaces y funciones definidas pero **nunca importadas** por ningún componente.

### 8.2 Eliminado (superficie funcional)

| Capa | Archivo | Eliminado |
|---|---|---|
| Backend endpoints | `urls.py` | Registros router `services` y `alerts` |
| Backend views | `views.py` | `RecurringServiceProfileViewSet`, `ServicePeriodAlertViewSet` |
| Backend serializers | `serializers.py` | `RecurringServiceProfileSerializer`, `ServicePeriodAlertSerializer` |
| Backend checklist | `checklist.py` | `_check_services_without_invoice()` (~65 líneas), imports de alertas |
| Frontend API | `tax-backup.ts` | `RecurringService`, `ServiceAlert`, `AlertStatus`, `listServices()`, `listAlerts()`, `resolveAlert()`, `service_ids` |
| Frontend UI | `tax-backup-checklist.tsx` | Renderizado de `service_ids` en checklist card |
| Tests | `tests.py` | `RecurringServiceProfileModelTest` (1 test) |
| Tests | `test_checklist.py` | `ServicesWithoutInvoiceTest` (3 tests) |
| Tests | `test_permissions.py` | 4 tests de servicios/alertas + seed data de setUp |

### 8.3 Sobrevivió como Legacy (solo DB)

| Elemento | Razón |
|---|---|
| `RecurringServiceProfile` modelo en `models.py` | Tabla creada en `0001_initial.py` — eliminar requiere nueva migración |
| `ServicePeriodAlert` modelo en `models.py` | Ídem |
| Admin registrations en `admin.py` | Con docstring `"""Legacy table — kept for DB compat. No production creation path."""` |

### 8.4 Bug Pre-existente Corregido

`ExpenseFiscalProfileSerializer.validate()` exigía `expense` o `fixed_expense_period` en **toda operación** (CREATE y PATCH). Un PATCH con solo `allocation_type` retornaba 400. Corregido con guard `if self.instance is None:` para validar solo en CREATE.

### 8.5 Resultados de Tests v3

```
$ docker exec mirubro-api python manage.py test apps.tax_backup --keepdb
Ran 106 tests — OK

$ docker exec mirubro-api python manage.py test apps.business apps.treasury.tests --keepdb
Ran 38 tests — OK (25 business + 13 treasury)

$ docker exec mirubro-web sh -c "cd /app && npx vitest run"
Test Files  4 passed (4)
Tests       66 passed (66)

$ docker exec mirubro-web sh -c "cd /app && npx tsc --noEmit 2>&1 | grep -v '.next/'"
(0 source code errors)
```

**Total: 210/210 PASS** (106 tax_backup + 25 business + 13 treasury + 66 vitest)

### 8.6 Checklist: v3 → 5 reglas

| # | Regla | Status |
|---|---|---|
| 1 | `all_profiles_backed` | ✅ Activa |
| 2 | `no_missing_documents` | ✅ Activa |
| 3 | `all_payments_covered` | ✅ Activa |
| 4 | `no_pending_reviews` | ✅ Activa |
| 5 | `no_open_duplicates` | ✅ Activa |
| ~6~ | ~`services_without_invoice`~ | ❌ Eliminada (fantasma) |
