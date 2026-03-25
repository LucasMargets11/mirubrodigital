# Auditoría Técnica y Funcional — Módulo de Gastos + Respaldo Impositivo

**Proyecto:** Mi Rubro Digital
**Fecha:** 2026-03-25
**Alcance:** Auditoría completa del dominio de gastos, su modelo actual y gap analysis contra el modelo objetivo
**Base de evidencia:** Inspección directa del código fuente en `services/api/src/apps/treasury/`, `services/api/src/apps/tax_backup/`, `services/api/src/apps/inventory/services.py`, `apps/web/src/app/app/gestion/finanzas/gastos/` y archivos relacionados

---

## 1. Resumen ejecutivo

### Diagnóstico general

El módulo de Gastos está **más cerca del modelo objetivo de lo que podría esperarse**, pero tiene **gaps estructurales específicos que deben corregirse antes de avanzar**. Varias decisiones de arquitectura ya están bien tomadas; pero hay acoplamientos, ausencias de entidades, y mezclas semánticas que van a complicar las fases siguientes si no se atacan primero.

### Nivel de deuda técnica: **MEDIO-ALTO**

| Dimensión | Estado |
|-----------|--------|
| Modelo de dominio | Parcialmente correcto. `FixedExpense` + `FixedExpensePeriod` ya es la separación correcta plantilla/período. Pero `Expense` (puntual) embebe pago en sí mismo — no hay entidad `Payment` separada. |
| Separación gasto/pago | **NO EXISTE** — El pago está embebido como campos en `Expense` y `FixedExpensePeriod` (`paid_at`, `paid_account`, `payment_transaction`). No soporta pagos parciales ni múltiples. |
| Separación gasto/comprobante | **CASI LOGRADA** — `FiscalDocument` en tax_backup es independiente, pero solo se vincula a `ExpenseFiscalProfile`, no al gasto directamente. En treasury, `Expense.attachment` y `Transaction.attachment` son campos de archivo sueltos, sin metadata. |
| Respaldo Impositivo | **BIEN DISEÑADO** — Es realmente una capa superpuesta, no crea gastos, tiene su propio pipeline de evaluación de reglas. La arquitectura `ExpenseFiscalProfile` como overlay es correcta. |
| Frontend | Funcional pero va a necesitar rediseño en formularios y flujos cuando lleguen los cambios de modelo. |
| Observabilidad | **MUY BAJA** — Sin audit trail propio, sin métricas, sin celery tasks, sin alertas de vencimiento. |

### Principales hallazgos

1. **El pago NO es entidad propia** — es el gap más crítico contra el modelo objetivo
2. **`ExpenseTemplate` está deprecado pero sigue en DB** — debe eliminarse
3. **No hay noción de "proveedor" en gastos** — solo existe `supplier_name` en reposiciones de stock
4. **El modelo de estados está distribuido en 3 entidades sin coordinación** — gasto, período, perfil fiscal
5. **Cero automatismos**: no hay cron/celery para generar períodos, alertar vencimientos, o procesar documentos
6. **El CSV export de transacciones tiene inyección potencial** — usa concatenación manual, no `csv.writer`

### Viabilidad del rediseño: **ALTA** con migración incremental

El sistema está lo suficientemente desacoplado para hacer un refactor incremental sin reescribir todo. El patrón `FixedExpense` → `FixedExpensePeriod` es reutilizable como base. El overlay de tax_backup ya es independiente y puede seguir siéndolo.

---

## 2. Inventario de evidencia

### Archivos clave inspeccionados

| Archivo | Contenido |
|---------|-----------|
| `services/api/src/apps/treasury/models.py` | 10 modelos: Account, TransactionCategory, Transaction, FixedExpense, FixedExpensePeriod, ExpenseTemplate (deprecado), Expense, Employee, PayrollPayment, TreasurySettings, Budget |
| `services/api/src/apps/treasury/views.py` | 12 ViewSets incluyendo AccountViewSet, TransactionViewSet, ExpenseViewSet, FixedExpenseViewSet, FixedExpensePeriodViewSet, DashboardFinanceSummaryView |
| `services/api/src/apps/treasury/serializers.py` | Serializers con campos computados (balance, current_period_status, source_details, reference_details) |
| `services/api/src/apps/treasury/signals.py` | Signal: Sale.post_save → auto-crea Transaction IN |
| `services/api/src/apps/tax_backup/models.py` | 7 modelos: ExpenseFiscalProfile, FiscalDocument, ExpensePaymentDetail, TaxStatusLog, DuplicateFlag, RecurringServiceProfile (legacy), ServicePeriodAlert (legacy) |
| `services/api/src/apps/tax_backup/services.py` | 2 funciones: ensure_fiscal_profile_for_expense(), ensure_fiscal_profile_for_fixed_expense_period() |
| `services/api/src/apps/tax_backup/rules.py` | 8 reglas de evaluación fiscal + detección de duplicados |
| `services/api/src/apps/tax_backup/views.py` | ExpenseFiscalProfileViewSet (11 actions), DuplicateFlagViewSet |
| `services/api/src/apps/inventory/services.py` | create_stock_replenishment() → auto-crea Expense con is_auto_generated=True |
| `apps/web/src/app/app/gestion/finanzas/gastos/gastos-client.tsx` | Tab switcher: fijos/puntuales/reposiciones/respaldo |
| `apps/web/src/app/app/gestion/finanzas/gastos/fixed-expenses-client.tsx` | Master-detail: lista de gastos fijos + historial de períodos |
| `apps/web/src/app/app/gestion/finanzas/gastos/expenses-client.tsx` | Grid de gastos puntuales pendientes/pagados |
| `apps/web/src/lib/api/treasury.ts` | API client completo con 30+ funciones |
| `apps/web/src/lib/api/tax-backup.ts` | API client tax backup con 17 funciones |

