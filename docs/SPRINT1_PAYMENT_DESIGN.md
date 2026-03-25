# Sprint 1 — Diseño Técnico de Remediación: Entidad Payment

**Proyecto:** Mi Rubro Digital
**Fecha:** 2026-03-25
**Autor:** Staff Engineer / Software Architect
**Base:** Auditoría `GASTOS_MODULE_AUDIT.md` (2026-03-25)
**Estado:** DISEÑO — NO implementar hasta aprobación

---

## 1. Resumen técnico de la solución propuesta

### Objetivo

Extraer el concepto de "pago" de los campos embebidos en `Expense` y `FixedExpensePeriod` hacia una entidad `Payment` de primera clase en treasury, habilitando:

- Múltiples pagos por gasto (parciales)
- Historial de pagos desacoplado
- Coordinación con tax_backup vía referencia directa
- Anulación de pagos con cascada limpia a perfil fiscal

### Alcance de Sprint 1

| Incluido | Excluido |
|----------|----------|
| Eliminar `ExpenseTemplate` | Modelo Provider/Supplier |
| Crear modelo `Payment` | Celery tasks de automatismos |
| Backfill pagos históricos → Payment | Cambios de UX/frontend (solo API compat) |
| Adaptar `Expense.pay()` | Pipeline documental OCR/QR |
| Adaptar `FixedExpensePeriod.pay()` | Unificación ExpensePaymentDetail ↔ Payment |
| Adaptar `Transaction.void()` con cascada fiscal | Frecuencias non-monthly en FixedExpense |
| Coordinación con `ExpenseFiscalProfile` | Modelo ExpenseAttachment con metadata |
| Fix CSV export injection (hallazgo A1) | Soft-delete en Expense/FixedExpense |
| Tests de migración + regresión | |
| Backward compat de API para frontend actual | |

### Cambio conceptual central

```
ANTES:
  Expense → [paid_at, paid_account, payment_transaction]  (embebido, 1:1)
  FixedExpensePeriod → [paid_at, paid_account, payment_transaction]  (embebido, 1:1)

DESPUÉS:
  Expense ← Payment(s) → Transaction
  FixedExpensePeriod ← Payment(s) → Transaction
  
  Expense.status = f(SUM(payments))
  FixedExpensePeriod.status = f(SUM(payments))
```

---

## 2. Decisiones de arquitectura congeladas

### D1. Relación Payment ↔ origen: DECISIÓN CRÍTICA

#### Alternativas analizadas

**Opción A: `payable_type` + `payable_id` (polimorfismo loose)**

```python
class Payment(models.Model):
    payable_type = models.CharField(max_length=50)  # 'expense', 'fixed_expense_period'
    payable_id = models.PositiveIntegerField()
```

| Criterio | Evaluación |
|----------|-----------|
| Integridad referencial | ❌ NINGUNA. `payable_id=999` puede apuntar a nada. El DB no puede enforcearlo. |
| Facilidad de query | ⚠️ Media. Requiere filtrar por type + id. No se puede hacer `select_related`. No se puede hacer JOIN directo sin saber el type. |
| Mantenibilidad | ✅ Buena. Agregar nuevo payable type es solo un string nuevo. |
| Compatibilidad con el repo | ✅ Transaction ya usa `reference_type`/`reference_id` con este pattern. |
| Impacto en reporting | ⚠️ Queries de reporte requieren CASE WHEN o UNION. |
| Facilidad de migración | ✅ Simple. Un CharField + IntegerField. |
| Costo futuro | ⚠️ Medio. La falta de integridad referencial acumula riesgo de datos huérfanos/inconsistentes. |

**Opción B: `GenericForeignKey` (Django ContentType)**

```python
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Payment(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    payable = GenericForeignKey('content_type', 'object_id')
```

| Criterio | Evaluación |
|----------|-----------|
| Integridad referencial | ❌ NINGUNA. GFK no crea FK real en DB. Mismos problemas que Opción A. |
| Facilidad de query | ❌ Mala. No soporta `select_related`, `prefetch_related` limitado, no se puede filtrar por campos del related object sin subquery. |
| Mantenibilidad | ⚠️ Agrega dependencia a ContentType framework. Requiere que las apps estén registradas. |
| Compatibilidad con el repo | ❌ **El repo no usa GenericForeignKey en ningún lugar.** Introducirlo sería una convención nueva. |
| Impacto en reporting | ❌ Peor que A. Requiere resolver ContentType → model → tabla para cada query. |
| Facilidad de migración | ⚠️ Media. Hay que mapear modelos a ContentType IDs durante backfill. |
| Costo futuro | ❌ Alto. GFK es notoriamente difícil de mantener en Django cuando crece la complejidad. Documentación oficial de Django lo desaconseja para uso intensivo. |

**Opción C: Múltiples FKs nullable con CheckConstraint**

```python
class Payment(models.Model):
    expense = models.ForeignKey(Expense, null=True, blank=True, on_delete=models.CASCADE)
    fixed_expense_period = models.ForeignKey(FixedExpensePeriod, null=True, blank=True, on_delete=models.CASCADE)
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(Q(expense__isnull=False, fixed_expense_period__isnull=True)
                     | Q(expense__isnull=True, fixed_expense_period__isnull=False)),
                name='payment_exactly_one_source',
            ),
        ]
```

| Criterio | Evaluación |
|----------|-----------|
| Integridad referencial | ✅ **COMPLETA.** FK real en DB. CASCADE funciona. El DB garantiza que `expense_id` apunta a un Expense real. |
| Facilidad de query | ✅ **Excelente.** `select_related('expense', 'fixed_expense_period')` funciona directo. JOINs nativos. Filtros como `Payment.objects.filter(expense__business=biz)` son triviales. |
| Mantenibilidad | ✅ Buena. Cada FK es explícita, documentada, tipada. El ORM genera helpers automáticos (`expense.payments.all()`). |
| Compatibilidad con el repo | ✅ **Exactamente el pattern que ya usa `ExpenseFiscalProfile`** (dual-origin con CheckConstraint). Probado y funcional en este codebase. |
| Impacto en reporting | ✅ Queries directas con JOINs reales. Sin CASE WHEN ni UNION. |
| Facilidad de migración | ✅ Simple. FKs nullable + CheckConstraint en una migración. |
| Costo futuro | ⚠️ **Bajo.** Agregar un nuevo payable type requiere una migración (nueva columna FK nullable + actualizar CheckConstraint). Esto es aceptable porque los payable types son pocos y conocidos (expense, fixed_expense_period, eventualmente payroll). |

**Opción D: Tabla de unión abstracta (PaymentExpense + PaymentFixedPeriod heredan de PaymentBase)**

```python
class PaymentBase(models.Model):
    amount = ...
    class Meta:
        abstract = True

class ExpensePayment(PaymentBase):
    expense = models.ForeignKey(Expense, ...)

class FixedExpensePeriodPayment(PaymentBase):
    fixed_expense_period = models.ForeignKey(FixedExpensePeriod, ...)
```

