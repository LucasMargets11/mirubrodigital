# Sprint 1 — Correcciones Finales al Diseño Técnico

**Fecha:** 2026-03-25
**Base:** `SPRINT1_PAYMENT_DESIGN.md` (mismo día)
**Estado:** SECCIONES CORREGIDAS — reemplazan las equivalentes del documento base

---

## CORRECCIÓN 1: Decisión D2 — Pagos parciales

### D2. ¿Payment soporta pagos parciales desde Sprint 1?

**Decisión anterior (ANULADA):** "SÍ. Payment soporta pagos parciales desde Sprint 1."

**Decisión corregida: NO operativamente. SÍ estructuralmente.**

**Recomendación final: Opción (a) — Modelo preparado, operación bloqueada.**

#### Justificación

1. **No hay UI para parciales.** El frontend envía `pay()` sin monto personalizado en Expense. No existe formulario de "pago parcial" ni indicación visual de saldo pendiente.

2. **El endpoint `ExpenseViewSet.pay()` no acepta `amount`.** Siempre usa `expense.amount` completo. Soportar parciales requiere modificar el contrato del endpoint, agregar validación de monto, y manejar la secuencia de pagos acumulados — todo fuera de scope de Sprint 1.

3. **`FixedExpensePeriod.pay()` acepta `amount` override, pero lo guarda EN `period.amount`**, sobreescribiendo el valor original. Esto no es un pago parcial — es un pago por un monto diferente. El resultado final sigue siendo status=PAID por el total.

4. **La contradicción concreta era:** D2 afirmaba soporte parcial, pero `refresh_status()` colapsaba `0 < total < amount` a `PAID`. Eso no es soporte, es un bug latente vestido de simplificación.

5. **Costo de preparar sin activar: CERO.** La FK sin UniqueConstraint ya permite N pagos. No se necesita nada adicional en schema.

#### Qué cambia en el diseño

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| Relación Payment→Expense | 1:N (FK sin unique). OK, no cambia. | 1:N (FK sin unique). Idéntico. |
| Guard en `pay()` | No había guard contra segundo pago | **NUEVO:** `pay()` rechaza si ya existe Payment(status=COMPLETED) para ese Expense/Period |
| `Expense.Status` enum | PENDING, PAID, CANCELLED (sin PARTIALLY_PAID) | Idéntico. No se agrega PARTIALLY_PAID en Sprint 1. |
| `refresh_status()` | Trataba parcial como PAID (bug) | **Simplificado:** No hay case parcial. Si hay ≥1 completed payment → PAID. Si hay 0 → PENDING. |
| `total_paid` property | Existía | Se mantiene para preparación. Útil para validación y Sprint 2. |
| `remaining_amount` | No existía | **NUEVO (computed, no persistido):** `expense.amount - expense.total_paid`. Preparación para Sprint 2. No se usa en lógica de Sprint 1. |

#### `refresh_status()` corregido

```python
# Expense
def refresh_status(self):
    """Recalcula status basado en pagos completados."""
    if self.is_auto_generated:
        return
    has_payment = self.payments.filter(
        status=Payment.Status.COMPLETED
    ).exists()
    if has_payment:
        self.status = self.Status.PAID
    else:
        if self.status != self.Status.CANCELLED:
            self.status = self.Status.PENDING
    self.save(update_fields=['status'])

# FixedExpensePeriod
def refresh_status(self):
    """Recalcula status basado en pagos. No toca SKIPPED."""
    if self.status == self.Status.SKIPPED:
        return
    has_payment = self.payments.filter(
        status=Payment.Status.COMPLETED
    ).exists()
    self.status = self.Status.PAID if has_payment else self.Status.PENDING
    self.save(update_fields=['status'])
```

#### Guard en `pay()` corregido

```python
# En ExpenseViewSet.pay() — al inicio del atomic block
existing = Payment.objects.filter(
    expense=expense, status=Payment.Status.COMPLETED
).exists()
if existing:
    return Response(
        {'detail': 'Este gasto ya tiene un pago completado.'},
        status=status.HTTP_400_BAD_REQUEST,
    )

# En FixedExpensePeriodViewSet.pay() — ídem
existing = Payment.objects.filter(
    fixed_expense_period=period, status=Payment.Status.COMPLETED
).exists()
if existing:
    return Response(
        {'detail': 'Este período ya tiene un pago completado.'},
        status=status.HTTP_400_BAD_REQUEST,
    )
```

#### Propiedades de preparación para Sprint 2

