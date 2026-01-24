from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.db import transaction
from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import CashMovement, CashSession, Payment
from apps.sales.models import Sale


def get_session_sales_queryset(session: CashSession, end_at=None):
  end_at = end_at or session.closed_at or timezone.now()
  zero = Decimal('0')
  payment_totals = (
    Payment.objects.filter(sale_id=OuterRef('pk'))
    .values('sale')
    .annotate(total=Sum('amount'))
    .values('total')[:1]
  )
  base_filters = Q(business=session.business, status=Sale.Status.COMPLETED)
  linked_sales = base_filters & Q(cash_session=session)
  legacy_sales = base_filters & Q(
    cash_session__isnull=True,
    created_at__gte=session.opened_at,
    created_at__lte=end_at,
  )
  return Sale.objects.filter(linked_sales | legacy_sales).annotate(
    paid_total=Coalesce(
      Subquery(payment_totals, output_field=DecimalField(max_digits=12, decimal_places=2)),
      Value(zero),
      output_field=DecimalField(max_digits=12, decimal_places=2),
    )
  )


def get_active_session(business, register_id: Optional[str] = None) -> Optional[CashSession]:
  queryset = CashSession.objects.filter(business=business, status=CashSession.Status.OPEN)
  if register_id:
    queryset = queryset.filter(register_id=register_id)
  return queryset.select_related('register', 'opened_by', 'closed_by').order_by('-opened_at').first()


def compute_session_totals(session: CashSession) -> Dict[str, Any]:
  zero = Decimal('0')

  payment_rows = session.payments.values('method').order_by().annotate(total=Sum('amount'))
  payments_by_method: Dict[str, Decimal] = {
    row['method']: (row['total'] or zero) for row in payment_rows
  }
  payments_total = sum(payments_by_method.values(), zero)
  cash_payments_total = payments_by_method.get(Payment.Method.CASH, zero)

  movement_rows = session.movements.values('movement_type').order_by().annotate(total=Sum('amount'))
  cash_in = zero
  cash_out = zero
  for row in movement_rows:
    if row['movement_type'] == CashMovement.MovementType.IN:
      cash_in += row['total'] or zero
    elif row['movement_type'] == CashMovement.MovementType.OUT:
      cash_out += row['total'] or zero

  expected_cash = (session.opening_cash_amount or zero) + cash_payments_total + cash_in - cash_out

  sales_count = (
    session.payments.values('sale_id')
    .order_by()
    .distinct()
    .aggregate(total=Count('sale_id'))
    .get('total', 0)
  )

  end_at = session.closed_at or timezone.now()
  pending_sales_queryset = get_session_sales_queryset(session, end_at=end_at)
  pending_sales_count = 0
  pending_sales_total = zero
  for sale in pending_sales_queryset:
    sale_total = sale.total or zero
    paid_total = sale.paid_total or zero
    pending_amount = sale_total - paid_total
    if pending_amount > 0:
      pending_sales_count += 1
      pending_sales_total += pending_amount

  return {
    'payments_total': payments_total,
    'payments_by_method': payments_by_method,
    'cash_payments_total': cash_payments_total,
    'movements_in_total': cash_in,
    'movements_out_total': cash_out,
    'cash_expected_total': expected_cash,
    'sales_count': sales_count,
    'pending_sales_count': pending_sales_count,
    'pending_sales_total': pending_sales_total,
  }


def collect_pending_session_sales(session: CashSession, *, user=None):
  zero = Decimal('0')
  reference = 'Cobro masivo en cierre de caja'
  with transaction.atomic():
    queryset = get_session_sales_queryset(session).select_for_update()
    collected_count = 0
    skipped = 0
    total_collected = zero
    sale_ids: list[str] = []
    for sale in queryset:
      sale_total = sale.total or zero
      paid_total = sale.paid_total or zero
      pending_amount = sale_total - paid_total
      if pending_amount <= 0:
        skipped += 1
        continue
      Payment.objects.create(
        business=sale.business,
        sale=sale,
        session=session,
        method=Payment.Method.CASH,
        amount=pending_amount,
        reference=reference,
        created_by=user if getattr(user, 'is_authenticated', False) else None,
      )
      collected_count += 1
      sale_ids.append(str(sale.id))
      total_collected += pending_amount

  return {
    'collected_count': collected_count,
    'skipped_count': skipped,
    'total_collected': total_collected,
    'sale_ids': sale_ids,
    'errors': [],
  }