### Modelos/tablas relevantes (treasury)

`Account`, `TransactionCategory`, `Transaction`, `FixedExpense`, `FixedExpensePeriod`, `Expense`, `ExpenseTemplate` (deprecado), `Employee`, `PayrollPayment`, `TreasurySettings`, `Budget`

### Modelos/tablas relevantes (tax_backup)

`ExpenseFiscalProfile`, `FiscalDocument`, `ExpensePaymentDetail`, `TaxStatusLog`, `DuplicateFlag`, `RecurringServiceProfile` (legacy DB-only), `ServicePeriodAlert` (legacy DB-only)

### Endpoints relevantes

```
/api/v1/treasury/expenses/                        CRUD + pay
/api/v1/treasury/fixed-expenses/                   CRUD + periods + ensure-current + generate-periods
/api/v1/treasury/fixed-expense-periods/            CRUD + pay + skip
/api/v1/treasury/transactions/                     CRUD + void + transfer + export-csv + monthly-report
/api/v1/treasury/accounts/                         CRUD + reconcile
/api/v1/treasury/dashboard/finance-summary/        Dashboard aggregate
/api/v1/tax-backup/profiles/                       CRUD + documents + payments + status-log + re-evaluate + summary + export-csv + export-zip + monthly-report + checklist
/api/v1/tax-backup/duplicates/                     GET + PATCH
```

---

## 3. Mapa del dominio actual

### 3.1 `FixedExpense` — Plantilla recurrente ✅

**Propósito real:** Representa una *obligación recurrente* (alquiler, internet, luz). Funciona como template.
**Campos clave:** `name`, `default_amount` (nullable), `due_day` (1-28, nullable), `frequency`, `category`, `is_active`
**Relaciones:** → Business, → TransactionCategory (opcional), ← FixedExpensePeriod (1:N)
**Evaluación:** **BIEN modelado.** La semántica es correcta: es plantilla, no instancia. El nombre `FixedExpense` es discutible (`RecurringExpenseTemplate` sería más preciso), pero es funcional. `default_amount` como nullable es correcto porque soporta montos variables.
**Riesgo:** `unique_together = [business, name]` obliga nombres únicos por negocio, lo cual es razonable pero podría ser restrictivo.

### 3.2 `FixedExpensePeriod` — Instancia de período ✅

**Propósito real:** Una ocurrencia concreta de un gasto fijo en un mes específico.
**Campos clave:** `period` (DateField, primer día del mes), `amount`, `status` (pending/paid/skipped), `due_date` (auto-calculado), `paid_at`, `paid_account`, `payment_transaction`, `notes`
**Relaciones:** → FixedExpense, → Account (pago), → Transaction (pago)
**Evaluación:** **CORRECTO conceptualmente.** Soporta monto variable por período (overrideable en pay action). Tiene `due_date` propio. Es una buena fundación.
**Problema semántico:** El pago está embebido (paid_at, paid_account, payment_transaction) en lugar de ser una entidad separada. **No soporta pagos parciales ni múltiples pagos por período.**

### 3.3 `Expense` — Gasto puntual ⚠️

**Propósito real:** Un gasto único, no recurrente.
**Campos clave:** `name`, `amount`, `due_date`, `status` (pending/paid/cancelled), `paid_at`, `paid_account`, `payment_transaction`, `attachment` (archivo suelto), `source_type`, `source_id`, `is_auto_generated`
**Relaciones:** → Business, → ExpenseTemplate (deprecado, nullable), → TransactionCategory, → Account (pago), → Transaction (pago)
**Evaluación:** Funcional pero con **mezcla conceptual**: el gasto y su pago son la misma entidad. El `attachment` es un FileField plano sin metadata (ni tipo de documento, ni emisor, ni validación fiscal).
**Problema grave:** Al no existir una entidad `Payment`, un gasto puntual solo puede tener UN pago por el monto total. La relación `template` → `ExpenseTemplate` es dead code.

### 3.4 `ExpenseTemplate` — DEPRECADO ❌