```python
# En Expense y FixedExpensePeriod
@property
def total_paid(self):
    from django.db.models import Sum
    return self.payments.filter(
        status=Payment.Status.COMPLETED
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

@property
def remaining_amount(self):
    return max(self.amount - self.total_paid, Decimal('0'))
```

#### Transición a Sprint 2

Cuando se quiera activar pagos parciales:

1. Agregar `PARTIALLY_PAID = 'partially_paid'` a `Expense.Status`
2. Modificar `refresh_status()` para derivar 3 estados:
   - `UNPAID`: `total_paid == 0`
   - `PARTIALLY_PAID`: `0 < total_paid < amount`
   - `PAID`: `total_paid >= amount`
3. Remover el guard que bloquea segundo pago
4. Agregar `amount` param al endpoint `pay()` de Expense
5. Agregar UI de saldo pendiente

**No requiere cambio de schema.** Solo código y migración de datos de enum.

**Decisión: CONGELADA.**

---

## CORRECCIÓN 2: Estrategia de migración y backfill (reemplaza §5 completa)

### 5.1 Migraciones de schema (sin cambios en orden)

Las migraciones 0006–0009 mantienen el mismo orden. Los cambios están en el **contenido** de 0008 y en la **estrategia de rollback**.

### 5.2 Backfill corregido (Migración 0008)

#### Principios de diseño del backfill

1. **Idempotencia:** Ejecutar el backfill N veces produce el mismo resultado. Si un Payment ya existe para un Expense/Period, se salta.
2. **Dry run obligatorio:** Antes de ejecutar la migración, se corre un management command que simula el backfill sin escribir, y reporta conteos y discrepancias.
3. **Fuente de verdad para amount:** Ver sección 5.3.
4. **Discrepancias documentadas:** Cada inconsistencia se loguea a un reporte JSON, no se silencia.

#### Código corregido

