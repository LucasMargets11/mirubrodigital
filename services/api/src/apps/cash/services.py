from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.db.models import Count, Sum

from .models import CashMovement, CashSession, Payment


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

  return {
    'payments_total': payments_total,
    'payments_by_method': payments_by_method,
    'cash_payments_total': cash_payments_total,
    'movements_in_total': cash_in,
    'movements_out_total': cash_out,
    'cash_expected_total': expected_cash,
    'sales_count': sales_count,
  }