**Propósito:** Fue el predecesor de `FixedExpense`. Su `generate_for_month` devuelve 501.
**Estado:** Existe en DB, tiene ViewSet, tiene serializer, pero NO se usa en el frontend (no hay calls a `expense-templates/`).
**Acción requerida:** **Eliminar migración de datos → eliminar modelo.** Es puro dead code.

### 3.5 `Transaction` — Movimiento financiero ✅ (con observaciones)

**Propósito real:** Registro contable de cualquier movimiento de dinero.
**Campos clave:** `direction` (IN/OUT/ADJUST), `amount` (siempre positivo), `status` (posted/voided), `reference_type` + `reference_id` (polimorfismo loose), `transfer_group_id` (UUID para transferencias), `attachment` (FileField suelto)
**Evaluación:** **Bien diseñado como ledger.** El polimorfismo loose con `reference_type`/`reference_id` es pragmático. Los valores válidos de reference_type son: `sale`, `expense`, `fixed_expense_period`, `payroll`, `reconciliation`, `stock_replenishment`.
**Problema:** El `attachment` es un FileField suelto sin metadata. Similar al de `Expense`.

### 3.6 `ExpenseFiscalProfile` (tax_backup) — Overlay fiscal ✅

**Propósito real:** Perfil fiscal de un gasto (fijo o puntual). Es la capa documental/fiscal que se superpone a gastos existentes.
**Campos clave:** `expense` (OneToOne nullable), `fixed_expense_period` (OneToOne nullable), `source_type`, `allocation_type`, `tax_status`, `amount_net`, `amount_vat`, `is_capital_asset`, `review_reason`
**Constraint:** Exactamente UNO de expense/fixed_expense_period debe ser no-null.
**Evaluación:** **Excelente diseño.** La separación gasto ≠ comprobante ≠ validación fiscal está correctamente implementada. El patrón dual-origin con CheckConstraint es sólido.

### 3.7 `FiscalDocument` (tax_backup) — Comprobante fiscal ✅

**Propósito real:** Documento fiscal adjunto a un perfil fiscal (factura, recibo, ticket, etc.)
**Campos clave:** `file`, `document_type`, `issuer_name`, `issuer_tax_id`, `buyer_name`, `buyer_tax_id`, `point_of_sale`, `invoice_number`, `issue_date`, `currency`, `subtotal`, `vat`, `total`, `is_fiscal_document`, `parse_status` (manual/pending/parsed/failed)
**Evaluación:** **Modelo excelente.** Tiene toda la metadata necesaria. El `parse_status` ya prepara para QR/OCR/Textract. El índice compuesto `(issuer_tax_id, invoice_number, issue_date, total)` habilita detección de duplicados.

### 3.8 `ExpensePaymentDetail` (tax_backup) — Detalle de pago fiscal ⚠️

**Propósito real:** Registro del medio de pago para tracking fiscal. **NO es la entidad Payment del dominio de gastos.**
**Campos clave:** `payment_method`, `payment_date`, `amount`, `reference`, `proof_file`
**Evaluación:** Modela el *cómo se pagó* para fines fiscales, pero **es independiente del pago real** registrado en treasury. Hay **duplicación semántica**: el pago se registra en treasury (Expense.paid_at/paid_account) Y en tax_backup (ExpensePaymentDetail). No están vinculados ni sincronizados.

### 3.9 Entidades que NO existen y deberían existir

| Entidad faltante | Justificación |
|-----------------|---------------|
| `Payment` | Entidad propia de pago reutilizable para gastos fijos, puntuales y reposiciones. Hoy el pago es data embebida. |
| `Provider` / `Supplier` | No hay entidad de proveedor. Solo existe `supplier_name` como string en StockReplenishment e `issuer_name`/`issuer_tax_id` en FiscalDocument. |
| `ExpenseDocument` (treasury) | Los FileField sueltos en Expense.attachment y Transaction.attachment no tienen metadata. FiscalDocument cubre lo fiscal, pero falta un modelo documental en treasury para archivos no-fiscales. |

---

## 4. Mapa de flujos actuales

### 4.1 Crear gasto fijo

| Paso | Backend | Frontend | Persistencia |
|------|---------|----------|-------------|
| 1. Usuario clickea "Nuevo Gasto Fijo" | — | `fixed-expenses-client.tsx` modal Create | — |
| 2. Completa: nombre, monto default (opcional), día vencimiento (1-28, opcional) | — | Formulario con name, default_amount, due_day | — |
| 3. POST /api/v1/treasury/fixed-expenses/ | `FixedExpenseViewSet.perform_create()` | — | INSERT FixedExpense |
| 4. Auto-crea período del mes actual | `_ensure_current_period()` → `get_or_create(FixedExpensePeriod)` | — | INSERT FixedExpensePeriod |