```python
import json
import logging
from decimal import Decimal

logger = logging.getLogger('treasury.backfill')


def backfill_payments(apps, schema_editor):
    Payment = apps.get_model('treasury', 'Payment')
    Expense = apps.get_model('treasury', 'Expense')
    FixedExpensePeriod = apps.get_model('treasury', 'FixedExpensePeriod')

    discrepancies = []
    created_count = 0
    skipped_count = 0

    # ── 1. Backfill desde Expense ──────────────────────────────
    paid_expenses = (
        Expense.objects
        .filter(status='paid')
        .select_related('payment_transaction', 'paid_account')
    )

    payments_to_create = []
    for exp in paid_expenses.iterator(chunk_size=500):
        # Idempotencia: si ya existe Payment para este Expense, saltar
        if Payment.objects.filter(expense_id=exp.id, status='completed').exists():
            skipped_count += 1
            continue

        amount, source, disc = _resolve_amount(
            transaction=exp.payment_transaction,
            source_amount=exp.amount,
            source_label=f'expense:{exp.id}',
        )
        if disc:
            discrepancies.append(disc)

        if exp.payment_transaction_id:
            txn = exp.payment_transaction
            payments_to_create.append(Payment(
                business_id=exp.business_id,
                expense_id=exp.id,
                fixed_expense_period=None,
                amount=amount,
                paid_at=exp.paid_at or txn.occurred_at,
                account_id=(
                    txn.account_id
                    if txn.account_id
                    else exp.paid_account_id
                ),
                transaction_id=txn.id,
                status='completed',
                created_by_id=txn.created_by_id,
                notes=f'Backfill from expense. Amount source: {source}',
            ))
        elif exp.paid_at and exp.paid_account_id:
            # Expense PAID sin transaction — data inconsistente pero con
            # suficiente info para crear Payment
            payments_to_create.append(Payment(
                business_id=exp.business_id,
                expense_id=exp.id,
                fixed_expense_period=None,
                amount=amount,
                paid_at=exp.paid_at,
                account_id=exp.paid_account_id,
                transaction=None,
                status='completed',
                notes=f'Backfill from expense (no transaction). Amount source: {source}',
            ))
            discrepancies.append({
                'type': 'expense_paid_no_transaction',
                'id': exp.id,
                'business_id': exp.business_id,
                'amount': str(amount),
            })
        else:
            # Expense con status=paid pero sin datos de pago suficientes
            discrepancies.append({
                'type': 'expense_paid_insufficient_data',
                'id': exp.id,
                'business_id': exp.business_id,
                'paid_at': str(exp.paid_at),
                'paid_account_id': exp.paid_account_id,
                'transaction_id': exp.payment_transaction_id,
            })
            continue

    # ── 2. Backfill desde FixedExpensePeriod ───────────────────
    paid_periods = (
        FixedExpensePeriod.objects
        .filter(status='paid')
        .select_related('payment_transaction', 'paid_account', 'fixed_expense')
    )

    for period in paid_periods.iterator(chunk_size=500):
        if Payment.objects.filter(
            fixed_expense_period_id=period.id, status='completed'
        ).exists():
            skipped_count += 1
            continue

        amount, source, disc = _resolve_amount(
            transaction=period.payment_transaction,
            source_amount=period.amount,
            source_label=f'fixed_expense_period:{period.id}',
        )
        if disc:
            discrepancies.append(disc)

        if period.payment_transaction_id:
            txn = period.payment_transaction
            payments_to_create.append(Payment(
                business_id=period.fixed_expense.business_id,
                expense=None,
                fixed_expense_period_id=period.id,
                amount=amount,
                paid_at=period.paid_at or txn.occurred_at,
                account_id=(
                    txn.account_id
                    if txn.account_id
                    else period.paid_account_id
                ),
                transaction_id=txn.id,
                status='completed',
                created_by_id=txn.created_by_id,
                notes=f'Backfill from period. Amount source: {source}',
            ))
        elif period.paid_at and period.paid_account_id:
            payments_to_create.append(Payment(
                business_id=period.fixed_expense.business_id,
                fixed_expense_period_id=period.id,
                expense=None,
                amount=amount,
                paid_at=period.paid_at,
                account_id=period.paid_account_id,
                transaction=None,
                status='completed',
                notes=f'Backfill from period (no transaction). Amount source: {source}',
            ))
            discrepancies.append({
                'type': 'period_paid_no_transaction',
                'id': period.id,
                'business_id': period.fixed_expense.business_id,
                'amount': str(amount),
            })
        else:
            discrepancies.append({
                'type': 'period_paid_insufficient_data',
                'id': period.id,
                'business_id': period.fixed_expense.business_id,
            })
            continue

    # ── 3. Bulk create ─────────────────────────────────────────
    Payment.objects.bulk_create(payments_to_create, batch_size=500)
    created_count = len(payments_to_create)

    # ── 4. Reporte de discrepancias ────────────────────────────
    if discrepancies:
        logger.warning(
            'Payment backfill completed with %d discrepancies. '
            'Created: %d, Skipped (idempotent): %d',
            len(discrepancies), created_count, skipped_count,
        )
        # Guardar reporte en tabla temporal o log
        logger.warning('Discrepancies:\n%s', json.dumps(discrepancies, indent=2))
    else:
        logger.info(
            'Payment backfill completed cleanly. '
            'Created: %d, Skipped: %d',
            created_count, skipped_count,
        )


def _resolve_amount(transaction, source_amount, source_label):
    """
    Determina el monto correcto para un Payment basado en prioridad de fuentes.
    
    Retorna: (amount, source_description, discrepancy_dict_or_None)
    """
    disc = None

    if transaction and transaction.amount:
        amount = transaction.amount
        source = 'transaction'

        # Detectar discrepancia entre transaction y source
        if source_amount and transaction.amount != source_amount:
            disc = {
                'type': 'amount_mismatch',
                'source': source_label,
                'transaction_id': transaction.id,
                'transaction_amount': str(transaction.amount),
                'source_amount': str(source_amount),
                'used': 'transaction',
                'delta': str(transaction.amount - source_amount),
            }
    elif source_amount:
        amount = source_amount
        source = 'source_model'
    else:
        amount = Decimal('0.0001')  # mínimo para pasar CheckConstraint
        source = 'fallback_minimum'
        disc = {
            'type': 'no_amount_available',
            'source': source_label,
            'note': 'Neither transaction nor source model had amount',
        }

    return amount, source, disc


def reverse_backfill(apps, schema_editor):
    """
    Rollback: solo seguro PRE-CUTOVER (antes de Deploy 3).
    Después de Deploy 3, usar estrategia de reverse completa (ver §5.4).
    """
    Payment = apps.get_model('treasury', 'Payment')
    # Solo borrar Payments que fueron creados por backfill
    Payment.objects.filter(notes__startswith='Backfill from').delete()
```

### 5.3 Prioridad de fuentes para `Payment.amount` (NUEVO)