| Criterio | Evaluación |
|----------|-----------|
| Integridad referencial | ✅ FK real por tipo. |
| Facilidad de query | ❌ **Mala.** No se pueden consultar "todos los pagos" sin UNION de dos tablas. Imposible para dashboard/reportes unificados. |
| Mantenibilidad | ❌ Duplicación de lógica entre dos modelos casi idénticos. |
| Compatibilidad con el repo | ❌ No hay precedente de multi-table inheritance en el repo. |
| Impacto en reporting | ❌ Cada reporte necesita unir N tablas. |
| Facilidad de migración | ⚠️ Dos migraciones, dos backfills. |
| Costo futuro | ❌ Alto. N payable types = N tablas = N×mantenimiento. |

#### RECOMENDACIÓN FINAL: OPCIÓN C — Múltiples FKs nullable con CheckConstraint

**Razones definitivas:**

1. **Consistencia probada en el codebase.** `ExpenseFiscalProfile` ya usa exactamente este pattern con `expense` + `fixed_expense_period` + CheckConstraint `tb_fp_exactly_one_source`. Está probado en producción con 36 tests de tax_backup.

2. **Integridad referencial real.** Es la ÚNICA opción que da garantía a nivel de base de datos. Las opciones A y B dependen de la aplicación para mantener consistencia — ese es un camino a datos huérfanos.

3. **Queries nativas del ORM.** `Payment.objects.filter(expense__business=biz).select_related('expense', 'transaction')` es un single JOIN. No hay magia.

4. **Costo marginal de extensión.** Si en el futuro se agrega `payroll` como payable, es una migración: `ALTER TABLE ADD COLUMN payroll_payment_id REFERENCES...` + actualizar CheckConstraint. Con 3-4 payable types, esto es mantenible.

5. **Reporting sin fricción.** Los dashboards y exports pueden hacer `Payment.objects.filter(business=biz).annotate(source=Coalesce(...))` directamente.

**Decisión: CONGELADA. Usar Opción C.**

---

### D2. ¿Payment soporta pagos parciales desde Sprint 1?

**Decisión: SÍ.**

El costo de modelar 1:N desde el inicio (muchos Payment por cada Expense/FixedExpensePeriod) es CERO comparado con el costo de rehacer la migración después. La FK `expense` en Payment sin UniqueConstraint ya permite N pagos.

El frontend en Sprint 1 seguirá mostrando un solo pago (el flujo actual), pero el modelo lo soporta nativamente.

**Decisión: CONGELADA.**

---

### D3. ¿Qué pasa con `ExpensePaymentDetail` (tax_backup)?

**Decisión: En Sprint 1 coexisten. No se modifica tax_backup.**

- `ExpensePaymentDetail` registra el "cómo se pagó" desde perspectiva fiscal (medio de pago, comprobante de pago, referencia bancaria).
- `Payment` registra el "pago real" desde perspectiva de tesorería (cuenta, transacción, monto).
- Son complementarios, no redundantes, por ahora.

En Sprint 4 se evaluará vincular `ExpensePaymentDetail.payment` → `Payment` FK para deduplicar.

**Decisión: CONGELADA para Sprint 1. Diferible para Sprint 4.**

---

### D4. Campos legacy embebidos — ¿eliminar o mantener como computed?

**Decisión: Mantener como `@property` que leen del Payment más reciente.**

Los campos `paid_at`, `paid_account`, `payment_transaction` en Expense y FixedExpensePeriod:
- Se eliminan como columnas de DB en la migración
- Se exponen como `@property` computados que leen del `payments.first()` (ordenados por `-created_at`)
- Los serializers siguen exponiendo estos campos sin cambio en el contrato API
- El frontend no necesita cambios en Sprint 1

Los campos computados se eliminarán cuando el frontend migre a leer `payments[]`.

**Decisión: CONGELADA.**

---

### D5. Estados de Payment

**Decisión: Dos estados finales.**

```python
class Status(models.TextChoices):
    COMPLETED = 'completed', 'Completado'
    VOIDED = 'voided', 'Anulado'
```

**NO incluir PENDING ni PARTIAL en Payment.**

Cada `Payment` representa un pago EJECUTADO (dinero que se movió). No hay pagos "programados" ni "parciales" como estado de Payment. La noción de "parcialidad" es derivada en el Expense:

```
Expense.payment_status = f(SUM(completed_payments.amount) vs expense.amount)
  → UNPAID: sum == 0
  → PARTIALLY_PAID: 0 < sum < amount
  → FULLY_PAID: sum >= amount
```

Si en el futuro se necesitan pagos programados, se agrega `SCHEDULED` al enum. Pero Sprint 1 no lo requiere.

**Decisión: CONGELADA.**

---

### D6. ¿Payment vive en treasury o en nuevo app?

**Decisión: En treasury.** Payment es una entidad de tesorería. No justifica un app separado.

**Decisión: CONGELADA.**

---

### D7. ¿Feature flag para transición?

**Decisión: NO. Hard cutover con migración + backward compat vía @property.**

La complejidad de mantener dos code paths (con/sin Payment) durante la transición no se justifica. La backward compat se logra con propiedades computadas, no con feature flags.

**Decisión: CONGELADA.**

---

### D8. Immutabilidad post-pago

**Decisión: Expense/FixedExpensePeriod pagados son immutables.** Solo se pueden revertir via `Transaction.void()`.

**Decisión: CONGELADA.**

---

## 3. Modelo objetivo de Payment

### Propósito

`Payment` representa un pago concreto ejecutado contra un gasto (puntual o de período fijo). Es una entidad de primer nivel en treasury que vincula:
- El origen del gasto (Expense o FixedExpensePeriod)
- La transacción financiera (Transaction)
- La cuenta de origen (Account)
- Metadata del pago (monto, fecha, notas)

### Definición del modelo

```python
class Payment(models.Model):
    """
    Pago concreto ejecutado contra un gasto.
    Soporta múltiples pagos por gasto (parciales).
    
    Exactamente UNO de (expense, fixed_expense_period) debe ser no-null.
    Pattern idéntico a ExpenseFiscalProfile.
    """
    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completado'
        VOIDED = 'voided', 'Anulado'

    # ── Multi-tenant ───────────────────────────────────────────────────
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE,
        related_name='payments',
    )

    # ── Origen (mutuamente excluyente) ─────────────────────────────────
    expense = models.ForeignKey(
        'Expense', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='payments',
    )
    fixed_expense_period = models.ForeignKey(
        'FixedExpensePeriod', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='payments',
    )

    # ── Datos del pago ─────────────────────────────────────────────────
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    paid_at = models.DateTimeField()
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        related_name='payment_records',
    )
    transaction = models.OneToOneField(
        Transaction, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='payment',
        help_text='Transacción financiera asociada (puede ser null si se anuló)',
    )

    # ── Estado ─────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
    )

    # ── Metadata ───────────────────────────────────────────────────────
    notes = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-paid_at']
        indexes = [
            models.Index(
                fields=['business', 'status', '-paid_at'],
                name='treasury_pay_biz_status_idx',
            ),
            models.Index(
                fields=['expense', 'status'],
                name='treasury_pay_expense_idx',
                condition=models.Q(expense__isnull=False),
            ),
            models.Index(
                fields=['fixed_expense_period', 'status'],
                name='treasury_pay_fep_idx',
                condition=models.Q(fixed_expense_period__isnull=False),
            ),
        ]
        constraints = [
            # Exactamente un origen
            models.CheckConstraint(
                check=(
                    models.Q(expense__isnull=False, fixed_expense_period__isnull=True)
                    | models.Q(expense__isnull=True, fixed_expense_period__isnull=False)
                ),
                name='payment_exactly_one_source',
            ),
            # Amount siempre positivo
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='payment_amount_positive',
            ),
        ]

    def __str__(self):
        target = f'expense={self.expense_id}' if self.expense_id else f'fep={self.fixed_expense_period_id}'
        return f'Payment({target}) ${self.amount} [{self.status}]'

    @property
    def source_object(self):
        """Retorna el Expense o FixedExpensePeriod asociado."""
        return self.expense or self.fixed_expense_period

    @property
    def source_type(self) -> str:
        if self.expense_id:
            return 'expense'
        return 'fixed_expense_period'
```