**Problemas:**
- No se setea categoría en el form de creación del frontend (pero el modelo lo soporta)
- No se setea `frequency` en el frontend (siempre queda `monthly` por defecto)
- El monto del período auto-creado es `default_amount or 0` — si no hay default_amount, se crea un período con monto 0

### 4.2 Pagar período de gasto fijo

| Paso | Backend | Frontend | Persistencia |
|------|---------|----------|-------------|
| 1. Usuario clickea "Pagar" en período pendiente | — | PayPeriodModal en fixed-expenses-client.tsx | — |
| 2. Selecciona cuenta, opcionalmente cambia monto y fecha | — | Form: account_id, amount (prefilled), paid_at | — |
| 3. POST /api/v1/treasury/fixed-expense-periods/{id}/pay/ | `FixedExpensePeriodViewSet.pay()` | — | Atomic: INSERT Transaction (OUT) + UPDATE FixedExpensePeriod (status=paid) |
| 4. Auto-crea perfil fiscal | `ensure_fiscal_profile_for_fixed_expense_period()` | — | INSERT ExpenseFiscalProfile si tax_backup habilitado |

**Funciona correctamente.** El override de monto es un detalle bien pensado.

### 4.3 Crear gasto puntual

| Paso | Backend | Frontend | Persistencia |
|------|---------|----------|-------------|
| 1. Usuario clickea "Nuevo Gasto" | — | `expenses-client.tsx` modal Create | — |
| 2. Completa: descripción, categoría, monto, fecha vencimiento | — | Form: name, category, amount, due_date | — |
| 3. POST /api/v1/treasury/expenses/ | ExpenseViewSet.perform_create() | — | INSERT Expense |

**Problema:** No hay campo de notas ni adjunto en el form de creación, aunque el modelo los soporta.

### 4.4 Pagar gasto puntual

| Paso | Backend | Frontend | Persistencia |
|------|---------|----------|-------------|
| 1. "Registrar Pago" | — | PayExpenseModal | — |
| 2. Solo selecciona cuenta (sin override de monto) | — | Form: account_id | — |
| 3. POST /api/v1/treasury/expenses/{id}/pay/ | `ExpenseViewSet.pay()` | — | Atomic: INSERT Transaction (OUT) + UPDATE Expense (status=paid) |
| 4. Auto-crea perfil fiscal | `ensure_fiscal_profile_for_expense()` | — | INSERT ExpenseFiscalProfile |

**Problema crítico:** El pago de gasto puntual NO permite override de monto (a diferencia de gasto fijo). El monto siempre es `expense.amount`. El usuario no puede registrar un pago parcial ni un monto diferente al esperado.

### 4.5 Cargar comprobante

| Paso | Backend | Frontend | Persistencia |
|------|---------|----------|-------------|
| 1. En tax-backup, abrir detalle de perfil fiscal | — | `tax-backup-detail.tsx` | — |
| 2. "Adjuntar comprobante" → form con metadata | — | `document-upload.tsx` | — |
| 3. POST /api/v1/tax-backup/profiles/{id}/documents/ | ExpenseFiscalProfileViewSet.documents() | — | INSERT FiscalDocument |
| 4. Signal auto-reevalúa tax_status | post_save(FiscalDocument) → _reevaluate_profile() | — | UPDATE ExpenseFiscalProfile.tax_status, INSERT TaxStatusLog |
| 5. Auto-detecta duplicados | create_duplicate_flags() | — | INSERT DuplicateFlag si match |

**Funciona correctamente.** El flujo es sólido.

### 4.6 Reposición de stock → gasto automático

| Paso | Backend | Persistencia |
|------|---------|-------------|
| 1. Se confirma reposición de stock | `create_stock_replenishment()` | INSERT StockReplenishment + StockMovements |
| 2. Se crea transacción OUT | Mismo servicio | INSERT Transaction (reference_type='stock_replenishment') |
| 3. Se crea/actualiza Expense auto | `Expense.objects.update_or_create(source_type='stock_replenishment')` | INSERT/UPDATE Expense (is_auto_generated=True, status=PAID) |

**Evaluación:** Bien implementado. El `update_or_create` con constraint unique garantiza idempotencia. El bloqueo de `.pay()` para auto-generated es correcto.

### 4.7 Anulación de transacción

| Paso | Backend | Persistencia |
|------|---------|-------------|
| 1. POST /api/v1/treasury/transactions/{id}/void/ | `TransactionViewSet.void()` | UPDATE Transaction (status=voided) |
| 2. Si reference_type='expense' → revierte gasto a pending | Mismo endpoint | UPDATE Expense (status=pending, nullifica paid_*) |
| 3. Si reference_type='fixed_expense_period' → revierte período a pending | Mismo endpoint | UPDATE FixedExpensePeriod (status=pending, nullifica paid_*) |
| 4. Si reference_type='payroll' → desvincula transaction | Mismo endpoint | UPDATE PayrollPayment (transaction=null) |