| Prioridad | Fuente | Justificación |
|-----------|--------|---------------|
| **1 (preferida)** | `Transaction.amount` | Es el registro financiero real: el dinero que se movió de la cuenta. Es la fuente de verdad contable. |
| **2 (fallback)** | `Expense.amount` / `FixedExpensePeriod.amount` | Valor declarado del gasto. Puede diferir del transaction si hubo override de monto en `period.pay(amount=X)` que actualizó `period.amount` pero la transaction tiene el monto real. |
| **3 (último recurso)** | Mínimo `0.0001` + discrepancia logueada | Para registros con status=paid pero sin monto resoluble. Se documenta para revisión manual. |

**Manejo de inconsistencias:**

Cuando `Transaction.amount != Expense/Period.amount`:

- Se usa `Transaction.amount` como monto del Payment (es el dinero real).
- Se loguea la discrepancia con ambos valores y el delta.
- El reporte de dry run muestra todas las discrepancias antes de ejecutar.
- Post-backfill, el management command `validate_payment_backfill` cruza `Payment.amount` vs `Transaction.amount` y reporta diferencias (debe ser 0 si la prioridad se respetó).

**¿Por qué NO usar `Expense.amount` como primera fuente?**

En `FixedExpensePeriod.pay()`, el endpoint acepta un `amount` override y actualiza `period.amount = amount`. Pero la Transaction ya fue creada con ese monto. Si el período fue editado posteriormente (se cambió el amount por algún ajuste manual en admin), `period.amount` ya no corresponde al pago real, pero `Transaction.amount` sí.

Para `Expense`, en la implementación actual `pay()` usa `expense.amount` directamente para la Transaction. Deberían coincidir, pero si algún proceso manual o bug modificó `expense.amount` post-pago, la Transaction es la fuente de verdad financiera.

### 5.4 Estrategia de rollback post-cutover (NUEVO — reemplaza §5.3 original)

La estrategia se divide en dos escenarios según el punto de avance del deploy.

#### Escenario A: Rollback PRE-CUTOVER (antes de Deploy 3)

Los campos legacy (`paid_at`, `paid_account`, `payment_transaction`) todavía existen en la DB. El código viejo todavía los lee.

```
1. Revertir migración 0008: DELETE Payment WHERE notes LIKE 'Backfill%'
2. Revertir migración 0007: DROP TABLE treasury_payment
3. Deploy código anterior
→ El sistema vuelve al estado original. Sin pérdida de datos.
```

**Riesgo:** BAJO. Los campos legacy nunca se tocaron.

#### Escenario B: Rollback POST-CUTOVER (después de Deploy 3, antes de Deploy 4)

El código nuevo ya está escribiendo Payments en producción. Los campos legacy todavía existen en DB pero ya no se escriben (solo se leen via @property). Puede haber Payments nuevos (creados por pay() del código nuevo) que no existían en el backfill.

```
Paso 1: Deploy código anterior (que lee campos legacy)
        → El sistema funciona porque paid_at/paid_account/payment_transaction
          siguen en la DB con datos del backfill original.
        → PERO: pagos nuevos (post-cutover) NO están en campos legacy.
        
Paso 2: Ejecutar management command reverse_populate_legacy:
        → Para cada Payment con status=COMPLETED creado DESPUÉS del cutover:
           UPDATE expense SET
             paid_at = payment.paid_at,
             paid_account_id = payment.account_id,
             payment_transaction_id = payment.transaction_id
           WHERE expense.id = payment.expense_id
             AND expense.paid_at IS NULL;   -- solo si no tiene dato legacy
        → Ídem para FixedExpensePeriod.
        
Paso 3: Validar que todos los Expense/Period con status=PAID tienen
        paid_at, paid_account, payment_transaction populados.

Paso 4: (Opcional) Revertir migraciones 0008/0007 una vez validado.
```

#### Escenario C: Rollback POST-DROP (después de Deploy 4 — migración 0009 ejecutada)

Los campos legacy YA NO EXISTEN en la DB. Este es el escenario más complejo.

```
Paso 1: Ejecutar migración reversa de 0009:
        → Re-agregar columnas paid_at, paid_account, payment_transaction
          a Expense y FixedExpensePeriod (nullable).

Paso 2: Ejecutar management command reverse_populate_legacy:
        → Poblar campos legacy DESDE Payment para TODOS los registros.
        → Prioridad: Payment más reciente con status=COMPLETED.
        
Paso 3: Validar conteos:
        - Expense.filter(status=paid).count() == 
          Expense.filter(paid_at__isnull=False).count()
        
Paso 4: Deploy código anterior.

Paso 5: (Opcional) Revertir 0008/0007.
```

