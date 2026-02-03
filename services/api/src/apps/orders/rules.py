from __future__ import annotations

from decimal import Decimal
from apps.sales.models import Sale

from .models import Order

LOCKED_ORDER_MESSAGE = 'Order is already paid and cannot be modified.'


def _iter_payments(sale: Sale | None):
    if sale is None:
        return []
    cache = getattr(sale, '_prefetched_objects_cache', None) or {}
    if 'payments' in cache:
        return cache['payments']
    return sale.payments.all()


def is_order_paid(order: Order) -> bool:
    if order.status == Order.Status.PAID:
        return True
    sale = getattr(order, 'sale', None)
    if sale is None:
        return False
    if sale.status == Sale.Status.CANCELLED:
        return False
    sale_total = Decimal(sale.total or 0)
    if sale_total <= 0:
        return False
    payments_total = sum((payment.amount for payment in _iter_payments(sale)), Decimal('0'))
    return payments_total >= sale_total


def is_order_editable(order: Order) -> bool:
    if is_order_paid(order):
        return False
    return order.status != Order.Status.CANCELLED