**Problema:** La anulación NO toca el ExpenseFiscalProfile. Si un gasto pagado ya tenía perfil fiscal con documentos, al anular queda un perfil fiscal huérfano con status inconsistente. **Sin cascada de estado hacia tax_backup.**

---

## 5. Hallazgos críticos

### CRÍTICO

| ID | Hallazgo | Evidencia | Impacto |
|----|----------|-----------|---------|
| C1 | **El pago NO es entidad propia.** El pago está embebido como campos (paid_at, paid_account, payment_transaction) en Expense y FixedExpensePeriod. | `models.py` líneas 122-126 (FixedExpensePeriod), 170-173 (Expense) | Imposibilita pagos parciales, pagos múltiples, historial de intentos de pago, y reutilización entre tipos de gasto |
| C2 | **Duplicación de concepto "pago" entre treasury y tax_backup.** `ExpensePaymentDetail` en tax_backup registra pagos de forma independiente, sin vinculación con el pago real en treasury. | `tax_backup/models.py` ExpensePaymentDetail vs Expense.paid_* | Datos inconsistentes, doble registro manual, imposible reconciliar automáticamente |
| C3 | **Anulación de transacción no propaga a perfil fiscal.** Al anular una transacción vinculada a un gasto pagado, el ExpenseFiscalProfile queda con status inconsistente. | `views.py` void action | Datos fiscales incorrectos, reglas de evaluación sobre estado stale |

### ALTO

| ID | Hallazgo | Evidencia | Impacto |
|----|----------|-----------|---------|
| A1 | **CSV export de transacciones vulnerable a inyección.** Usa concatenación manual con `.replace(',', ';')` en lugar de `csv.writer`. | `views.py` export_csv | Datos corruptos con comillas o newlines en descripciones. Potencial CSV injection. |
| A2 | **No hay modelo de Proveedor.** Los proveedores solo existen como strings en distintos lugares (StockReplenishment.supplier_name, FiscalDocument.issuer_name). | Múltiples archivos | No se puede reutilizar info de proveedores, reportar por proveedor, ni vincular gastos al mismo proveedor |
| A3 | **ExpenseTemplate sigue en DB.** Modelo deprecado con ViewSet activo que devuelve 501. | `models.py` línea 145, `views.py` línea 337 | Dead code, confusión, migración pendiente |
| A4 | **El gasto puntual no permite override de monto al pagar** (pero el gasto fijo sí). | `ExpenseViewSet.pay()`: usa `expense.amount` hardcoded | Inconsistencia funcional entre tipos de gasto |
| A5 | **Cero automatismos.** No hay celery task para: generar períodos de meses futuros, alertar vencimientos, detectar gastos vencidos impagos, o auto-provisionar perfiles fiscales. | `settings.py` CELERY_BEAT_SCHEDULE: 0 tareas de treasury | El sistema depende de que el usuario o el frontend invoquen ensure-current. Silencioso ante deudas |

### MEDIO

| ID | Hallazgo | Evidencia | Impacto |
|----|----------|-----------|---------|
| M1 | **Los `attachment` FileField en Expense y Transaction no tienen metadata.** Son archivos planos, sin tipo de documento, sin validación de formato, sin tamaño máximo. | `models.py` Expense.attachment, Transaction.attachment | No sirven para pipeline documental. Incompatibles con FiscalDocument que sí tiene metadata. |
| M2 | **El form de creación de gasto fijo no incluye categoría ni frecuencia.** El modelo soporta ambos pero el frontend no los expone. | `fixed-expenses-client.tsx` | Pérdida de información de clasificación |
| M3 | **El form de creación de gasto puntual no incluye notas ni adjunto.** | `expenses-client.tsx` | Funcionalidad disponible en API pero no expuesta en UI |
| M4 | **El balance de Account se calcula por query en el serializer** (N+1 potencial en listados). | `serializers.py` AccountSerializer.get_balance() | Performance en businesses con muchas transacciones |
| M5 | **`FixedExpensePeriod.amount` se inicializa en 0 si default_amount es null.** | `views.py` `_ensure_current_period()`: `fixed_expense.default_amount or Decimal('0')` | Períodos con monto 0 que no reflejan la realidad |

### BAJO

| ID | Hallazgo | Evidencia | Impacto |
|----|----------|-----------|---------|
| B1 | **RecurringServiceProfile y ServicePeriodAlert son modelos legacy** que existen en DB pero no tienen superficie funcional. | tax_backup admin docstrings | Limpieza pendiente |
| B2 | **No hay soft-delete en Expense ni FixedExpense.** El delete es hard. | BaseTreasuryViewSet hereda ModelViewSet | Pérdida de datos en eliminación accidental |
| B3 | **PayrollPayment.status usa strings en lugar de TextChoices.** | `models.py` línea 243 | Inconsistencia de estilo con el resto del dominio |

---

## 6. Gap Analysis contra el modelo objetivo

### 6.1 Gastos Fijos