#### Management command: `reverse_populate_legacy`

```python
# treasury/management/commands/reverse_populate_legacy.py

class Command(BaseCommand):
    help = 'Reconstituye campos legacy desde Payment (para rollback post-cutover)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Simular sin escribir')
        parser.add_argument('--only-missing', action='store_true',
                            help='Solo poblar registros donde paid_at IS NULL')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        only_missing = options['only_missing']
        
        updated = 0
        errors = 0
        
        # Expense
        payments_for_expenses = (
            Payment.objects
            .filter(expense__isnull=False, status='completed')
            .select_related('expense', 'account', 'transaction')
            .order_by('expense_id', '-paid_at')
            .distinct('expense_id')  # PostgreSQL: un Payment por Expense
        )
        
        for payment in payments_for_expenses:
            exp = payment.expense
            if only_missing and exp.paid_at is not None:
                continue
            if not dry_run:
                Expense.objects.filter(id=exp.id).update(
                    paid_at=payment.paid_at,
                    paid_account_id=payment.account_id,
                    payment_transaction_id=payment.transaction_id,
                )
            updated += 1

        # FixedExpensePeriod (mismo patrón)
        payments_for_periods = (
            Payment.objects
            .filter(fixed_expense_period__isnull=False, status='completed')
            .select_related('fixed_expense_period', 'account', 'transaction')
            .order_by('fixed_expense_period_id', '-paid_at')
            .distinct('fixed_expense_period_id')
        )
        
        for payment in payments_for_periods:
            period = payment.fixed_expense_period
            if only_missing and period.paid_at is not None:
                continue
            if not dry_run:
                FixedExpensePeriod.objects.filter(id=period.id).update(
                    paid_at=payment.paid_at,
                    paid_account_id=payment.account_id,
                    payment_transaction_id=payment.transaction_id,
                )
            updated += 1

        verb = 'Would update' if dry_run else 'Updated'
        self.stdout.write(f'{verb} {updated} records. Errors: {errors}')
```

#### Management command: `dry_run_payment_backfill` (NUEVO)

Simula el backfill completo sin escribir. Se ejecuta ANTES de la migración 0008.

```python
# treasury/management/commands/dry_run_payment_backfill.py

class Command(BaseCommand):
    help = 'Dry run del backfill de Payment — reporta sin escribir'

    def handle(self, *args, **options):
        report = {
            'expenses_paid_with_txn': 0,
            'expenses_paid_no_txn': 0,
            'expenses_paid_insufficient': 0,
            'periods_paid_with_txn': 0,
            'periods_paid_no_txn': 0,
            'periods_paid_insufficient': 0,
            'amount_mismatches': [],
            'total_to_create': 0,
        }

        # Simular lógica del backfill (sin escribir)
        paid_expenses = Expense.objects.filter(status='paid').select_related(
            'payment_transaction'
        )
        for exp in paid_expenses.iterator():
            if exp.payment_transaction_id:
                report['expenses_paid_with_txn'] += 1
                txn = exp.payment_transaction
                if txn.amount != exp.amount:
                    report['amount_mismatches'].append({
                        'type': 'expense',
                        'id': exp.id,
                        'txn_amount': str(txn.amount),
                        'exp_amount': str(exp.amount),
                    })
            elif exp.paid_at and exp.paid_account_id:
                report['expenses_paid_no_txn'] += 1
            else:
                report['expenses_paid_insufficient'] += 1

        # Ídem para periods...
        paid_periods = FixedExpensePeriod.objects.filter(
            status='paid'
        ).select_related('payment_transaction')
        for period in paid_periods.iterator():
            if period.payment_transaction_id:
                report['periods_paid_with_txn'] += 1
                txn = period.payment_transaction
                if txn.amount != period.amount:
                    report['amount_mismatches'].append({
                        'type': 'period',
                        'id': period.id,
                        'txn_amount': str(txn.amount),
                        'period_amount': str(period.amount),
                    })
            elif period.paid_at and period.paid_account_id:
                report['periods_paid_no_txn'] += 1
            else:
                report['periods_paid_insufficient'] += 1

        report['total_to_create'] = (
            report['expenses_paid_with_txn']
            + report['expenses_paid_no_txn']
            + report['periods_paid_with_txn']
            + report['periods_paid_no_txn']
        )

        self.stdout.write(json.dumps(report, indent=2))
        
        if report['amount_mismatches']:
            self.stderr.write(
                f"⚠ {len(report['amount_mismatches'])} amount mismatches detected. "
                f"Transaction.amount will be used as source of truth."
            )
        if (report['expenses_paid_insufficient']
                + report['periods_paid_insufficient']) > 0:
            self.stderr.write(
                f"⚠ {report['expenses_paid_insufficient'] + report['periods_paid_insufficient']} "
                f"records with status=paid but insufficient data for Payment creation."
            )
```