### Relaciones

```
Payment.expense          → Expense (FK nullable, CASCADE)
Payment.fixed_expense_period → FixedExpensePeriod (FK nullable, CASCADE)
Payment.account          → Account (FK, PROTECT)
Payment.transaction      → Transaction (OneToOne nullable, SET_NULL)
Payment.business         → Business (FK, CASCADE)
Payment.created_by       → User (FK nullable, SET_NULL)

Expense.payments         ← Payment (reverse, 0..N)
FixedExpensePeriod.payments ← Payment (reverse, 0..N)
```

### Invariantes

1. **Exactamente un origen**: `expense XOR fixed_expense_period` (CheckConstraint en DB)
2. **Amount > 0**: (CheckConstraint en DB)
3. **Status is final**: Un Payment COMPLETED se vuelve VOIDED solo via void(). No vuelve a COMPLETED.
4. **Transaction es 1:1**: Cada Payment tiene a lo sumo una Transaction. Una Transaction tiene a lo sumo un Payment. (OneToOneField)
5. **Business consistency**: `payment.business == payment.expense.business` (validado en código, no en DB para evitar cross-FK constraint)

---

## 4. Impacto sobre entidades actuales

### 4.1 Expense

**Cambios en modelo:**

| Campo | Acción | Detalle |
|-------|--------|---------|
| `paid_at` | **ELIMINAR columna DB → convertir a @property** | Lee de `self.payments.filter(status='completed').order_by('-paid_at').first().paid_at` |
| `paid_account` | **ELIMINAR columna DB → convertir a @property** | Lee de `self.payments.filter(status='completed').order_by('-paid_at').first().account` |
| `payment_transaction` | **ELIMINAR columna DB → convertir a @property** | Lee de `self.payments.filter(status='completed').order_by('-paid_at').first().transaction` |
| `template` | **ELIMINAR columna DB** | FK a ExpenseTemplate deprecado |
| `status` | **CAMBIAR semántica** | Ya no se setea manualmente a PAID. Se DERIVA de pagos. Ver abajo. |

**Propiedades computadas nuevas:**

```python
class Expense(models.Model):
    # ... campos existentes sin paid_at, paid_account, payment_transaction, template ...

    @property
    def paid_at(self):
        """Backward compat: fecha del pago más reciente completado."""
        p = self.payments.filter(status=Payment.Status.COMPLETED).order_by('-paid_at').first()
        return p.paid_at if p else None

    @property
    def paid_account(self):
        """Backward compat: cuenta del pago más reciente completado."""
        p = self.payments.filter(status=Payment.Status.COMPLETED).order_by('-paid_at').first()
        return p.account if p else None

    @property
    def payment_transaction(self):
        """Backward compat: transacción del pago más reciente completado."""
        p = self.payments.filter(status=Payment.Status.COMPLETED).order_by('-paid_at').first()
        return p.transaction if p else None

    @property
    def total_paid(self):
        """Suma de pagos completados."""
        from django.db.models import Sum
        return self.payments.filter(
            status=Payment.Status.COMPLETED
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    def refresh_status(self):
        """Recalcula status basado en pagos. Llamar dentro de atomic."""
        if self.is_auto_generated:
            return  # Auto-generated expenses no cambian status via Payment
        total = self.total_paid
        if total <= 0:
            self.status = self.Status.PENDING
        elif total < self.amount:
            # Sprint 1: partial payments modelados pero UI aún no los usa
            self.status = self.Status.PAID  # Simplificación Sprint 1
        else:
            self.status = self.Status.PAID
        self.save(update_fields=['status'])
```

> **Nota Sprint 1:** `refresh_status()` trata pago parcial como PAID por simplicidad. La UI no soporta parciales aún. En Sprint 2 se puede agregar `PARTIALLY_PAID` al enum Status si la UI lo necesita.

**Status derivación — regla:**

```
PENDING   → SUM(completed payments) == 0  AND  not cancelled
PAID      → SUM(completed payments) > 0
CANCELLED → seteado manualmente (no cambia con pagos)
```

### 4.2 FixedExpensePeriod

**Cambios en modelo (idénticos al pattern de Expense):**

| Campo | Acción |
|-------|--------|
| `paid_at` | ELIMINAR columna DB → @property |
| `paid_account` | ELIMINAR columna DB → @property |
| `payment_transaction` | ELIMINAR columna DB → @property |
| `status` | Derivado de pagos (pending/paid/skipped) |

```python
class FixedExpensePeriod(models.Model):
    # ... campos existentes sin paid_at, paid_account, payment_transaction ...

    @property
    def paid_at(self):
        p = self.payments.filter(status=Payment.Status.COMPLETED).order_by('-paid_at').first()
        return p.paid_at if p else None

    @property
    def paid_account(self):
        p = self.payments.filter(status=Payment.Status.COMPLETED).order_by('-paid_at').first()
        return p.account if p else None

    @property
    def payment_transaction(self):
        p = self.payments.filter(status=Payment.Status.COMPLETED).order_by('-paid_at').first()
        return p.transaction if p else None

    def refresh_status(self):
        """Recalcula status basado en pagos. No toca SKIPPED."""
        if self.status == self.Status.SKIPPED:
            return
        total = self.payments.filter(
            status=Payment.Status.COMPLETED
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        if total <= 0:
            self.status = self.Status.PENDING
        else:
            self.status = self.Status.PAID
        self.save(update_fields=['status'])
```

### 4.3 Transaction

**Cambios mínimos:**

- `void()` action ahora debe también void-ear el Payment asociado (si existe)
- El campo `reference_type`/`reference_id` sigue existiendo (no cambia). Payment se vincula via su propio FK, no via reference_type.
- Nuevo reverse relation: `transaction.payment` (OneToOne desde Payment)

**void() flow actualizado:**