| Aspecto | Estado actual | Estado objetivo | Gap | Impacto |
|---------|--------------|-----------------|-----|---------|
| Modelado como plantilla recurrente | ✅ FixedExpense es plantilla | ✅ Correcto | Ninguno | — |
| Soporte monto fijo o variable | ✅ default_amount nullable, monto overrideable en pay | ✅ Correcto | Ninguno | — |
| Cada período con monto esperado | ⚠️ `amount` existe pero se inicia en 0 si no hay default | Monto esperado significativo | Bajo | Lógico |
| Cada período con monto facturado | ❌ No existe | Debe existir (del comprobante fiscal) | Medio | Requiere vínculo directo con FiscalDocument |
| Cada período con monto pagado | ⚠️ El monto pagado es el `amount` después del override en pay | Debe ser campo explícito o entidad Payment | Medio | Ambigüedad: amount es esperado o pagado? |
| Estado de pago por período | ✅ pending/paid/skipped | ✅ Correcto | Ninguno | — |
| Estado documental/fiscal por período | ✅ Via ExpenseFiscalProfile.tax_status | ✅ Correcto | Ninguno | — |
| Frecuencias no-mensuales | ⚠️ El modelo tiene WEEKLY/QUARTERLY/YEARLY pero `period` es siempre primer-día-del-mes | Soporte real de frecuencias | Medio | La abstracción solo funciona para `monthly` |

### 6.2 Gastos Puntuales

| Aspecto | Estado actual | Estado objetivo | Gap | Impacto |
|---------|--------------|-----------------|-----|---------|
| Registro de egreso único | ✅ Expense funciona | ✅ | Ninguno | — |
| Pagos asociados | ❌ Pago embebido, 1 solo, sin parciales | Entidad Payment separada | **ALTO** | Rediseño de modelo |
| Comprobantes asociados | ⚠️ attachment (plano) + FiscalDocument (via fiscal profile) | Acceso directo a documentos | Medio | El flujo actual obliga a pasar por tax_backup para adjuntar comprobantes con metadata |

### 6.3 Reposiciones

| Aspecto | Estado actual | Estado objetivo | Gap | Impacto |
|---------|--------------|-----------------|-----|---------|
| Vínculo stock → gasto | ✅ source_type='stock_replenishment' | ✅ | Ninguno | — |
| Respaldo documental | ⚠️ Solo via tax_backup si se crea perfil fiscal | Debe ser automático para reposiciones pagadas | Bajo | Feature enhancement |

### 6.4 Respaldo Impositivo

| Aspecto | Estado actual | Estado objetivo | Gap | Impacto |
|---------|--------------|-----------------|-----|---------|
| NO crea gastos | ✅ Correcto | ✅ | Ninguno | — |
| Capa documental/fiscal | ✅ ExpenseFiscalProfile overlay | ✅ | Ninguno | — |
| Recibe comprobantes | ✅ FiscalDocument con metadata completa | ✅ | Ninguno | — |
| Procesa/valida comprobantes | ✅ 8 reglas + señales automáticas | ✅ | Ninguno | — |
| Estados fiscales completos | ✅ registrado/respaldado/potencialmente_deducible/a_revisar/no_respaldado | ✅ | Ninguno | — |

### 6.5 Separación conceptual obligatoria

| Separación | Estado actual | Evaluación |
|-----------|-------------|------------|
| gasto fijo ≠ período | ✅ FixedExpense ≠ FixedExpensePeriod | **CORRECTO** |
| gasto ≠ pago | ❌ Pago embebido en gasto/período | **INCORRECTO — gap principal** |
| gasto ≠ comprobante | ✅/⚠️ FiscalDocument separado en tax_backup, pero `attachment` plano en treasury | **Parcial** |
| comprobante ≠ validación fiscal | ✅ FiscalDocument ≠ TaxStatus ≠ TaxStatusLog | **CORRECTO** |

---

## 7. Riesgos técnicos y funcionales

### Riesgos de dominio

| Riesgo | Severidad | Detalle |
|--------|-----------|---------|
| Introducir entidad Payment sin romper flujos existentes | ALTO | Los flujos de pay() en ExpenseViewSet y FixedExpensePeriodViewSet están hardcodeados para campos embebidos. Hay que migrar sin perder los pagos históricos. |
| Ambigüedad de "monto" en FixedExpensePeriod | MEDIO | `amount` puede ser monto esperado O monto pagado (después de override). No hay campo explícito para diferenciar. |
| Orphaned fiscal profiles post-void | ALTO | Al anular un pago, el perfil fiscal queda con estado stale. No hay mecanismo de cascada. |

### Riesgos de datos

| Riesgo | Severidad | Detalle |
|--------|-----------|---------|
| Migración de pagos embebidos a entidad Payment | ALTO | Cada Expense.paid_at/paid_account/payment_transaction y cada FixedExpensePeriod con sus campos paid_* debe generar un registro Payment. Backfill necesario. |
| ExpensePaymentDetail (tax_backup) vs Payment (treasury) | MEDIO | Si se crea Payment en treasury, ExpensePaymentDetail queda redundante o debe vincularse. Datos duplicados en producción. |
| Períodos con amount=0 | BAJO | Necesitan backfill o re-evaluación lógica. |