#### Tabla resumen de rollback corregida

| Punto de avance | Acción de rollback | Riesgo | Pérdida de datos |
|---|---|---|---|
| Pre-cutover (Deploy 1–2) | Revert migrations + deploy código anterior | BAJO | Ninguna |
| Post-cutover, pre-drop (Deploy 3) | Deploy código anterior + `reverse_populate_legacy --only-missing` | MEDIO | Ninguna si se ejecuta el command |
| Post-drop (Deploy 4) | Revert 0009 + `reverse_populate_legacy` + deploy código anterior | ALTO | Ninguna, pero requiere pasos manuales |

**Regla operacional:** Deploy 4 (migración 0009) NO se ejecuta hasta que:
1. Deploy 3 lleva ≥48h sin incidentes en producción.
2. Se confirmó que los @property retornan datos correctos para el 100% de los registros.
3. Se tiene backup del DB pre-0009 etiquetado y verificado.

---

## CORRECCIÓN 3: Impacto sobre tax_backup — Desacoplamiento de cascada fiscal

### Problema con el diseño anterior

El documento anterior proponía esta lógica **directamente en `treasury/views.py`**:

```python
# ❌ ANTES (en treasury/views.py void()):
from apps.tax_backup.models import ExpenseFiscalProfile
from apps.tax_backup.rules import evaluate_tax_status
from apps.tax_backup.models import TaxStatusLog

profile = ExpenseFiscalProfile.objects.filter(expense=payment.expense).first()
if profile:
    old_status = profile.tax_status
    profile.tax_status = TaxStatus.NEEDS_REVIEW
    profile.review_reason = f'Pago anulado...'
    profile.save(...)
    TaxStatusLog.objects.create(...)
```

**Problemas:**
1. Treasury importa y manipula directamente modelos internos de tax_backup (acoplamiento fuerte).
2. Conoce los campos `tax_status`, `review_reason`, `TaxStatusLog` — detalle de implementación fiscal.
3. Si tax_backup cambia su schema o agrega lógica (e.g., evaluar reglas antes de marcar NEEDS_REVIEW), hay que modificar treasury.
4. Rompe la responsabilidad: treasury no debería saber cómo funciona la contabilidad fiscal.

### Solución: Servicio dedicado en tax_backup

Treasury llama a un método público de tax_backup. Tax_backup encapsula toda la lógica fiscal.

#### Nuevo método en `tax_backup/services.py`

```python
# services/api/src/apps/tax_backup/services.py

# ── Funciones existentes (no cambian) ──────────────────────
def ensure_fiscal_profile_for_expense(expense):
    ...  # sin cambios

def ensure_fiscal_profile_for_fixed_expense_period(period):
    ...  # sin cambios


# ── NUEVO: Cascada fiscal por anulación de pago ───────────
def handle_payment_voided(expense=None, fixed_expense_period=None, reason=''):
    """
    Llamado por treasury cuando se anula un pago.
    Busca el perfil fiscal asociado y lo marca para revisión.
    
    Es idempotente: si no hay perfil, no hace nada.
    Si el perfil ya está en NEEDS_REVIEW, solo actualiza la razón.
    
    Args:
        expense: Expense instance (o None)
        fixed_expense_period: FixedExpensePeriod instance (o None)
        reason: Texto descriptivo del motivo de la anulación
    """
    from .models import ExpenseFiscalProfile, TaxStatusLog, TaxStatus

    profile = None
    if expense:
        profile = ExpenseFiscalProfile.objects.filter(
            expense=expense
        ).first()
    elif fixed_expense_period:
        profile = ExpenseFiscalProfile.objects.filter(
            fixed_expense_period=fixed_expense_period
        ).first()

    if not profile:
        return  # No hay perfil fiscal — nada que hacer

    old_status = profile.tax_status

    # Si ya está en revisión, solo actualizar razón
    profile.tax_status = TaxStatus.NEEDS_REVIEW
    profile.review_reason = reason or 'Pago anulado. Requiere revisión fiscal.'
    profile.save(update_fields=['tax_status', 'review_reason', 'updated_at'])

    TaxStatusLog.objects.create(
        fiscal_profile=profile,
        previous_status=old_status,
        new_status=TaxStatus.NEEDS_REVIEW,
        rule_code='VOID_PAYMENT_CASCADE',
        note=reason or 'Pago anulado → perfil marcado para revisión.',
    )
```