```
1. txn.status = VOIDED
2. Si txn.payment existe:
   a. payment.status = VOIDED
   b. payment.source_object.refresh_status()  → recalcular status del gasto
3. Si txn tiene reference_type='expense' o 'fixed_expense_period':
   → ya NO se tocan campos embebidos (no existen más)
   → el refresh_status() en paso 2b ya lo cubre
4. NUEVO: Propagar a fiscal profile
   a. Buscar ExpenseFiscalProfile del gasto/período
   b. Si existe → re-evaluar tax_status (o marcar a_revisar)
```

### 4.4 ExpenseFiscalProfile

**Cambios en Sprint 1:**

- **Nuevo comportamiento:** Cuando se anula una transacción vinculada a un gasto pagado, el perfil fiscal se re-evalúa automáticamente.
- **No hay cambios de schema** en ExpenseFiscalProfile.
- Se agrega al void() flow:

```python
# En void() después de revertir el Payment:
from apps.tax_backup.models import ExpenseFiscalProfile
from apps.tax_backup.rules import evaluate_tax_status
from apps.tax_backup.models import TaxStatusLog

profile = None
if payment.expense_id:
    profile = ExpenseFiscalProfile.objects.filter(expense=payment.expense).first()
elif payment.fixed_expense_period_id:
    profile = ExpenseFiscalProfile.objects.filter(
        fixed_expense_period=payment.fixed_expense_period
    ).first()

if profile:
    old_status = profile.tax_status
    profile.tax_status = TaxStatus.NEEDS_REVIEW
    profile.review_reason = f'Pago anulado (transaction #{txn.id}). Requiere revisión.'
    profile.save(update_fields=['tax_status', 'review_reason', 'updated_at'])
    TaxStatusLog.objects.create(
        fiscal_profile=profile,
        previous_status=old_status,
        new_status=TaxStatus.NEEDS_REVIEW,
        rule_code='VOID_PAYMENT_CASCADE',
        note=f'Transacción #{txn.id} anulada → perfil marcado para revisión.',
    )
```

### 4.5 ExpensePaymentDetail (tax_backup)

**Sprint 1: SIN CAMBIOS.**

`ExpensePaymentDetail` sigue funcionando como hoy. Es un registro fiscal del medio de pago, no del pago en sí. La unificación con `Payment` se evalúa en Sprint 4.

### 4.6 ExpenseTemplate

**ELIMINACIÓN COMPLETA en Sprint 1.**

Archivos afectados:
- `treasury/models.py` → eliminar clase `ExpenseTemplate`
- `treasury/views.py` → eliminar `ExpenseTemplateViewSet`
- `treasury/serializers.py` → eliminar `ExpenseTemplateSerializer`
- `treasury/urls.py` → eliminar ruta `expense-templates/`
- `Expense.template` FK → eliminar campo
- `ExpenseSerializer.template_name` → eliminar campo computado
- Migración: DROP table + DROP FK column

---

## 5. Estrategia de migración y backfill

### 5.1 Migraciones de schema (en orden)

#### Migración 0006: Eliminar ExpenseTemplate

```
Operations:
  1. RemoveField(model_name='expense', name='template')
  2. DeleteModel(name='ExpenseTemplate')
```

**Riesgo:** Bajo. No hay datos significativos en ExpenseTemplate (modelo deprecado, sin uso frontend).

**Pre-check:** `SELECT COUNT(*) FROM treasury_expensetemplate;` — si hay filas, documentarlas pero proceder.

#### Migración 0007: Crear Payment + campos temporales

```
Operations:
  1. CreateModel(name='Payment', fields=[...], constraints=[...])
  2. -- NO eliminar campos legacy todavía (paid_at, paid_account, payment_transaction en Expense/FixedExpensePeriod)
```

**Nota:** Los campos legacy se mantienen en DB durante esta migración para que el backfill pueda leerlos.

#### Migración 0008: Backfill de datos (RunPython)

```python
def backfill_payments(apps, schema_editor):
    Payment = apps.get_model('treasury', 'Payment')
    Expense = apps.get_model('treasury', 'Expense')
    FixedExpensePeriod = apps.get_model('treasury', 'FixedExpensePeriod')
    
    # 1. Backfill desde Expense
    paid_expenses = Expense.objects.filter(
        status='paid',
        payment_transaction__isnull=False,
    ).select_related('payment_transaction', 'paid_account')
    
    payments_to_create = []
    for exp in paid_expenses:
        payments_to_create.append(Payment(
            business_id=exp.business_id,
            expense_id=exp.id,
            fixed_expense_period=None,
            amount=exp.amount,
            paid_at=exp.paid_at or exp.payment_transaction.occurred_at,
            account_id=exp.paid_account_id or exp.payment_transaction.account_id,
            transaction_id=exp.payment_transaction_id,
            status='completed',
            created_by_id=exp.payment_transaction.created_by_id,
        ))
    
    # 2. Backfill desde FixedExpensePeriod
    paid_periods = FixedExpensePeriod.objects.filter(
        status='paid',
        payment_transaction__isnull=False,
    ).select_related('payment_transaction', 'paid_account', 'fixed_expense')
    
    for period in paid_periods:
        payments_to_create.append(Payment(
            business_id=period.fixed_expense.business_id,
            expense=None,
            fixed_expense_period_id=period.id,
            amount=period.amount,
            paid_at=period.paid_at or period.payment_transaction.occurred_at,
            account_id=period.paid_account_id or period.payment_transaction.account_id,
            transaction_id=period.payment_transaction_id,
            status='completed',
            created_by_id=period.payment_transaction.created_by_id,
        ))
    
    Payment.objects.bulk_create(payments_to_create, batch_size=500)
    
    # 3. Gastos pagados SIN transacción (datos inconsistentes)
    orphan_expenses = Expense.objects.filter(
        status='paid',
        payment_transaction__isnull=True,
    )
    for exp in orphan_expenses:
        if exp.paid_at and exp.paid_account_id:
            Payment.objects.create(
                business_id=exp.business_id,
                expense_id=exp.id,
                amount=exp.amount,
                paid_at=exp.paid_at,
                account_id=exp.paid_account_id,
                transaction=None,
                status='completed',
            )
        # Si ni siquiera tiene paid_at/paid_account, el gasto tiene status=paid
        # pero sin datos de pago. Se crea Payment con datos mínimos.
        elif exp.paid_at:
            # Tiene fecha pero no cuenta — inconsistencia. Log y skip.
            pass  # Se documenta en validación post-migración
    
    # Mismo tratamiento para FixedExpensePeriod sin transacción
    orphan_periods = FixedExpensePeriod.objects.filter(
        status='paid',
        payment_transaction__isnull=True,
    )
    for period in orphan_periods:
        if period.paid_at and period.paid_account_id:
            Payment.objects.create(
                business_id=period.fixed_expense.business_id,
                fixed_expense_period_id=period.id,
                amount=period.amount,
                paid_at=period.paid_at,
                account_id=period.paid_account_id,
                transaction=None,
                status='completed',
            )


def reverse_backfill(apps, schema_editor):
    """Rollback: simplemente eliminar todos los Payment. Los campos legacy aún existen."""
    Payment = apps.get_model('treasury', 'Payment')
    Payment.objects.all().delete()
```

#### Migración 0009: Eliminar campos legacy