### Riesgos de API

| Riesgo | Severidad | Detalle |
|--------|-----------|---------|
| Breaking changes en respuestas de pay() | ALTO | El frontend espera los campos paid_at, paid_account, payment_transaction en la respuesta del serializer. Si se migra a Payment, los serializers necesitan adaptar. |
| Backward compatibility de `attachment` FileField | BAJO | Si se migra a entidad Document, el campo viejo queda deprecated. |

### Riesgos de UX

| Riesgo | Severidad | Detalle |
|--------|-----------|---------|
| El usuario necesita entender 4 tabs para gastos | MEDIO | La estructura actual (fijos/puntuales/reposiciones/respaldo) puede confundir. Requiere onboarding claro. |
| No hay vista unificada de "todos los gastos del mes" | MEDIO | El dashboard summary existe pero es solo para el resumen, no para gestión operativa. |
| El flujo de adjuntar comprobante obliga a ir a "Respaldo Impositivo" | MEDIO | Un usuario que quiere adjuntar una factura a un gasto debe navegar al tab de Respaldo, no hay acceso directo desde el detalle del gasto. |

### Riesgos de rollout

| Riesgo | Severidad | Detalle |
|--------|-----------|---------|
| Migración de datos sin downtime | ALTO | La creación de Payment y el backfill requieren script de migración + posible feature flag. |
| Coordinación frontend/backend | MEDIO | El frontend consume directamente los campos embebidos. La migración a Payment necesita adapter pattern o versionado. |

---

## 8. Recomendaciones de remediación

**Priorizadas por orden correcto de implementación:**

### 8.1 Pre-requisitos (antes de tocar nada)

1. **Eliminar `ExpenseTemplate`** — Drop modelo, ViewSet, serializer, URL, migración. Es dead code puro.
2. **Eliminar `RecurringServiceProfile` y `ServicePeriodAlert`** — Legacy DB tables sin uso funcional.
3. **Fixear CSV export** — Reemplazar concatenación manual por `csv.writer` con proper escaping.

### 8.2 Sprint 1: Fundaciones de modelo

4. **Crear entidad `Payment`** en treasury. Campos: business, amount, paid_at, account, transaction, payment_method, reference, notes, status (completed/voided). Relation polimórfica: payable_type (expense/fixed_expense_period/payroll) + payable_id.
5. **Backfill de datos**: migración Django que lea todo `Expense` con status=paid y todo `FixedExpensePeriod` con status=paid, y cree Payment para cada uno.
6. **Adaptar ViewSets pay()**: los endpoints pay() deben crear Payment en vez de embeber campos. Mantener backward compatibility vía serializer (campos computados que leen de Payment).
7. **Propagar anulación a tax_backup**: cuando se anula una transacción vinculada a un gasto, invalidar o marcar para revisión el perfil fiscal asociado.

### 8.3 Sprint 2: Cleanup y automatismos

8. **Agregar celery task**: `ensure_all_current_periods` automático mensual (primer día de cada mes).
9. **Agregar celery task**: alertas de vencimiento (diaria, notifica gastos que vencen hoy/mañana).
10. **Crear entidad `Provider`**: business, name, tax_id, contact_info, is_active. Vincular opcionalmente a FixedExpense, Expense, y FiscalDocument.
11. **Unificar modelo documental**: evaluar si `attachment` en Expense/Transaction se migra a FiscalDocument o a un nuevo `ExpenseAttachment`.

### 8.4 Sprint 3: Frontend

12. **Exponer categoría y frequency en form de gasto fijo.**
13. **Agregar notas y adjunto en form de gasto puntual.**
14. **Permitir override de monto en pago de gasto puntual.**
15. **Acceso directo a "adjuntar comprobante" desde detalle de gasto** (sin obligar a navegar a Respaldo Impositivo).
16. **Vista unificada de gastos del mes** (cross-tab).

### 8.5 Sprint 4: Pipeline documental

17. **Integrar procesamiento de documentos** (QR/OCR) usando el `parse_status` ya modelado en FiscalDocument.
18. **Auto-provisionar perfiles fiscales para reposiciones.**
19. **Reconciliar ExpensePaymentDetail (tax_backup) con Payment (treasury)** — o eliminar ExpensePaymentDetail y reemplazar por vínculo a Payment.

---

## 9. Propuesta de alcance exacto para Sprint 1

### SÍ entra en Sprint 1