#### Llamada desde treasury (limpia)

```python
# services/api/src/apps/treasury/views.py — en void()

# ✅ DESPUÉS: treasury solo conoce la interfaz pública
from apps.tax_backup.services import handle_payment_voided

# Dentro del atomic block, después de void-ear el Payment:
if payment.expense_id:
    handle_payment_voided(
        expense=payment.expense,
        reason=f'Transacción #{txn.id} anulada.',
    )
elif payment.fixed_expense_period_id:
    handle_payment_voided(
        fixed_expense_period=payment.fixed_expense_period,
        reason=f'Transacción #{txn.id} anulada.',
    )
```

#### Comparación

| Aspecto | Antes (inline en treasury) | Después (servicio en tax_backup) |
|---------|---------------------------|----------------------------------|
| Imports en treasury | `ExpenseFiscalProfile`, `TaxStatusLog`, `TaxStatus`, `evaluate_tax_status` | Solo `handle_payment_voided` |
| Conocimiento fiscal en treasury | Completo (campos, estados, log) | Cero (solo interface) |
| Cambios en tax_backup schema | Requieren editar treasury | Transparentes — solo tax_backup |
| Testing | Mock complejo de 4 modelos | Mock de una función |
| Comportamiento funcional | Idéntico | Idéntico |

#### Llamada desde `pay()` (sin cambios funcionales, solo consistencia)

La llamada existente a `ensure_fiscal_profile_for_expense()` ya está correctamente en tax_backup/services.py. No requiere cambios.

```python
# En ExpenseViewSet.pay() — ya es correcto:
from apps.tax_backup.services import ensure_fiscal_profile_for_expense
ensure_fiscal_profile_for_expense(expense)

# En FixedExpensePeriodViewSet.pay() — ya es correcto:
from apps.tax_backup.services import ensure_fiscal_profile_for_fixed_expense_period
ensure_fiscal_profile_for_fixed_expense_period(period)
```

#### Diagrama de dependencias corregido

```
treasury/views.py
  ├── pay()  ──calls──►  tax_backup/services.py :: ensure_fiscal_profile_for_expense()
  │                       tax_backup/services.py :: ensure_fiscal_profile_for_fixed_expense_period()
  │
  └── void() ──calls──►  tax_backup/services.py :: handle_payment_voided()
                          ↓
                          tax_backup/models.py (interno, no expuesto a treasury)
                            ├── ExpenseFiscalProfile
                            ├── TaxStatusLog
                            └── TaxStatus enum

Treasury NUNCA importa directamente de tax_backup/models.py
```

---

## CORRECCIÓN 4: Plan de implementación ajustado

### Cambios al plan original

Los pasos 1–3 y 6–9 se mantienen con ajustes menores. Los cambios significativos están en **Paso 4** (refresh_status), **Paso 5** (void con desacoplamiento fiscal), y un **nuevo Paso 3b** (dry run).

### Paso 3b (NUEVO): Dry run de backfill

**Archivos:**
- `treasury/management/commands/dry_run_payment_backfill.py` (nuevo)

**Ejecución:** `python manage.py dry_run_payment_backfill`
**Dependencias:** Paso 2 completado (modelo Payment existe).
**Riesgo:** CERO (read-only).
**Validación:** Output JSON sin discrepancias críticas. Si hay `amount_mismatches`, documentarlos y confirmar que el uso de `Transaction.amount` es aceptable. Si hay `paid_insufficient`, decidir manejo caso a caso antes de proceder.

**Regla:** Migración 0008 NO se ejecuta sin dry run previo aprobado.

### Paso 3 (ajustado): Migración 0008 — Backfill

**Cambios vs. original:**
- `_resolve_amount()` usa Transaction.amount como primera fuente
- Backfill es idempotente (check de existencia antes de crear)
- `reverse_backfill` solo borra Payments marcados como backfill (via `notes LIKE 'Backfill%'`)
- Discrepancias se loguean, no se silencian

### Paso 4 (ajustado): Modelos Expense y FixedExpensePeriod