```
Operations:
  1. RemoveField(model_name='expense', name='paid_at')
  2. RemoveField(model_name='expense', name='paid_account')
  3. RemoveField(model_name='expense', name='payment_transaction')
  4. RemoveField(model_name='fixedexpenseperiod', name='paid_at')
  5. RemoveField(model_name='fixedexpenseperiod', name='paid_account')
  6. RemoveField(model_name='fixedexpenseperiod', name='payment_transaction')
```

**IMPORTANTE:** Esta migración se ejecuta DESPUÉS del backfill y DESPUÉS de validar que los @property funcionan correctamente.

### 5.2 Detección de inconsistencias históricas

Script de validación post-backfill (management command):

```python
# validate_payment_backfill.py
"""
Checks ejecutados:
1. Todo Expense con status=paid tiene al menos 1 Payment completed
2. Todo FixedExpensePeriod con status=paid tiene al menos 1 Payment completed
3. Todo Payment.transaction_id es único (OneToOne)
4. Todo Payment.amount > 0
5. Conteo: Payments creados == Expenses paid + Periods paid
6. Detectar gastos paid sin Payment (errores de backfill)
7. Detectar Payment sin transaction (huérfanos aceptables documentados)
"""
```

### 5.3 Rollback / mitigación

| Escenario | Acción |
|-----------|--------|
| Backfill falla a mitad | La migración corre en transaction. Rollback automático de Django. |
| Backfill completa pero datos inconsistentes | Los campos legacy aún existen (0009 no ejecutada). Se puede revertir al código anterior. |
| 0009 ejecutada y detecto problema | Los datos ya están en Payment. Se pueden reconstruir los campos legacy con reverse migration. |
| Problema en producción post-deploy | Rollback: revertir 0009 (re-agrega columnas), revertir 0008 (borra Payments), revertir code change. Los campos legacy se re-populan desde Payment si es necesario. |

**Estrategia de safety net:** Las migraciones 0008 y 0009 se ejecutan por separado. Se valida entre ambas. Solo se ejecuta 0009 después de confirmar que el backfill es correcto y que los @property funcionan.

---

## 6. Estrategia de compatibilidad de API

### 6.1 Contrato actual del frontend (NO romper)

**Expense:**
```typescript
interface Expense {
  paid_at?: string;           // → @property → serializer
  paid_account?: number;      // → @property → serializer
  paid_account_name?: string; // → @property → serializer
  payment_transaction?: number | null;  // → @property → serializer
}
```

**FixedExpensePeriod:**
```typescript
interface FixedExpensePeriod {
  paid_at?: string;
  paid_account?: number;
  paid_account_name?: string;
  payment_transaction?: number;
}
```

### 6.2 Estrategia: campos legacy como SerializerMethodField

Los serializers se adaptan para leer de Payment en vez de los campos DB:

```python
class ExpenseSerializer(serializers.ModelSerializer):
    # Campos legacy → computados desde Payment
    paid_at = serializers.SerializerMethodField()
    paid_account = serializers.SerializerMethodField()
    paid_account_name = serializers.SerializerMethodField()
    payment_transaction = serializers.SerializerMethodField()
    
    # Campo nuevo (opcional, para frontend futuro)
    payments = PaymentSummarySerializer(many=True, read_only=True, source='payments')

    def _get_latest_payment(self, obj):
        """Helper: retorna el pago completado más reciente, usando prefetch si disponible."""
        if hasattr(obj, '_prefetched_objects_cache') and 'payments' in obj._prefetched_objects_cache:
            completed = [p for p in obj.payments.all() if p.status == 'completed']
            return completed[0] if completed else None
        return obj.payments.filter(status='completed').order_by('-paid_at').first()

    def get_paid_at(self, obj):
        p = self._get_latest_payment(obj)
        return p.paid_at.isoformat() if p else None

    def get_paid_account(self, obj):
        p = self._get_latest_payment(obj)
        return p.account_id if p else None

    def get_paid_account_name(self, obj):
        p = self._get_latest_payment(obj)
        return p.account.name if p and p.account else None

    def get_payment_transaction(self, obj):
        p = self._get_latest_payment(obj)
        return p.transaction_id if p else None
```

### 6.3 Endpoints afectados

| Endpoint | Cambio interno | Contrato API |
|----------|---------------|--------------|
| `POST /expenses/{id}/pay/` | Crea Payment + Transaction (en vez de embeber) | **SIN CAMBIO.** Respuesta sigue siendo `ExpenseSerializer` con los mismos campos. |
| `POST /fixed-expense-periods/{id}/pay/` | Crea Payment + Transaction | **SIN CAMBIO.** |
| `POST /transactions/{id}/void/` | Void-ea Payment asociado + propaga a fiscal | **SIN CAMBIO en response.** |
| `GET /expenses/` | QuerySet debe hacer `prefetch_related('payments')` | **SIN CAMBIO.** |
| `GET /fixed-expense-periods/` | QuerySet debe hacer `prefetch_related('payments')` | **SIN CAMBIO.** |
| `DELETE /expense-templates/` | **ELIMINADO.** | **BREAKING** (pero endpoint no se usa). |
| `GET /transactions/{id}/export-csv/` | Fix inyección | **Mismo formato, escapado correcto.** |

### 6.4 Nuevos campos opcionales

El serializer expone un campo nuevo `payments` (array de Payment resumen) que el frontend puede empezar a usar cuando esté listo:

```json
{
  "id": 42,
  "name": "Proveedor X",
  "amount": "15000.0000",
  "status": "paid",
  "paid_at": "2026-03-15T10:00:00Z",
  "paid_account": 3,
  "paid_account_name": "Caja",
  "payment_transaction": 187,
  "payments": [
    {
      "id": 1,
      "amount": "15000.0000",
      "paid_at": "2026-03-15T10:00:00Z",
      "account_id": 3,
      "account_name": "Caja",
      "transaction_id": 187,
      "status": "completed"
    }
  ]
}
```

### 6.5 Qué debe devolver `pay()` después del refactor

**La MISMA estructura de antes**, con los campos legacy computados desde el Payment. El frontend no necesita cambios.

---

## 7. Cambios exactos por capa

### 7.1 Modelos (`treasury/models.py`)

| Cambio | Detalle |
|--------|---------|
| **AGREGAR** clase `Payment` | ~70 líneas. Modelo completo con constraints e índices. Ubicar después de `FixedExpensePeriod`, antes de `ExpenseTemplate`. |
| **ELIMINAR** clase `ExpenseTemplate` | ~20 líneas. Eliminar completamente. |
| **MODIFICAR** clase `Expense` | Eliminar campos `paid_at`, `paid_account`, `payment_transaction`, `template`. Agregar `@property` para backward compat. Agregar `refresh_status()`. Agregar `total_paid` property. |
| **MODIFICAR** clase `FixedExpensePeriod` | Eliminar campos `paid_at`, `paid_account`, `payment_transaction`. Agregar `@property` y `refresh_status()`. |

**Archivos:** `services/api/src/apps/treasury/models.py`

**Dependencias:** Migración 0006-0009 previa.