| Item | Justificación |
|------|---------------|
| Eliminar ExpenseTemplate (modelo + ViewSet + serializer + URL) | Dead code blocking, evita confusión |
| Crear modelo Payment | Fundación obligatoria para todo lo demás |
| Migración backfill de pagos existentes a Payment | Datos consistentes antes de cambiar lógica |
| Adaptar ExpenseViewSet.pay() y FixedExpensePeriodViewSet.pay() para crear Payment | Endpoint cambia behavior pero mantiene contrato API |
| Adaptar void en TransactionViewSet para propagar a fiscal profile | Cierra el bug C3 |
| Fix CSV export injection | Seguridad — urgente |
| Tests de migración + tests de regresión para pay/void | Garantía de no romper nada |

### NO entra en Sprint 1

| Item | Razón |
|------|-------|
| Modelo Provider | Útil pero no crítico para fundación |
| Celery tasks de automatismos | Se pueden agregar post-fundación sin migración |
| Cambios de frontend | Dependen de que el modelo backend esté estable |
| Pipeline documental (OCR/QR) | Fase 4 |
| Unificación de ExpensePaymentDetail con Payment | Evaluar después de que Payment exista |
| Eliminar RecurringServiceProfile/ServicePeriodAlert | Pueden vivir vacíos sin daño |

---

## 10. Decisiones de arquitectura a congelar antes de tocar código

| # | Decisión | Opciones | Recomendación | Impacto si no se decide |
|---|----------|----------|---------------|------------------------|
| D1 | **¿Payment es polimórfico o hay PaymentExpense + PaymentFixedPeriod?** | A) Polimórfico (payable_type + payable_id) B) GenericForeignKey Django C) Tres FKs nullable con constraint | **Opción A o C.** GenericForeignKey (B) rompe queries. Polimorfismo loose (A) es consistente con Transaction.reference_type. Tres FKs (C) es lo que ya usa ExpenseFiscalProfile y funciona bien. | Retrabajo de modelo si se cambia después |
| D2 | **¿Payment soporta parcialidades desde día 1?** | A) Sí, múltiples Payment por gasto B) No, solo 1 Payment (migrar después) | **Opción A.** El costo de modelarlo bien desde el inicio es marginal. Una FK en Payment hacia el gasto permite N pagos. | Si se modela 1:1 y después se necesita 1:N, hay otra migración |
| D3 | **¿Qué pasa con ExpensePaymentDetail (tax_backup)?** | A) Eliminar y reemplazar por FK a Payment B) Mantener como registro fiscal paralelo C) Vincular a Payment vía FK | **Opción C para Sprint 1, evaluar A para Sprint 4.** No romper tax_backup que ya está probado. | Duplicación de datos indefinida si no se decide |
| D4 | **¿Los campos embebidos (paid_at, paid_account, etc.) se eliminan o se mantienen como computed?** | A) Eliminar en migración B) Mantener como @property que lee de Payment C) Mantener deprecated + nuevo campo | **Opción B para backward compat.** Eliminar en Sprint 3 cuando el frontend se adapte completamente. | Breaking changes en API si se elimina sin transición |
| D5 | **¿Qué estados tiene Payment?** | A) completed/voided B) pending/completed/voided/partial C) created/authorized/completed/voided | **Opción B.** `pending` para pagos futuros programados, `partial` para pagos parciales, `completed` y `voided` para finales. | Retrabajo de states si se agrega pending después |
| D6 | **¿El attachment de Expense/Transaction se migra a una entidad documental en treasury o se deja como está?** | A) Crear ExpenseAttachment en treasury B) Reutilizar FiscalDocument de tax_backup C) Dejar como está | **Opción C para Sprint 1, evaluar A vs B para Sprint 3.** No bloquea nada inmediato. | Solo deuda técnica menor |
| D7 | **¿Qué pasa con las frecuencias no-monthly en FixedExpense?** | A) Eliminar y dejar solo monthly B) Implementar real support con cálculo de períodos C) Mantener el campo pero documentar que solo monthly funciona | **Opción C para Sprint 1.** Documentar la limitación. Implementar en Sprint futuro si hay demanda real. | Los usuarios podrían setear quarterly/yearly sin que funcione correctamente |
| D8 | **¿Payment vive en treasury o es un nuevo app?** | A) En treasury (junto al resto) B) Nuevo app `payments` | **Opción A.** Payment es parte del dominio de tesorería. No justifica un app separado aún. | Over-engineering si se separa prematuramente |
| D9 | **¿Se usa feature flag para la transición a Payment?** | A) Sí, rollout gradual B) No, hard cutover con migración | **Opción B.** El modelo Payment se crea, se backfilla, y los endpoints se adaptan en una sola release. La backward compat via @property es suficiente. Feature flag agrega complejidad innecesaria aquí. | Complejidad de mantenimiento de dos paths |
| D10 | **¿Se expone PATCH/DELETE en Expense ya pagado?** | A) Sí (con validaciones) B) No — immutable después de pago | **Opción B.** Un gasto pagado no debe editarse. Solo se puede anular vía Transaction.void(). | Datos inconsistentes si se permite editar gastos ya con perfil fiscal |