**Cambios vs. original:**
- `refresh_status()` simplificado: solo PENDING/PAID binario, sin case parcial
- Guard contra segundo pago completado (nuevo)
- `remaining_amount` property preparatorio (nuevo, no usado en lógica)

### Paso 5 (ajustado): Adaptar servicios (pay / void)

**Cambios vs. original:**

| Sub-paso | Antes | Ahora |
|----------|-------|-------|
| `void()` cascada fiscal | Lógica fiscal inline en treasury/views.py | Llamada a `handle_payment_voided()` de tax_backup/services.py |
| `void()` imports | 4 imports de tax_backup.models | 1 import de tax_backup.services |
| `pay()` guard | Check `expense.status == PAID` | Check `Payment.exists(expense=expense, status=COMPLETED)` (más robusto) |

**Archivos afectados adicionales:**
- `services/api/src/apps/tax_backup/services.py` — agregar `handle_payment_voided()`

### Paso 7 (ajustado): Tests adicionales

Tests nuevos requeridos por las correcciones:

```
# Idempotencia de backfill
test_backfill_idempotent_skips_existing_payments
test_backfill_amount_from_transaction_when_available
test_backfill_amount_fallback_to_source_when_no_transaction
test_backfill_logs_amount_mismatch

# Guard de pago único en Sprint 1
test_pay_expense_twice_returns_400
test_pay_fep_twice_returns_400
test_pay_after_void_allows_new_payment

# Desacoplamiento fiscal
test_void_calls_handle_payment_voided
test_handle_payment_voided_marks_needs_review
test_handle_payment_voided_creates_log
test_handle_payment_voided_no_profile_no_error
test_handle_payment_voided_idempotent_on_repeated_call

# Dry run
test_dry_run_reports_correct_counts
test_dry_run_detects_amount_mismatches

# Rollback helpers
test_reverse_populate_legacy_from_payment
test_reverse_populate_legacy_dry_run
test_reverse_populate_legacy_only_missing
```

### Deploy corregido (Apéndice B)

```
Deploy 1 (low risk):
  → Migración 0006 (drop ExpenseTemplate)
  → Code change: remove ExpenseTemplateViewSet, serializer, URL
  → ✅ Validar: frontend sin errores, /expense-templates/ = 404

Deploy 2 (medium risk):
  ANTES de migrar:
  → python manage.py dry_run_payment_backfill
  → Revisar output. Aprobar o resolver discrepancias.
  
  Migrar:
  → Migración 0007 (create Payment table)
  → Migración 0008 (backfill con prioridad Transaction.amount)
  → python manage.py validate_payment_backfill
  → ✅ Validar: conteo correcto, discrepancias esperadas documentadas

Deploy 3 (high risk — CUTOVER):
  → Agregar handle_payment_voided() a tax_backup/services.py
  → Code change: pay(), void(), serializers, prefetch, guards
  → ✅ Validar: tests verdes, API functional test, frontend sin errores
  → ✅ Monitorear 48h antes de Deploy 4

Deploy 4 (irreversible, solo después de validar Deploy 3 + 48h):
  → Snapshot/backup de DB etiquetado: pre-0009-{timestamp}
  → Migración 0009 (drop legacy columns)
  → ✅ Validar: sin errores, queries limpias
```

---

## Resumen de decisiones congeladas afectadas

| ID | Decisión Original | Estado | Decisión Corregida |
|----|-------------------|--------|-------------------|
| D2 | Payment soporta pagos parciales desde Sprint 1 | **CORREGIDA** | Estructura 1:N preparada, operación bloqueada. Guard contra segundo pago. Sin PARTIALLY_PAID en Sprint 1. |
| D5 | Payment states: COMPLETED, VOIDED only | Sin cambio | Idéntica. |
| D5b | (implícita) Expense.status derivado colapsa parcial a PAID | **CORREGIDA** | No hay case parcial. Binario: PENDING (0 payments) / PAID (≥1 payment). Parciales se activan en Sprint 2. |

| ID | Decisión Nueva | Estado |
|----|----------------|--------|
| D9 | Backfill usa Transaction.amount como fuente primaria de Payment.amount | **CONGELADA** |
| D10 | Dry run obligatorio antes de backfill en producción | **CONGELADA** |
| D11 | Backfill es idempotente (safe to re-run) | **CONGELADA** |
| D12 | Cascada fiscal pasa por tax_backup/services.py, nunca inline en treasury | **CONGELADA** |
| D13 | Deploy 4 requiere 48h sin incidentes post-Deploy 3 + backup etiquetado | **CONGELADA** |