**Riesgo:** MEDIO — cambio structural en modelos core. Mitigado por @property backward compat.

### 7.2 Servicios / Lógica de negocio

No hay archivo `services.py` en treasury actualmente. La lógica vive en los ViewSets. Sprint 1 mantiene esta estructura pero extrae la lógica a funciones helper dentro de views.py.

| Cambio | Detalle |
|--------|---------|
| **MODIFICAR** `ExpenseViewSet.pay()` | Crear Payment y Transaction dentro de atomic. Llamar `expense.refresh_status()`. Mantener llamada a `ensure_fiscal_profile_for_expense()`. |
| **MODIFICAR** `FixedExpensePeriodViewSet.pay()` | Idem. Crear Payment + Transaction. Llamar `period.refresh_status()`. |
| **MODIFICAR** `TransactionViewSet.void()` | Buscar `txn.payment`. Si existe: void-ear Payment → refresh_status del gasto → propagar a fiscal profile. |
| **ELIMINAR** `ExpenseTemplateViewSet` | Completo. |

**Archivos:** `services/api/src/apps/treasury/views.py`

**Dependencias:** Modelo Payment ya creado.

**Riesgo:** ALTO — flujos de pago y anulación son críticos. Tests son imprescindibles.

### 7.3 Views

Los cambios principales están en 7.2.

Cambio adicional:

| Cambio | Detalle |
|--------|---------|
| **MODIFICAR** `ExpenseViewSet.get_queryset()` | Agregar `.prefetch_related(Prefetch('payments', queryset=Payment.objects.filter(status='completed').select_related('account', 'transaction')))` |
| **MODIFICAR** `FixedExpensePeriodViewSet.get_queryset()` | Idem. |
| **MODIFICAR** `TransactionViewSet.export_csv()` | Reemplazar concatenación manual por `csv.writer` (fix hallazgo A1). |

**Archivos:** `services/api/src/apps/treasury/views.py`

### 7.4 Serializers (`treasury/serializers.py`)

| Cambio | Detalle |
|--------|---------|
| **AGREGAR** `PaymentSerializer` | Serializer completo para CRUD de Payment (futuro). |
| **AGREGAR** `PaymentSummarySerializer` | Serializer ligero para embedding en Expense/FixedExpensePeriod response. |
| **MODIFICAR** `ExpenseSerializer` | Campos `paid_at`, `paid_account`, `paid_account_name`, `payment_transaction` → `SerializerMethodField`. Eliminar `template_name`. Agregar `payments` nested. |
| **MODIFICAR** `FixedExpensePeriodSerializer` | Mismo pattern que ExpenseSerializer. |
| **ELIMINAR** `ExpenseTemplateSerializer` | Completo. |

**Archivos:** `services/api/src/apps/treasury/serializers.py`

**Riesgo:** MEDIO — si los SerializerMethodField no se cachean correctamente, N+1 queries. Mitigado por prefetch_related.

### 7.5 URLs (`treasury/urls.py`)

| Cambio | Detalle |
|--------|---------|
| **ELIMINAR** ruta `expense-templates/` | Router entry. |
| **AGREGAR** ruta `payments/` (opcional Sprint 1) | Para debugging/admin. Read-only en Sprint 1. |

### 7.6 Tax Backup

| Cambio | Detalle |
|--------|---------|
| **SIN CAMBIOS de modelo** | ExpenseFiscalProfile, ExpensePaymentDetail, rules.py no cambian. |
| **MODIFICAR** `services.py` | Actualizar imports si `Expense` cambia de signature (no debería ser necesario). |
| **AGREGAR** lógica en `void()` de treasury | La cascada a fiscal se implementa en treasury/views.py, no en tax_backup. Tax_backup es pasivo. |

**Archivos:** Potencialmente `services/api/src/apps/tax_backup/services.py` (solo import cleanup).

**Riesgo:** BAJO — tax_backup no se toca structuralmente.

### 7.7 Frontend impactado

**Sprint 1: CERO cambios de frontend.**

El contrato API se mantiene idéntico gracias a las `SerializerMethodField`. Los campos `paid_at`, `paid_account`, `paid_account_name`, `payment_transaction` siguen existiendo en la respuesta JSON.

El campo nuevo `payments[]` se agrega pero es aditivo — el frontend lo ignora hasta que se adapte.

**Sprint 2+ frontend changes:**
- Leer `payments[]` en vez de campos legacy
- Mostrar historial de pagos en detalle
- UI para pagos parciales

### 7.8 Tests

Ver sección 10.

---

## 8. Riesgos del diseño propuesto

### 8.1 Riesgos técnicos

| Riesgo | Severidad | Mitigación |
|--------|-----------|-----------|
| **N+1 queries en serializers** al leer Payment desde @property | ALTO | Usar `prefetch_related('payments')` en todos los querysets. Tests de query count. |
| **OneToOne Transaction↔Payment puede conflictar** si hay transacciones que no son pagos (transfers, adjusts) | BAJO | El OneToOne es desde Payment→Transaction, no inverso. Solo Payment que tiene transaction apunta. Transactions sin Payment no se ven afectadas. `related_name='payment'` permite `txn.payment` para check en void(). |
| **Race condition en pagos concurrentes** al mismo Expense | MEDIO | El `atomic()` block existe. Agregar `select_for_update()` en el queryset del gasto antes de crear Payment. |
| **Backfill de gran volumen** si hay muchos pagos históricos | BAJO | `bulk_create` con batch_size=500. Mi Rubro es B2B SaaS con volumen moderado por tenant. |
| **Migración 0009 (drop columns) es irreversible** | MEDIO | Se ejecuta solo después de validar backfill. Reverse migration re-agrega columns vacías + script de reverse-populate desde Payment. |

### 8.2 Riesgos funcionales

| Riesgo | Severidad | Mitigación |
|--------|-----------|-----------|
| **Auto-generated expenses** (stock replenishment) no deben pagarse via Payment | MEDIO | Mantener guard en `pay()`: `if expense.is_auto_generated: return 400`. El backfill crea Payment para estos igualmente (para consistencia de datos), pero el endpoint sigue bloqueado para pago manual. |
| **Skipped periods** no deben recibir pagos | BAJO | Guard en `pay()`: `if period.status == SKIPPED: return 400`. |
| **Gastos con status=paid pero sin datos de pago** en datos históricos | MEDIO | El backfill los detecta. Se crea Payment con datos parciales o se omite con log de advertencia. |

### 8.3 Riesgos de datos

| Riesgo | Severidad | Mitigación |
|--------|-----------|-----------|
| **Transaction.payment_transaction_id** en Expense/FixedExpensePeriod apunta a Transaction que también está referenciada por otro Expense/Period | BAJO | El OneToOne en Payment lo previene. El backfill lo detecta y reporta. |
| **Pagos huérfanos** (Payment sin Expense ni FixedExpensePeriod) | BAJO | CheckConstraint en DB previene creación. Backfill solo crea desde fuentes existentes. |
| **Pérdida de paid_at/paid_account en migración 0009** | ALTO | No se ejecuta 0009 hasta validar que toda la data está en Payment y que los @property retornan los mismos valores. Script de validación obligatorio. |

### 8.4 Riesgos de rollout

| Riesgo | Severidad | Mitigación |
|--------|-----------|-----------|
| **Deploy coordinated: migration + code change** | MEDIO | Las migraciones 0006-0008 son forward-compatible (no rompen el código viejo porque los campos legacy siguen). El code change se deploya después. La migración 0009 se deploya como paso final. |
| **Si falla en producción** y hay que rollback | MEDIO | Secuencia: revertir code → revertir 0009 (si fue aplicada) → los campos legacy están de nuevo → app funciona como antes. |

---

## 9. Plan exacto de implementación de Sprint 1

### Paso 1: Migración 0006 — Eliminar ExpenseTemplate

**Archivos:**
- `treasury/migrations/0006_remove_expense_template.py`
- `treasury/models.py` (eliminar clase ExpenseTemplate, eliminar FK `template` en Expense)
- `treasury/views.py` (eliminar ExpenseTemplateViewSet)
- `treasury/serializers.py` (eliminar ExpenseTemplateSerializer, eliminar `template_name` de ExpenseSerializer)
- `treasury/urls.py` (eliminar ruta)

**Dependencias:** Ninguna.
**Riesgo:** Bajo.
**Validación:** `python manage.py test apps.treasury` pasa. Endpoint `/expense-templates/` retorna 404.

---

### Paso 2: Migración 0007 — Crear modelo Payment

**Archivos:**
- `treasury/migrations/0007_create_payment.py`
- `treasury/models.py` (agregar clase Payment)

**Dependencias:** 0006 completada.
**Riesgo:** Bajo (es additive, no rompe nada).
**Validación:** `python manage.py migrate` sin errores. `Payment.objects.count() == 0`.

---

### Paso 3: Migración 0008 — Backfill de pagos históricos

**Archivos:**
- `treasury/migrations/0008_backfill_payments.py` (RunPython)

**Dependencias:** 0007 completada.
**Riesgo:** MEDIO (datos de producción).
**Validación:** Management command `python manage.py validate_payment_backfill`:
- Conteo: `Payment.count == Expense.filter(status=paid, payment_transaction__isnull=False).count + FixedExpensePeriod.filter(status=paid, payment_transaction__isnull=False).count`
- Cero Payment con amount <= 0
- Cero Payment sin business
- Log de gastos pagados sin transacción (inconsistencias históricas documentadas)

---

### Paso 4: Adaptar modelos Expense y FixedExpensePeriod

**Archivos:**
- `treasury/models.py`:
  - Expense: agregar @property `paid_at`, `paid_account`, `payment_transaction`, `total_paid`. Agregar `refresh_status()`.
  - FixedExpensePeriod: idem.
  - **NO eliminar campos DB todavía** (se hace en paso 8).

**Dependencias:** Paso 3 completado y validado.
**Riesgo:** MEDIO — los @property deben retornar exactamente lo mismo que los campos actuales.
**Validación:** Script que compara `expense.paid_at` (campo DB) vs `expense.paid_at` (@property) para TODOS los gastos. Deben coincidir.

> **NOTA:** En este paso los @property y los campos DB coexisten. Los @property se definen con nombre diferente temporalmente (`_paid_at_computed`) y se validan. Una vez validados, en paso 8 se renombran.

---

### Paso 5: Adaptar servicios (pay / void)

**Archivos:**
- `treasury/views.py`:
  - `ExpenseViewSet.pay()`: crear Payment + Transaction en atomic. Llamar `expense.refresh_status()`.
  - `FixedExpensePeriodViewSet.pay()`: idem.
  - `TransactionViewSet.void()`: buscar `txn.payment`, void-ear, refresh_status, propagar a fiscal.
  - `ExpenseViewSet.get_queryset()`: agregar prefetch_related.
  - `FixedExpensePeriodViewSet.get_queryset()`: idem.
  - Fix CSV export (hallazgo A1).

**Dependencias:** Paso 4 completado.
**Riesgo:** ALTO — flujos core de pago y anulación.
**Validación:** Tests E2E del flujo completo pay → verify → void → verify.

---

### Paso 6: Adaptar serializers

**Archivos:**
- `treasury/serializers.py`:
  - Agregar `PaymentSerializer` y `PaymentSummarySerializer`.
  - Adaptar `ExpenseSerializer`: campos legacy → SerializerMethodField. Agregar `payments`.
  - Adaptar `FixedExpensePeriodSerializer`: idem.

**Dependencias:** Paso 5 completado.
**Riesgo:** MEDIO — contrato API debe ser idéntico al actual.
**Validación:** Snapshot test: serializar un Expense pagado, comparar JSON con el formato anterior. Campos `paid_at`, `paid_account`, `paid_account_name`, `payment_transaction` presentes y con mismos valores.

---

### Paso 7: Tests completos

**Archivos:**
- `treasury/tests/test_payment.py` (nuevo)
- `treasury/tests/test_treasury.py` (adaptar existentes)
- `treasury/tests/test_backfill.py` (nuevo)

**Dependencias:** Pasos 5-6 completados.
**Riesgo:** BAJO.
**Validación:** 100% pass. Ver sección 10 para detalle de tests.

---

### Paso 8: Migración 0009 — Eliminar campos legacy

**Archivos:**
- `treasury/migrations/0009_remove_legacy_payment_fields.py`
- `treasury/models.py`: eliminar campos DB `paid_at`, `paid_account`, `payment_transaction`. Los @property ya cubren la lectura.

**Dependencias:** Paso 7 completado con tests verdes. Validación de backfill confirmada.
**Riesgo:** ALTO (irreversible).
**Validación:** `python manage.py test` completo. API responses idénticas.

**NOTA DE DEPLOY:** Se puede ejecutar 0009 en un deploy separado posterior, una vez confirmado que el sistema funciona correctamente con los @property leyendo de Payment.

---

### Paso 9: Agregar ruta Payment (read-only, opcional)

**Archivos:**
- `treasury/urls.py`: agregar `payments/` read-only.
- `treasury/views.py`: `PaymentViewSet` (list, retrieve only).

**Dependencias:** Paso 6.
**Riesgo:** BAJO.

---

## 10. Criterio de Done de Sprint 1

### Funcional

- [ ] `ExpenseTemplate` eliminado de código y DB
- [ ] Modelo `Payment` creado con constraints e índices
- [ ] Todo pago histórico backfilled a Payment (validado)
- [ ] `POST /expenses/{id}/pay/` crea Payment + Transaction correctamente
- [ ] `POST /fixed-expense-periods/{id}/pay/` crea Payment + Transaction correctamente
- [ ] `POST /transactions/{id}/void/` void-ea Payment + propaga a fiscal profile
- [ ] API responses idénticas al formato anterior (campos legacy computados)
- [ ] Campo nuevo `payments[]` disponible en response (aditivo)
- [ ] CSV export usa `csv.writer` (fix inyección)
- [ ] Frontend funciona sin cambios

### Tests requeridos

#### Unit tests (`test_payment.py`)

```
test_create_payment_for_expense
test_create_payment_for_fixed_expense_period
test_payment_exactly_one_source_constraint
test_payment_amount_must_be_positive
test_payment_void_changes_status
test_expense_total_paid_single_payment
test_expense_total_paid_multiple_payments
test_expense_refresh_status_pending
test_expense_refresh_status_paid
test_fep_refresh_status_pending
test_fep_refresh_status_paid
test_fep_refresh_status_skipped_unchanged
test_expense_paid_at_property_returns_latest
test_expense_paid_account_property
test_expense_payment_transaction_property
test_expense_properties_return_none_when_unpaid
```

#### Integration tests

```
test_pay_expense_creates_payment_and_transaction
test_pay_expense_auto_generated_blocked
test_pay_expense_already_paid_returns_400
test_pay_fixed_expense_period_creates_payment_and_transaction
test_pay_fixed_expense_period_amount_override
test_pay_fixed_expense_period_already_paid_returns_400
test_pay_fixed_expense_period_skipped_blocked
test_void_reverts_payment_and_expense_status
test_void_reverts_payment_and_fep_status
test_void_cascades_to_fiscal_profile
test_void_without_payment_still_works  # transacciones legacy sin Payment
test_void_already_voided_returns_400
```

#### Migración / backfill tests

```
test_backfill_creates_payment_for_paid_expense
test_backfill_creates_payment_for_paid_fep
test_backfill_handles_expense_without_transaction
test_backfill_skips_pending_expenses
test_backfill_payment_count_matches
test_reverse_backfill_deletes_all_payments
```

#### Regresión de serializers

```
test_expense_serializer_paid_at_from_payment
test_expense_serializer_includes_payments_array
test_expense_serializer_no_payment_returns_null
test_fep_serializer_paid_at_from_payment
test_fep_serializer_includes_payments_array
test_expense_list_no_n_plus_one  # assert query count with prefetch
test_fep_list_no_n_plus_one
```

#### Fiscal profile integration

```
test_void_marks_fiscal_profile_needs_review
test_void_creates_tax_status_log
test_void_without_fiscal_profile_no_error
test_pay_still_creates_fiscal_profile
```

#### CSV export fix

```
test_csv_export_escapes_commas
test_csv_export_escapes_newlines
test_csv_export_escapes_quotes
```

### Métricas de calidad

- 0 errores de `python manage.py check`
- 0 errores de `python manage.py test apps.treasury apps.tax_backup`
- 0 errores de tipo en frontend (si se agregan types de Payment)
- Query count de listados ≤ 5 queries (con prefetch)
- Backfill validation: 0 discrepancias reportadas

---

## Apéndice A: Diagrama de relaciones post-Sprint 1

```
┌──────────────────────┐     ┌──────────────────────────────┐
│      Expense         │     │      FixedExpensePeriod       │
│  ──────────────────  │     │  ──────────────────────────   │
│  id                  │     │  id                           │
│  business (FK)       │     │  fixed_expense (FK)           │
│  name                │     │  period                       │
│  amount              │     │  amount                       │
│  due_date            │     │  status (derived)             │
│  status (derived)    │     │  due_date                     │
│  category (FK)       │     │  notes                        │
│  notes               │     │                               │
│  attachment          │     │  @paid_at → Payment           │
│  source_type         │     │  @paid_account → Payment      │
│  source_id           │     │  @payment_transaction → Pay.  │
│  is_auto_generated   │     │                               │
│                      │     │  payments ← Payment (1:N)     │
│  @paid_at → Payment  │     └──────────┬───────────────────┘
│  @paid_account → Pay │                │
│  @payment_txn → Pay  │                │
│                      │                │
│  payments ← Pay (1:N)│                │
└──────────┬───────────┘                │
           │                            │
           │  ┌─────────────────────────┤
           │  │                         │
           ▼  ▼                         │
    ┌──────────────────┐                │
    │     Payment      │                │
    │  ──────────────  │                │
    │  id              │                │
    │  business (FK)   │                │
    │  expense (FK?)   │◄───────────────┘
    │  fixed_expense_  │
    │   period (FK?)   │  CheckConstraint:
    │  amount          │  exactly_one_source
    │  paid_at         │
    │  account (FK)    │
    │  transaction     │──────► Transaction (1:1)
    │   (OneToOne?)    │
    │  status          │  ┌──────────────────────┐
    │  notes           │  │     Transaction      │
    │  created_by (FK) │  │  ──────────────────  │
    │  created_at      │  │  id, direction,      │
    │  updated_at      │  │  amount, status,     │
    └──────────────────┘  │  reference_type/id,  │
                          │  account (FK), ...   │
                          │                      │
                          │  payment ← Payment   │
                          │    (reverse 1:1)     │
                          └──────────────────────┘

    ┌───────────────────────────────┐
    │   ExpenseFiscalProfile        │
    │  ─────────────────────────── │
    │  expense (1:1, FK?)           │──► Expense
    │  fixed_expense_period (1:1?)  │──► FixedExpensePeriod
    │  tax_status                   │
    │  ...                          │
    │                               │
    │  ← void() cascade:           │
    │    tax_status → NEEDS_REVIEW  │
    └───────────────────────────────┘
```

## Apéndice B: Secuencia de deploy recomendada

```
Deploy 1 (low risk):
  → Migración 0006 (drop ExpenseTemplate)
  → Code change: remove ExpenseTemplateViewSet, serializer, URL
  → ✅ Validar: frontend sin errores, /expense-templates/ = 404

Deploy 2 (medium risk):
  → Migración 0007 (create Payment table)
  → Migración 0008 (backfill)
  → Management command: validate_payment_backfill
  → ✅ Validar: conteo correcto, 0 discrepancias

Deploy 3 (high risk):
  → Code change: nuevos pay(), void(), serializers, prefetch
  → ✅ Validar: tests verdes, API functional test, frontend sin errores

Deploy 4 (irreversible, solo después de validar Deploy 3):
  → Migración 0009 (drop legacy columns)
  → ✅ Validar: sin errores, queries limpias

Opción alternativa: Deploy 2+3 juntos si hay confianza.
```

## Apéndice C: Decisiones diferidas a sprints posteriores

| Decisión | Sprint target | Razón del defer |
|----------|---------------|-----------------|
| Vincular ExpensePaymentDetail → Payment FK | Sprint 4 | No bloquea nada. Tax_backup funciona independiente. |
| Agregar `PARTIALLY_PAID` a Expense.Status | Sprint 2 | Requiere UI para pagos parciales. |
| Payroll como payable_type en Payment | Sprint 3+ | PayrollPayment tiene su propio flujo. Evaluar si se unifica. |
| Modelo Provider/Supplier | Sprint 2 | Útil pero no crítico para fundación de Payment. |
| Celery tasks de automatismos | Sprint 2 | No necesita Payment para funcionar. |
| Eliminar RecurringServiceProfile / ServicePeriodAlert | Sprint 2 | Zero functional surface pero no daña. |
| Pipeline documental OCR/QR | Sprint 4 | parse_status ya preparado en FiscalDocument. |
